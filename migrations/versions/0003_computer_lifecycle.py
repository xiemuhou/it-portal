"""Computer accessories and auditable lifecycle history."""
from alembic import op
import sqlalchemy as sa

revision='0003_computer_lifecycle'
down_revision='0002_ipam_base'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('computer_accessories',
        sa.Column('id',sa.String(36),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.Column('computer_id',sa.String(36),nullable=False),sa.Column('accessory_type',sa.Unicode(64),nullable=False),
        sa.Column('brand_model',sa.Unicode(160)),sa.Column('serial_number',sa.Unicode(160)),sa.Column('notes',sa.Unicode(512)),
        sa.PrimaryKeyConstraint('id',name='pk_computer_accessories'),sa.ForeignKeyConstraint(['computer_id'],['computer_assets.id'],name='fk_computer_accessories_computer_id',ondelete='NO ACTION'))
    op.create_index('ix_computer_accessories_computer','computer_accessories',['computer_id'])
    op.create_table('computer_change_history',
        sa.Column('id',sa.String(36),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('computer_id',sa.String(36),nullable=False),
        sa.Column('actor_user_id',sa.String(36),nullable=False),sa.Column('action_code',sa.String(32),nullable=False),
        sa.Column('change_summary',sa.Unicode(1000),nullable=False),sa.Column('snapshot_json',sa.UnicodeText(),nullable=False),
        sa.PrimaryKeyConstraint('id',name='pk_computer_change_history'),sa.ForeignKeyConstraint(['computer_id'],['computer_assets.id'],name='fk_computer_change_history_computer_id',ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['actor_user_id'],['users.id'],name='fk_computer_change_history_actor_user_id',ondelete='NO ACTION'))
    op.create_index('ix_computer_change_history_computer','computer_change_history',['computer_id','created_at'])

def downgrade():
    op.drop_table('computer_change_history');op.drop_table('computer_accessories')
