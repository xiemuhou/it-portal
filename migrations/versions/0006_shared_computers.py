"""Allow computers to be registered as shared assets."""
from alembic import op
import sqlalchemy as sa

revision='0006_shared_computers'
down_revision='0005_organization_cleanup'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('computer_assets',sa.Column('assignment_type',sa.String(32),nullable=False,server_default='personal'))
    op.alter_column('computer_assets','assignment_type',server_default=None)

def downgrade():
    op.drop_column('computer_assets','assignment_type')
