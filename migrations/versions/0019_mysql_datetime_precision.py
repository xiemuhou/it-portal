"""Preserve milliseconds in MySQL tables created by early feature revisions.

SQL Server returned millisecond-bearing ``datetime`` values while the original
MySQL DDL used plain ``DATETIME`` (fsp=0).  Imports therefore lost the
fractional part and correctly failed the row-digest verification.  This target
repair is a no-op on SQL Server and retains existing values on MySQL.
"""
from alembic import op
from sqlalchemy.dialects import mysql


revision = '0019_mysql_datetime_precision'
down_revision = '0018_remove_portal_backup'
branch_labels = None
depends_on = None


COLUMNS = {
    'computer_assets': {'created_at': False, 'updated_at': False},
    'computer_network_adapters': {'created_at': False, 'updated_at': False},
    'static_ip_records': {'created_at': False, 'updated_at': False, 'verified_at': True},
    'static_ip_history': {'created_at': False},
    'computer_accessories': {'created_at': False, 'updated_at': False},
    'computer_change_history': {'created_at': False},
    'job_positions': {'created_at': False, 'updated_at': False},
    'user_job_assignments': {'created_at': False, 'updated_at': False},
    'organization_external_links': {'created_at': False, 'updated_at': False, 'last_seen_at': False},
    'organization_sync_state': {
        'first_success_at': True, 'last_success_at': True, 'last_attempt_at': True, 'updated_at': False,
    },
    'organization_sync_runs': {'created_at': False, 'completed_at': True},
    'announcement_files': {'created_at': False},
    'quick_links': {'created_at': False, 'updated_at': False},
}


def upgrade():
    if op.get_bind().dialect.name != 'mysql':
        return
    for table_name, columns in COLUMNS.items():
        for column_name, nullable in columns.items():
            op.alter_column(
                table_name,
                column_name,
                existing_type=mysql.DATETIME(),
                type_=mysql.DATETIME(fsp=3),
                existing_nullable=nullable,
            )


def downgrade():
    if op.get_bind().dialect.name == 'mysql':
        raise RuntimeError('Downgrade would discard timestamp milliseconds; restore a verified backup instead.')
