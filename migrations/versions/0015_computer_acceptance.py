"""Add month-precision computer acceptance date."""
from alembic import op
import sqlalchemy as sa

revision='0015_computer_acceptance'
down_revision='0014_memo_shared_scope'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('computer_assets',sa.Column('acceptance_month',sa.Date(),nullable=True))


def downgrade():
    op.drop_column('computer_assets','acceptance_month')
