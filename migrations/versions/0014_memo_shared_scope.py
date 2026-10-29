"""Make IT memos shared by the administrator and IT roles."""
from alembic import op
import sqlalchemy as sa

revision='0014_memo_shared_scope'
down_revision='0013_secure_memos'
branch_labels=None
depends_on=None


def upgrade():
    op.drop_index('ix_secure_memos_visibility_archived',table_name='secure_memos')
    op.drop_column('secure_memos','visibility')


def downgrade():
    op.add_column('secure_memos',sa.Column('visibility',sa.String(32),nullable=False,server_default='it'))
    op.create_index('ix_secure_memos_visibility_archived','secure_memos',['visibility','is_archived','updated_at'])
