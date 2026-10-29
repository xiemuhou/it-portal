"""Create the computer and static-IP base tables used by later revisions.

These tables originally came from application-level ``metadata.create_all``.
That happened to work on established SQL Server installations, but a fresh
Alembic-only MySQL deployment reaches revision 0003 before the referenced
``computer_assets`` table exists.  Insert this revision into the historical
chain so a new database is complete without starting the application first.
"""
from alembic import op
import sqlalchemy as sa


revision = '0002_ipam_base'
down_revision = '0002_ledger'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('computer_assets',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('created_by_user_id', sa.String(36), nullable=False),
        sa.Column('updated_by_user_id', sa.String(36), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('is_archived', sa.Boolean(), nullable=False),
        sa.Column('asset_code', sa.Unicode(64), nullable=False),
        sa.Column('device_name', sa.Unicode(160), nullable=False),
        sa.Column('device_type', sa.Unicode(64), nullable=False),
        sa.Column('brand', sa.Unicode(128)),
        sa.Column('model', sa.Unicode(160)),
        sa.Column('serial_number', sa.Unicode(160)),
        sa.Column('site_id', sa.String(36), nullable=False),
        sa.Column('department_id', sa.String(36)),
        sa.Column('user_id', sa.String(36)),
        sa.Column('user_name', sa.Unicode(128)),
        sa.Column('location', sa.Unicode(256)),
        sa.Column('operating_system', sa.Unicode(160)),
        sa.Column('asset_status', sa.String(32), nullable=False),
        sa.Column('notes', sa.UnicodeText()),
        sa.PrimaryKeyConstraint('id', name='pk_computer_assets'),
        sa.UniqueConstraint('asset_code', name='uq_computer_assets_asset_code'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name='fk_computer_assets_created_by_user_id', ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name='fk_computer_assets_updated_by_user_id', ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['site_id'], ['sites.id'], name='fk_computer_assets_site_id', ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], name='fk_computer_assets_department_id', ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_computer_assets_user_id', ondelete='NO ACTION'),
        mysql_charset='utf8mb4')
    op.create_index('ix_computer_assets_site_archived', 'computer_assets', ['site_id', 'is_archived'])
    op.create_index('ix_computer_assets_user', 'computer_assets', ['user_id'])

    op.create_table('computer_network_adapters',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('computer_id', sa.String(36), nullable=False),
        sa.Column('adapter_name', sa.Unicode(128), nullable=False),
        sa.Column('adapter_type', sa.String(32), nullable=False),
        sa.Column('mac_address', sa.String(17), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('notes', sa.Unicode(512)),
        sa.PrimaryKeyConstraint('id', name='pk_computer_network_adapters'),
        sa.UniqueConstraint('mac_address', name='uq_computer_network_adapters_mac'),
        sa.ForeignKeyConstraint(['computer_id'], ['computer_assets.id'], name='fk_computer_network_adapters_computer_id', ondelete='NO ACTION'),
        mysql_charset='utf8mb4')
    op.create_index('ix_computer_network_adapters_computer', 'computer_network_adapters', ['computer_id'])

    op.create_table('static_ip_records',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('created_by_user_id', sa.String(36), nullable=False),
        sa.Column('updated_by_user_id', sa.String(36), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('vlan_id', sa.String(36), nullable=False),
        sa.Column('network_id', sa.String(36), nullable=False),
        sa.Column('ip_address', sa.String(45), nullable=False),
        sa.Column('occupancy_status', sa.String(32), nullable=False),
        sa.Column('verification_status', sa.String(32), nullable=False),
        sa.Column('department_id', sa.String(36)),
        sa.Column('user_id', sa.String(36)),
        sa.Column('user_name', sa.Unicode(128)),
        sa.Column('device_type', sa.Unicode(64)),
        sa.Column('computer_id', sa.String(36)),
        sa.Column('adapter_id', sa.String(36)),
        sa.Column('mac_address', sa.String(17)),
        sa.Column('location', sa.Unicode(256)),
        sa.Column('notes', sa.UnicodeText()),
        sa.Column('verified_at', sa.DateTime()),
        sa.Column('verified_by_user_id', sa.String(36)),
        sa.PrimaryKeyConstraint('id', name='pk_static_ip_records'),
        sa.UniqueConstraint('vlan_id', 'network_id', 'ip_address', name='uq_static_ip_records_address'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name='fk_static_ip_records_created_by_user_id', ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name='fk_static_ip_records_updated_by_user_id', ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['vlan_id'], ['resources.id'], name='fk_static_ip_records_vlan_id', ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], name='fk_static_ip_records_department_id', ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_static_ip_records_user_id', ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['computer_id'], ['computer_assets.id'], name='fk_static_ip_records_computer_id', ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['adapter_id'], ['computer_network_adapters.id'], name='fk_static_ip_records_adapter_id', ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['verified_by_user_id'], ['users.id'], name='fk_static_ip_records_verified_by_user_id', ondelete='NO ACTION'),
        mysql_charset='utf8mb4')
    op.create_index('ix_static_ip_records_network', 'static_ip_records', ['vlan_id', 'network_id'])
    op.create_index('ix_static_ip_records_computer', 'static_ip_records', ['computer_id'])
    op.create_index('ix_static_ip_records_mac', 'static_ip_records', ['mac_address'])

    op.create_table('static_ip_history',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('ip_record_id', sa.String(36), nullable=False),
        sa.Column('actor_user_id', sa.String(36), nullable=False),
        sa.Column('action_code', sa.String(32), nullable=False),
        sa.Column('snapshot_json', sa.UnicodeText(), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_static_ip_history'),
        sa.ForeignKeyConstraint(['ip_record_id'], ['static_ip_records.id'], name='fk_static_ip_history_ip_record_id', ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name='fk_static_ip_history_actor_user_id', ondelete='NO ACTION'),
        mysql_charset='utf8mb4')
    op.create_index('ix_static_ip_history_record', 'static_ip_history', ['ip_record_id', 'created_at'])


def downgrade():
    op.drop_table('static_ip_history')
    op.drop_table('static_ip_records')
    op.drop_table('computer_network_adapters')
    op.drop_table('computer_assets')
