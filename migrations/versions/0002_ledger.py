"""Aggregate ledger extension; existing resource IDs and subtype rows are retained."""
from alembic import op
import sqlalchemy as sa

revision='0002_ledger'
down_revision='0001_business'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('ledger_profiles',
        sa.Column('resource_id',sa.String(36),nullable=False),
        sa.Column('data_json',sa.UnicodeText(),nullable=False),
        sa.PrimaryKeyConstraint('resource_id',name='pk_ledger_profiles'),
        sa.ForeignKeyConstraint(['resource_id'],['resources.id'],name='fk_ledger_profiles_resource_id',ondelete='NO ACTION'),mysql_charset='utf8mb4')
    op.create_table('ledger_links',
        sa.Column('id',sa.String(36),nullable=False),
        sa.Column('source_id',sa.String(36),nullable=False),
        sa.Column('target_id',sa.String(36),nullable=False),
        sa.Column('relation',sa.String(32),nullable=False),
        sa.PrimaryKeyConstraint('id',name='pk_ledger_links'),
        sa.ForeignKeyConstraint(['source_id'],['resources.id'],name='fk_ledger_links_source_id',ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['target_id'],['resources.id'],name='fk_ledger_links_target_id',ondelete='NO ACTION'),
        sa.UniqueConstraint('source_id','target_id','relation',name='uq_ledger_links_0'),mysql_charset='utf8mb4')
    op.create_index('ix_ledger_links_0','ledger_links',['target_id'])
    op.create_index('ix_ledger_links_1','ledger_links',['source_id'])


def downgrade():
    op.drop_table('ledger_links')
    op.drop_table('ledger_profiles')
