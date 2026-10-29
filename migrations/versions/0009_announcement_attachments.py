"""Enable announcement attachments, announcement notifications, and remove announcement summaries."""
from alembic import op
import sqlalchemy as sa

revision='0009_announcement_attachments'
down_revision='0008_knowledge_view_count'
branch_labels=None
depends_on=None


def upgrade():
    op.drop_column('announcements','summary')
    op.add_column('notifications',sa.Column('announcement_id',sa.String(36),nullable=True))
    op.create_foreign_key('fk_notifications_announcement_id','notifications','announcements',['announcement_id'],['id'],ondelete='NO ACTION')
    op.create_table('announcement_files',
        sa.Column('id',sa.String(36),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('created_by_user_id',sa.String(36),nullable=True),
        sa.Column('announcement_id',sa.String(36),nullable=False),
        sa.Column('file_id',sa.String(36),nullable=False),
        sa.Column('label',sa.Unicode(128),nullable=True),
        sa.ForeignKeyConstraint(['announcement_id'],['announcements.id'],name='fk_announcement_files_announcement_id',ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['created_by_user_id'],['users.id'],name='fk_announcement_files_created_by_user_id',ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['file_id'],['file_objects.id'],name='fk_announcement_files_file_id',ondelete='NO ACTION'),
        sa.PrimaryKeyConstraint('id',name='pk_announcement_files'),
        sa.UniqueConstraint('file_id',name='uq_announcement_files_0'))
    op.create_index('ix_announcement_files_0','announcement_files',['announcement_id'])


def downgrade():
    op.drop_index('ix_announcement_files_0',table_name='announcement_files')
    op.drop_table('announcement_files')
    op.drop_constraint('fk_notifications_announcement_id','notifications',type_='foreignkey')
    op.drop_column('notifications','announcement_id')
    op.add_column('announcements',sa.Column('summary',sa.Unicode(512),nullable=True))
