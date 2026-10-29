"""One-time transfer to an INITIALIZED EMPTY SQL database; preserve UUIDs and hashes.

Stop the source application first. This command never clears a target database,
never disables FKs and never migrates sessions or idempotency keys.
"""
from datetime import datetime
from pathlib import Path
import hashlib
import json
import shutil
import sqlite3

import sqlalchemy as sa
from .database import TABLES,metadata,make_engine,database_url,settings,jsonable

EXCLUDED={'user_sessions','idempotency_keys'}


def row_digest(rows,pk):
    values=sorted((jsonable(dict(r)) for r in rows),key=lambda r:r[pk])
    payload=json.dumps(values,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    return hashlib.sha256(payload).hexdigest()


def migrate():
    config=settings();folder=Path(config['data_dir']).resolve();source=folder/'business.db'
    if not source.is_file():raise RuntimeError('Local source database does not exist.')
    target=make_engine(database_url(config))
    if target.dialect.name not in ('mssql','mysql'):raise RuntimeError('Target must be SQL Server or MySQL, not SQLite.')
    inspector=sa.inspect(target)
    if not all(inspector.has_table(n) for n in TABLES):raise RuntimeError('Run Alembic migrations on the empty target first.')
    with target.connect() as conn:
        if any(conn.execute(sa.select(sa.func.count()).select_from(t)).scalar_one() for t in TABLES.values()):
            raise RuntimeError('Target contains data; transfer refused. Nothing was cleared.')
    backup=folder/'migration-backups'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True)
    snapshot=backup/'business-before-transfer.db'
    original=sqlite3.connect(source);saved=sqlite3.connect(snapshot)
    try:
        original.backup(saved)
        if saved.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or saved.execute('PRAGMA foreign_key_check').fetchone():
            raise RuntimeError('Source integrity/FK validation failed.')
    finally:original.close();saved.close()
    for name in ('knowledge','knowledge-assets','attachments'):
        path=folder/name
        if path.exists():shutil.copytree(path,backup/name,symlinks=True)
    source_engine=make_engine('sqlite:///'+snapshot.as_posix())
    contents={};manifest={};deferred=[]
    try:
        with source_engine.connect() as conn:
            for name,table in TABLES.items():
                rows=[dict(r) for r in conn.execute(sa.select(table)).mappings()] if name not in EXCLUDED else []
                if name=='background_jobs':
                    if any(r['job_state'] in ('running','queued') for r in rows):raise RuntimeError('Source has pending background jobs; finish/cancel them before transfer.')
                contents[name]=rows
                manifest[name]={'count':len(rows),'sha256':row_digest(rows,table.primary_key.columns.keys()[0])}
        with target.begin() as conn:
            # Repeat emptiness check inside the transaction. The app stays stopped.
            if any(conn.execute(sa.select(sa.func.count()).select_from(t)).scalar_one() for t in TABLES.values()):
                raise RuntimeError('Target changed during transfer; transaction refused.')
            for table in metadata.sorted_tables:
                name=table.name;pk=table.primary_key.columns.keys()[0]
                for start in range(0,len(contents[name]),100):
                    batch=[]
                    for record in contents[name][start:start+100]:
                        values=dict(record);restore={}
                        # Resolve nullable cycles in two phases without disabling FKs.
                        for column in table.c:
                            if column.foreign_keys and column.nullable and values.get(column.name) is not None:
                                restore[column.name]=values[column.name];values[column.name]=None
                        if restore:deferred.append((name,pk,values[pk],restore))
                        batch.append(values)
                    if batch:conn.execute(table.insert(),batch)
            for name,pk,key,values in deferred:
                conn.execute(TABLES[name].update().where(TABLES[name].c[pk]==key).values(**values))
            for name,table in TABLES.items():
                actual=[dict(r) for r in conn.execute(sa.select(table)).mappings()]
                expected=manifest[name]
                if len(actual)!=expected['count'] or row_digest(actual,table.primary_key.columns.keys()[0])!=expected['sha256']:
                    raise RuntimeError('Row count/content validation failed for '+name+'; transaction rolled back.')
        result={'status':'completed','target_engine':target.dialect.name,'table_count':len(TABLES),
                'nonempty_tables':{n:v['count'] for n,v in manifest.items() if v['count']},
                'excluded':sorted(EXCLUDED),'backup_directory':str(backup),'tables':manifest}
        (backup/'transfer-manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k!='tables'},ensure_ascii=False))
    finally:source_engine.dispose();target.dispose()


if __name__=='__main__':
    try:migrate()
    except sa.exc.DBAPIError as exc:
        # Driver messages can contain business values; never print them or credentials.
        state=exc.orig.args[0] if getattr(exc.orig,'args',None) else 'unknown'
        print(json.dumps({'status':'failed','category':'database_operation','sqlstate':state}))
        raise SystemExit(1)
    except RuntimeError as exc:
        print(json.dumps({'status':'failed','message':str(exc)}));raise SystemExit(1)
