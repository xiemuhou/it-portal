"""Allow static IP records to belong to shared non-computer devices."""
from alembic import op
import sqlalchemy as sa

revision='0007_shared_ip_occupancy'
down_revision='0006_shared_computers'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('static_ip_records',sa.Column('assignment_type',sa.String(32),nullable=False,server_default='personal'))
    op.execute("UPDATE static_ip_records SET assignment_type='shared' WHERE computer_id IN (SELECT id FROM computer_assets WHERE assignment_type='shared')")
    op.alter_column('static_ip_records','assignment_type',server_default=None)

def downgrade():
    op.drop_column('static_ip_records','assignment_type')
