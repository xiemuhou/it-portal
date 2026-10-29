import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from portal.database import TABLES, make_engine, metadata
from portal.migrate_database import EXCLUDED_TABLES, _revisions_compatible, _source_summaries, _table_summary, _transfer
from portal.security import seed


class CrossDatabaseMigrationTests(unittest.TestCase):
    def test_mysql_precision_repair_revision_is_compatible_with_0018_source(self):
        self.assertTrue(_revisions_compatible('0018_remove_portal_backup', '0018_remove_portal_backup'))
        self.assertTrue(_revisions_compatible('0018_remove_portal_backup', '0019_mysql_datetime_precision'))
        self.assertFalse(_revisions_compatible('0017_shared_ip_department', '0019_mysql_datetime_precision'))

    def test_fresh_schema_creates_ipam_base_before_computer_lifecycle(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory, 'fresh.db').as_posix()
            with patch.dict('os.environ', {'IT_PORTAL_DATABASE_URL': 'sqlite:///' + database}):
                command.upgrade(Config(str(root / 'alembic.ini')), '0004_organization_sync')
            engine = sa.create_engine('sqlite:///' + database)
            inspector = sa.inspect(engine)
            for name in ('computer_assets', 'computer_network_adapters', 'static_ip_records',
                         'static_ip_history', 'computer_accessories', 'computer_change_history'):
                self.assertTrue(inspector.has_table(name), name)
            with engine.connect() as connection:
                self.assertEqual(connection.execute(sa.text('select version_num from alembic_version')).scalar(),
                                 '0004_organization_sync')
            engine.dispose()

    def test_transfer_preserves_rows_hashes_and_excludes_sessions(self):
        source = make_engine('sqlite:///:memory:')
        target = make_engine('sqlite:///:memory:')
        metadata.create_all(source)
        metadata.create_all(target)
        with tempfile.TemporaryDirectory() as directory:
            with source.begin() as connection:
                seed(connection, directory)
                users = TABLES['users']
                user = connection.execute(sa.select(users.c.id, users.c.created_at).limit(1)).mappings().one()
                sessions = TABLES['user_sessions']
                connection.execute(sessions.insert().values(
                    id='migration-session', user_id=user['id'], token_hash='x' * 64,
                    csrf_hash='y' * 64, auth_version=1, created_at=user['created_at'],
                    last_seen_at=user['created_at'], expires_at=user['created_at'],
                    idle_expires_at=user['created_at'], revoked_at=None,
                ))
            with source.connect() as source_connection:
                summaries = _source_summaries(source_connection, 25)
                with target.begin() as target_connection:
                    _transfer(source_connection, target_connection, summaries, 25)
                    for name, table in TABLES.items():
                        actual = _table_summary(target_connection, table, 25)
                        if name in EXCLUDED_TABLES:
                            self.assertEqual(actual['count'], 0, name)
                        else:
                            self.assertEqual(actual['count'], summaries[name]['count'], name)
                            self.assertEqual(actual['sha256'], summaries[name]['sha256'], name)
        source.dispose()
        target.dispose()


if __name__ == '__main__':
    unittest.main()
