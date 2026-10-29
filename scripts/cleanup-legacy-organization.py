"""Replace legacy department references with EHR organization records."""
import argparse
import json
import sys
from datetime import date,datetime
from pathlib import Path

import sqlalchemy as sa

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from portal.database import settings,database_url,make_engine,utcnow


def plain(value):
    if isinstance(value,(datetime,date)):return value.isoformat()
    return value


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    engine=make_engine(database_url(settings()));meta=sa.MetaData();meta.reflect(bind=engine)
    t=meta.tables;links=t['organization_external_links'];departments=t['departments'];users=t['users'];ips=t['static_ip_records'];computers=t['computer_assets']
    with engine.begin() as conn:
        ehr_depts=set(conn.execute(sa.select(links.c.local_id).where(links.c.source_code=='ehr',links.c.entity_type=='department')).scalars())
        ehr_users=set(conn.execute(sa.select(links.c.local_id).where(links.c.source_code=='ehr',links.c.entity_type=='user')).scalars())
        replacement=conn.execute(sa.select(links.c.local_id).where(links.c.source_code=='ehr',links.c.entity_type=='department',links.c.external_key=='00074')).scalar_one()
        legacy=set(conn.execute(sa.select(departments.c.id).where(departments.c.id.not_in(ehr_depts))).scalars())
        user_rows=[dict(v) for v in conn.execute(sa.select(users).where(users.c.id.in_(ehr_users),users.c.is_archived==False)).mappings()]
        by_name={}
        for user in user_rows:by_name.setdefault((user['display_name'] or '').strip(),[]).append(user)
        snapshot={name:[{k:('***' if k=='password_hash' else plain(v)) for k,v in row.items()} for row in conn.execute(sa.select(t[name])).mappings()]
                  for name in ('departments','users','computer_assets','static_ip_records','role_permission_departments')}
        target=Path('.tmp')/f"organization-before-cleanup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        target.parent.mkdir(exist_ok=True);target.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf-8')
        report={'snapshot':str(target.resolve()),'legacy_departments':len(legacy),'computers_linked':0,'ips_linked':0,'ips_review':0}
        if not args.apply:
            print(json.dumps(report,ensure_ascii=False,indent=2));return

        # Manual portal accounts keep working under the EHR IT department.
        conn.execute(users.update().where(users.c.department_id.in_(legacy)).values(department_id=replacement,updated_at=utcnow()))
        for computer in conn.execute(sa.select(computers).where(computers.c.is_archived==False)).mappings().all():
            linked=next((v for v in user_rows if v['id']==computer['user_id']),None)
            if not linked:
                matches=by_name.get((computer.get('user_name') or '').strip(),[]);linked=matches[0] if len(matches)==1 else None
            if not linked:raise RuntimeError(f"电脑 {computer['asset_code']} 无法唯一匹配 EHR 人员，已回滚")
            conn.execute(computers.update().where(computers.c.id==computer['id']).values(user_id=linked['id'],department_id=linked['department_id'],user_name=None,updated_at=utcnow()))
            report['computers_linked']+=1
        for record in conn.execute(sa.select(ips).where(ips.c.occupancy_status.in_(('occupied','conflict')))).mappings().all():
            linked=next((v for v in user_rows if v['id']==record['user_id']),None)
            if not linked:
                matches=by_name.get((record.get('user_name') or '').strip(),[]);linked=matches[0] if len(matches)==1 else None
            if linked:
                conn.execute(ips.update().where(ips.c.id==record['id']).values(user_id=linked['id'],department_id=linked['department_id'],user_name=None,updated_at=utcnow()))
                report['ips_linked']+=1
            else:
                old_dept=conn.execute(sa.select(departments.c.name).where(departments.c.id==record['department_id'])).scalar() if record['department_id'] else ''
                legacy_note='历史责任信息：'+('部门='+old_dept+'；' if old_dept else '')+('使用人='+record['user_name'] if record.get('user_name') else '使用人未登记')
                notes=((record.get('notes') or '').rstrip()+'\n'+legacy_note).strip()
                conn.execute(ips.update().where(ips.c.id==record['id']).values(user_id=None,department_id=None,user_name=None,occupancy_status='conflict',verification_status='pending',notes=notes,updated_at=utcnow()))
                report['ips_review']+=1
        permissions=t['role_permission_departments']
        for item in conn.execute(sa.select(permissions).where(permissions.c.department_id.in_(legacy))).mappings().all():
            exists=conn.execute(sa.select(permissions.c.id).where(permissions.c.role_permission_id==item['role_permission_id'],permissions.c.department_id==replacement)).scalar()
            if exists:conn.execute(permissions.delete().where(permissions.c.id==item['id']))
            else:conn.execute(permissions.update().where(permissions.c.id==item['id']).values(department_id=replacement))
        conn.execute(departments.update().where(departments.c.parent_id.in_(legacy)).values(parent_id=None))
        conn.execute(departments.delete().where(departments.c.id.in_(legacy)))
        print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
