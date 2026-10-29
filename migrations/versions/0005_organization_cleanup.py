"""Make positions global and remove their department ownership."""
from alembic import op
import sqlalchemy as sa
import uuid

revision='0005_organization_cleanup'
down_revision='0004_organization_sync'
branch_labels=None
depends_on=None


def upgrade():
    bind=op.get_bind();meta=sa.MetaData()
    positions=sa.Table('job_positions',meta,autoload_with=bind)
    assignments=sa.Table('user_job_assignments',meta,autoload_with=bind)
    links=sa.Table('organization_external_links',meta,autoload_with=bind)
    rows=[dict(v) for v in bind.execute(sa.select(positions).order_by(positions.c.created_at,positions.c.id)).mappings()]
    canonical={};ehr_titles={}
    for item in rows:
        title=(item['title'] or '').strip();key=title.casefold()
        if key not in canonical:
            canonical[key]=item
            if title!=item['title']:bind.execute(positions.update().where(positions.c.id==item['id']).values(title=title))
            continue
        keep=canonical[key];duplicate=item
        for assignment in bind.execute(sa.select(assignments).where(assignments.c.position_id==duplicate['id'])).mappings().all():
            exists=bind.execute(sa.select(assignments.c.id).where(assignments.c.user_id==assignment['user_id'],assignments.c.position_id==keep['id'])).scalar()
            if exists:bind.execute(assignments.delete().where(assignments.c.id==assignment['id']))
            else:bind.execute(assignments.update().where(assignments.c.id==assignment['id']).values(position_id=keep['id']))
        bind.execute(links.update().where(links.c.entity_type=='position',links.c.local_id==duplicate['id']).values(local_id=keep['id']))
        bind.execute(positions.delete().where(positions.c.id==duplicate['id']))
    old_links=bind.execute(sa.select(links).where(links.c.source_code=='ehr',links.c.entity_type=='position')).mappings().all()
    for link in old_links:
        local=bind.execute(sa.select(positions.c.title).where(positions.c.id==link['local_id'])).scalar()
        if local:
            key=local.casefold();current=ehr_titles.get(key)
            if not current or link['last_seen_at']>current[2]:ehr_titles[key]=(local,link['local_id'],link['last_seen_at'],link['created_at'],link['updated_at'])
    bind.execute(links.delete().where(links.c.source_code=='ehr',links.c.entity_type=='position'))
    for title,local_id,last_seen,created,updated in ehr_titles.values():
        bind.execute(links.insert().values(id=str(uuid.uuid4()),created_at=created,updated_at=updated,source_code='ehr',entity_type='position',external_key=title,local_id=local_id,last_seen_at=last_seen))
    # MySQL will not drop an index that is still required by a foreign key.
    # Remove the FK first; SQL Server accepts the same portable order.
    op.drop_constraint('fk_job_positions_department_id','job_positions',type_='foreignkey')
    op.drop_index('ix_job_positions_department',table_name='job_positions')
    op.drop_constraint('uq_job_positions_department_title','job_positions',type_='unique')
    op.drop_column('job_positions','department_id')
    op.create_unique_constraint('uq_job_positions_title','job_positions',['title'])
    op.create_index('ix_job_positions_title','job_positions',['title','is_archived'])


def downgrade():
    op.drop_index('ix_job_positions_title',table_name='job_positions')
    op.drop_constraint('uq_job_positions_title','job_positions',type_='unique')
    op.add_column('job_positions',sa.Column('department_id',sa.String(36),nullable=True))
    op.create_foreign_key('fk_job_positions_department_id','job_positions','departments',['department_id'],['id'],ondelete='NO ACTION')
    op.create_unique_constraint('uq_job_positions_department_title','job_positions',['department_id','title'])
    op.create_index('ix_job_positions_department','job_positions',['department_id','is_archived'])
