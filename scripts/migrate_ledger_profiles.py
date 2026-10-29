"""Backfill aggregate profiles without changing existing resource IDs or subtype rows."""
from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import sqlalchemy as sa
from portal.database import settings,database_url,make_engine,TABLES as T,insert_row,jsonable
from portal import ledger as L
from portal.security import audit

engine=make_engine(database_url(settings()));count=0
with engine.begin() as conn:
    admin=dict(conn.execute(sa.select(T['users']).where(T['users'].c.login_name=='admin')).mappings().one())
    resources=conn.execute(sa.select(T['resources']).where(T['resources'].c.resource_kind.in_(list(L.KINDS)),T['resources'].c.is_archived==False)).mappings().all()
    for resource in resources:
        if L.row(conn,'ledger_profiles',resource['id']):continue
        old=L.detail(conn,admin,resource['id'],False);kind=resource['resource_kind']
        data=L.clean(conn,admin,kind,{f['name']:old.get(f['name']) for f in L.schema(kind)},old)
        insert_row(conn,'ledger_profiles',{'resource_id':resource['id'],'data_json':json.dumps(jsonable(data),ensure_ascii=False)})
        for field,target,_ in L.references(data,kind):insert_row(conn,'ledger_links',{'source_id':resource['id'],'target_id':target,'relation':field})
        audit(conn,admin,'resource.ledger_migrated','resources',resource['id'],{'preserved_id':True});count+=1
engine.dispose();print('Profiles migrated without changing original records:',count)
