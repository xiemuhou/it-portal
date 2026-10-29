"""Apply the reviewed service content explicitly; never runs at app startup.

Run without arguments to preview, or with --apply to save and publish the entries.
Existing entries are matched by name/aliases and backed up before any update.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
import sqlalchemy as sa
from portal import catalog
from portal.database import TABLES as T, settings, database_url, make_engine, jsonable


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    content=json.loads((ROOT/'docs'/'IT服务目录内容.json').read_text(encoding='utf-8'))
    config=settings();engine=make_engine(database_url(config))
    try:
        with engine.begin() as conn:
            admin=dict(conn.execute(sa.select(T['users']).where(T['users'].c.login_name=='admin')).mappings().one())
            existing=conn.execute(sa.select(T['service_catalog'])).mappings().all()
            categories=conn.execute(sa.select(T['ticket_categories']).where(T['ticket_categories'].c.is_enabled==True,T['ticket_categories'].c.is_archived==False)).mappings().all()
            plan=[]
            for index,item in enumerate(content):
                names={item['name'],*item.get('aliases',[])}
                matches=[v for v in existing if v['name'] in names and not v['is_archived']]
                if len(matches)>1:raise RuntimeError('Multiple matching services; review before updating')
                category=[v for v in categories if v['name']==item['category']]
                if len(category)!=1:raise RuntimeError('Missing or ambiguous ticket category; review before updating')
                old=matches[0] if matches else None
                values={k:item[k] for k in ('name','summary','scope_text','submission_guide')}
                values.update(category_id=category[0]['id'],is_published=True,sort_order=index)
                if not old or not old['contact_text']:values['contact_text']='在门户提交工单，并在工单中补充信息、查看进展。'
                if old:values['version']=old['version']
                catalog.validate(conn,admin,'service_catalog',values,old)
                plan.append((old,values))
            if args.apply:
                folder=Path(config['data_dir'])/'service-catalog-backups'
                folder.mkdir(parents=True,exist_ok=True)
                backup=folder/('before-completion-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json')
                with backup.open('x',encoding='utf-8') as output:
                    json.dump(jsonable(existing),output,ensure_ascii=False,indent=2)
                for old,values in plan:
                    catalog.save(conn,admin,'service_catalog',values,old['id'] if old else None)
            print(json.dumps({'mode':'applied' if args.apply else 'preview','services':len(plan),
                              'updates':sum(old is not None for old,_ in plan),
                              'creates':sum(old is None for old,_ in plan),'published':args.apply}))
    finally:engine.dispose()


if __name__=='__main__':main()
