"""Organization jobs, external mappings and EHR sync history."""
from alembic import op
import sqlalchemy as sa

revision='0004_organization_sync'
down_revision='0003_computer_lifecycle'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('job_positions',
        sa.Column('id',sa.String(36),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.Column('created_by_user_id',sa.String(36)),sa.Column('updated_by_user_id',sa.String(36)),
        sa.Column('version',sa.Integer(),nullable=False),sa.Column('is_archived',sa.Boolean(),nullable=False),
        sa.Column('department_id',sa.String(36),nullable=False),sa.Column('title',sa.Unicode(160),nullable=False),sa.Column('is_enabled',sa.Boolean(),nullable=False),
        sa.PrimaryKeyConstraint('id',name='pk_job_positions'),sa.UniqueConstraint('department_id','title',name='uq_job_positions_department_title'),
        sa.ForeignKeyConstraint(['created_by_user_id'],['users.id'],name='fk_job_positions_created_by_user_id',ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['updated_by_user_id'],['users.id'],name='fk_job_positions_updated_by_user_id',ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['department_id'],['departments.id'],name='fk_job_positions_department_id',ondelete='NO ACTION'))
    op.create_index('ix_job_positions_department','job_positions',['department_id','is_archived'])

    op.create_table('user_job_assignments',
        sa.Column('id',sa.String(36),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.Column('created_by_user_id',sa.String(36)),sa.Column('updated_by_user_id',sa.String(36)),
        sa.Column('user_id',sa.String(36),nullable=False),sa.Column('position_id',sa.String(36),nullable=False),sa.Column('source_type',sa.String(32),nullable=False),
        sa.PrimaryKeyConstraint('id',name='pk_user_job_assignments'),sa.UniqueConstraint('user_id','position_id',name='uq_user_job_assignments_user_position'),
        sa.ForeignKeyConstraint(['created_by_user_id'],['users.id'],name='fk_user_job_assignments_created_by_user_id',ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['updated_by_user_id'],['users.id'],name='fk_user_job_assignments_updated_by_user_id',ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['user_id'],['users.id'],name='fk_user_job_assignments_user_id',ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['position_id'],['job_positions.id'],name='fk_user_job_assignments_position_id',ondelete='NO ACTION'))
    op.create_index('ix_user_job_assignments_user','user_job_assignments',['user_id'])
    op.create_index('ix_user_job_assignments_position','user_job_assignments',['position_id'])

    op.create_table('organization_external_links',
        sa.Column('id',sa.String(36),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.Column('source_code',sa.String(32),nullable=False),sa.Column('entity_type',sa.String(32),nullable=False),
        sa.Column('external_key',sa.Unicode(256),nullable=False),sa.Column('local_id',sa.String(36),nullable=False),sa.Column('last_seen_at',sa.DateTime(),nullable=False),
        sa.PrimaryKeyConstraint('id',name='pk_organization_external_links'),
        sa.UniqueConstraint('source_code','entity_type','external_key',name='uq_organization_external_links_source_entity_key'))
    op.create_index('ix_organization_external_links_local','organization_external_links',['entity_type','local_id'])

    op.create_table('organization_sync_state',
        sa.Column('source_code',sa.String(32),nullable=False),sa.Column('first_success_at',sa.DateTime()),sa.Column('last_success_at',sa.DateTime()),
        sa.Column('last_attempt_at',sa.DateTime()),sa.Column('last_status',sa.String(32),nullable=False),sa.Column('last_message',sa.Unicode(1000)),
        sa.Column('updated_at',sa.DateTime(),nullable=False),sa.PrimaryKeyConstraint('source_code',name='pk_organization_sync_state'))

    op.create_table('organization_sync_runs',
        sa.Column('id',sa.String(36),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('completed_at',sa.DateTime()),
        sa.Column('source_code',sa.String(32),nullable=False),sa.Column('trigger_type',sa.String(32),nullable=False),sa.Column('trigger_key',sa.String(128),nullable=False),
        sa.Column('actor_user_id',sa.String(36)),sa.Column('status',sa.String(32),nullable=False),sa.Column('message',sa.Unicode(1000)),sa.Column('summary_json',sa.UnicodeText()),
        sa.PrimaryKeyConstraint('id',name='pk_organization_sync_runs'),sa.UniqueConstraint('source_code','trigger_key',name='uq_organization_sync_runs_source_trigger'),
        sa.ForeignKeyConstraint(['actor_user_id'],['users.id'],name='fk_organization_sync_runs_actor_user_id',ondelete='NO ACTION'))
    op.create_index('ix_organization_sync_runs_created','organization_sync_runs',['source_code','created_at'])


def downgrade():
    op.drop_table('organization_sync_runs')
    op.drop_table('organization_sync_state')
    op.drop_table('organization_external_links')
    op.drop_table('user_job_assignments')
    op.drop_table('job_positions')
