"""Add traceable consumable returns and inbound reversals."""
from alembic import op
import sqlalchemy as sa


revision='0016_consumable_reversals'
down_revision='0015_computer_acceptance'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('consumable_movements',sa.Column('is_reversed',sa.Boolean(),nullable=False,server_default=sa.false()))
    op.add_column('consumable_movements',sa.Column('reversal_of_id',sa.String(36),nullable=True))
    op.create_foreign_key('fk_consumable_movements_reversal_of_id','consumable_movements','consumable_movements',['reversal_of_id'],['id'],ondelete='NO ACTION')
    op.create_index('ix_consumable_movements_reversal','consumable_movements',['reversal_of_id'])
    op.alter_column('consumable_movements','is_reversed',server_default=None)


def downgrade():
    op.drop_index('ix_consumable_movements_reversal',table_name='consumable_movements')
    op.drop_constraint('fk_consumable_movements_reversal_of_id','consumable_movements',type_='foreignkey')
    op.drop_column('consumable_movements','reversal_of_id')
    op.drop_column('consumable_movements','is_reversed')
