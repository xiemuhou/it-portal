"""Track successful knowledge article opens."""
from alembic import op
import sqlalchemy as sa

revision='0008_knowledge_view_count'
down_revision='0007_shared_ip_occupancy'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('knowledge_articles',sa.Column('view_count',sa.BigInteger(),nullable=False,server_default='0'))
    op.alter_column('knowledge_articles','view_count',server_default=None)


def downgrade():
    op.drop_column('knowledge_articles','view_count')
