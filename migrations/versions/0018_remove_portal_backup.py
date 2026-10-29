"""Remove the application-level database backup permission.

Database backup is managed by SQL Server Agent and DBA tooling instead of the
web portal. Historical audit records and existing backup files are preserved.
"""
from datetime import datetime, timezone
import uuid

from alembic import op
import sqlalchemy as sa


revision = '0018_remove_portal_backup'
down_revision = '0017_shared_ip_department'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    meta = sa.MetaData()
    permissions = sa.Table('permissions', meta, autoload_with=bind)
    role_permissions = sa.Table('role_permissions', meta, autoload_with=bind)
    permission_ids = sa.select(permissions.c.id).where(permissions.c.code == 'backup.create')
    bind.execute(role_permissions.delete().where(role_permissions.c.permission_id.in_(permission_ids)))
    bind.execute(permissions.delete().where(permissions.c.code == 'backup.create'))


def downgrade():
    bind = op.get_bind()
    meta = sa.MetaData()
    permissions = sa.Table('permissions', meta, autoload_with=bind)
    role_permissions = sa.Table('role_permissions', meta, autoload_with=bind)
    roles = sa.Table('roles', meta, autoload_with=bind)
    if bind.execute(sa.select(permissions.c.id).where(permissions.c.code == 'backup.create')).scalar():
        return
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    permission_id = str(uuid.uuid4())
    bind.execute(permissions.insert().values(
        id=permission_id, created_at=now, updated_at=now, version=1,
        is_archived=False, code='backup.create', name='backup.create',
        module_code='backup', supports_data_scope=False,
    ))
    admin_role_id = bind.execute(sa.select(roles.c.id).where(roles.c.code == 'admin')).scalar()
    if admin_role_id:
        bind.execute(role_permissions.insert().values(
            id=str(uuid.uuid4()), created_at=now, role_id=admin_role_id,
            permission_id=permission_id, data_scope='none',
        ))
