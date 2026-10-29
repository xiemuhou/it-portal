"""Consumable catalog and immutable stock movements."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql,mysql

revision='0011_consumables'
down_revision='0010_quick_links'
branch_labels=None
depends_on=None

utc_type=sa.DateTime().with_variant(mssql.DATETIME2(precision=3),'mssql').with_variant(mysql.DATETIME(fsp=3),'mysql')

def upgrade():
    op.create_table('consumable_items',
        sa.Column('id',sa.String(36),nullable=False),sa.Column('created_at',utc_type,nullable=False),sa.Column('updated_at',utc_type,nullable=False),
        sa.Column('created_by_user_id',sa.String(36),nullable=False),sa.Column('updated_by_user_id',sa.String(36),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),sa.Column('is_archived',sa.Boolean(),nullable=False),
        sa.Column('item_code',sa.Unicode(64),nullable=False),sa.Column('name',sa.Unicode(160),nullable=False),
        sa.Column('category',sa.Unicode(80)),sa.Column('specification',sa.Unicode(200)),sa.Column('unit',sa.Unicode(32),nullable=False),
        sa.Column('minimum_stock',sa.Numeric(18,2),nullable=False),sa.Column('notes',sa.Unicode(1000)),
        sa.PrimaryKeyConstraint('id',name='pk_consumable_items'),sa.UniqueConstraint('item_code',name='uq_consumable_items_code'),
        sa.ForeignKeyConstraint(['created_by_user_id'],['users.id'],name='fk_consumable_items_created_by_user_id',ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['updated_by_user_id'],['users.id'],name='fk_consumable_items_updated_by_user_id',ondelete='NO ACTION'))
    op.create_index('ix_consumable_items_name','consumable_items',['name','is_archived'])
    op.create_table('consumable_movements',
        sa.Column('id',sa.String(36),nullable=False),sa.Column('created_at',utc_type,nullable=False),
        sa.Column('actor_user_id',sa.String(36),nullable=False),sa.Column('item_id',sa.String(36),nullable=False),
        sa.Column('movement_type',sa.String(32),nullable=False),sa.Column('quantity',sa.Numeric(18,2),nullable=False),
        sa.Column('occurred_on',sa.Date(),nullable=False),sa.Column('unit_cost',sa.Numeric(18,2)),sa.Column('supplier',sa.Unicode(160)),
        sa.Column('reference_no',sa.Unicode(128)),sa.Column('computer_id',sa.String(36)),sa.Column('department_id',sa.String(36)),
        sa.Column('user_id',sa.String(36)),sa.Column('recipient_text',sa.Unicode(160)),sa.Column('purpose',sa.Unicode(300)),
        sa.Column('notes',sa.Unicode(1000)),sa.Column('item_name_snapshot',sa.Unicode(160),nullable=False),sa.Column('unit_snapshot',sa.Unicode(32),nullable=False),
        sa.PrimaryKeyConstraint('id',name='pk_consumable_movements'),
        sa.ForeignKeyConstraint(['actor_user_id'],['users.id'],name='fk_consumable_movements_actor_user_id',ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['item_id'],['consumable_items.id'],name='fk_consumable_movements_item_id',ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['computer_id'],['computer_assets.id'],name='fk_consumable_movements_computer_id',ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['department_id'],['departments.id'],name='fk_consumable_movements_department_id',ondelete='NO ACTION'),
        sa.ForeignKeyConstraint(['user_id'],['users.id'],name='fk_consumable_movements_user_id',ondelete='NO ACTION'))
    op.create_index('ix_consumable_movements_item_date','consumable_movements',['item_id','occurred_on'])
    op.create_index('ix_consumable_movements_computer','consumable_movements',['computer_id','occurred_on'])
    op.create_index('ix_consumable_movements_department','consumable_movements',['department_id','occurred_on'])

def downgrade():
    op.drop_table('consumable_movements')
    op.drop_table('consumable_items')

