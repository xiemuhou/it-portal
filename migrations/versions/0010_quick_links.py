"""Add administrator-maintained internal quick links."""
from alembic import op
import sqlalchemy as sa

revision='0010_quick_links'
down_revision='0009_announcement_attachments'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('quick_links',
        sa.Column('id',sa.String(36),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.Column('created_by_user_id',sa.String(36),nullable=True),sa.Column('updated_by_user_id',sa.String(36),nullable=True),
        sa.Column('version',sa.Integer(),nullable=False),sa.Column('is_archived',sa.Boolean(),nullable=False),
        sa.Column('title',sa.Unicode(120),nullable=False),sa.Column('url',sa.Unicode(1000),nullable=False),
        sa.Column('icon_text',sa.Unicode(16),nullable=True),sa.Column('description',sa.Unicode(300),nullable=True),
        sa.Column('link_category',sa.String(32),nullable=False),sa.Column('is_enabled',sa.Boolean(),nullable=False),
        sa.Column('sort_order',sa.Integer(),nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'],['users.id'],name='fk_quick_links_created_by_user_id',ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['updated_by_user_id'],['users.id'],name='fk_quick_links_updated_by_user_id',ondelete='NO ACTION'),
        sa.PrimaryKeyConstraint('id',name='pk_quick_links'))
    op.create_index('ix_quick_links_category_enabled','quick_links',['link_category','is_enabled','sort_order'])


def downgrade():
    op.drop_index('ix_quick_links_category_enabled',table_name='quick_links')
    op.drop_table('quick_links')
