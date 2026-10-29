"""Add encrypted IT memo records."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql,mysql

revision='0013_secure_memos'
down_revision='0012_consumable_dates'
branch_labels=None
depends_on=None

utc_type=sa.DateTime().with_variant(mssql.DATETIME2(precision=3),'mssql').with_variant(mysql.DATETIME(fsp=3),'mysql')


def upgrade():
    op.create_table('secure_memos',
        sa.Column('id',sa.String(36),nullable=False),sa.Column('created_at',utc_type,nullable=False),sa.Column('updated_at',utc_type,nullable=False),
        sa.Column('created_by_user_id',sa.String(36),nullable=False),sa.Column('updated_by_user_id',sa.String(36),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),sa.Column('is_archived',sa.Boolean(),nullable=False),
        sa.Column('title',sa.Unicode(160),nullable=False),sa.Column('category',sa.String(32),nullable=False),
        sa.Column('system_address',sa.Unicode(1000)),sa.Column('username',sa.Unicode(256)),
        sa.Column('password_ciphertext',sa.UnicodeText()),sa.Column('tags',sa.Unicode(500)),
        sa.Column('visibility',sa.String(32),nullable=False),sa.Column('notes',sa.UnicodeText()),
        sa.PrimaryKeyConstraint('id',name='pk_secure_memos'),
        sa.ForeignKeyConstraint(['created_by_user_id'],['users.id'],name='fk_secure_memos_created_by_user_id',ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['updated_by_user_id'],['users.id'],name='fk_secure_memos_updated_by_user_id',ondelete='NO ACTION'))
    op.create_index('ix_secure_memos_owner_archived','secure_memos',['created_by_user_id','is_archived','updated_at'])
    op.create_index('ix_secure_memos_visibility_archived','secure_memos',['visibility','is_archived','updated_at'])


def downgrade():
    op.drop_index('ix_secure_memos_visibility_archived',table_name='secure_memos')
    op.drop_index('ix_secure_memos_owner_archived',table_name='secure_memos')
    op.drop_table('secure_memos')
