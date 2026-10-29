"""Align consumable timestamps with the portal UTC timestamp type."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql,mysql

revision='0012_consumable_dates'
down_revision='0011_consumables'
branch_labels=None
depends_on=None

utc_type=sa.DateTime().with_variant(mssql.DATETIME2(precision=3),'mssql').with_variant(mysql.DATETIME(fsp=3),'mysql')


def upgrade():
    if op.get_bind().dialect.name=='sqlite':
        return
    op.alter_column('consumable_items','created_at',existing_type=sa.DateTime(),type_=utc_type,existing_nullable=False)
    op.alter_column('consumable_items','updated_at',existing_type=sa.DateTime(),type_=utc_type,existing_nullable=False)
    op.alter_column('consumable_movements','created_at',existing_type=sa.DateTime(),type_=utc_type,existing_nullable=False)


def downgrade():
    if op.get_bind().dialect.name=='sqlite':
        return
    op.alter_column('consumable_movements','created_at',existing_type=utc_type,type_=sa.DateTime(),existing_nullable=False)
    op.alter_column('consumable_items','updated_at',existing_type=utc_type,type_=sa.DateTime(),existing_nullable=False)
    op.alter_column('consumable_items','created_at',existing_type=utc_type,type_=sa.DateTime(),existing_nullable=False)
