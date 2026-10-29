"""Keep an independent management department on shared IP assignments."""
from alembic import op
import sqlalchemy as sa


revision='0017_shared_ip_department'
down_revision='0016_consumable_reversals'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('static_ip_records',sa.Column('department_name_snapshot',sa.Unicode(128),nullable=True))


def downgrade():
    op.drop_column('static_ip_records','department_name_snapshot')
