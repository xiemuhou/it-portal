"""Portal-owned organization directory and read-only EHR synchronization."""
from datetime import datetime
import json
import re
import uuid

import sqlalchemy as sa
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError, IntegrityError

from .database import TABLES as T, insert_row, row, utcnow
from .security import audit, fail, password_hash, require
from .tickets import text

SOURCE='ehr'
ALLOWED_VIEWS=('dbo.V_Employee','dbo.V_Department','dbo.V_Employee_JOB')
EHR_QUERIES={
    'departments': "SELECT ParentCode AS parent_code, Code AS department_code, Name AS department_name FROM dbo.V_Department WHERE OrgCode = :org_code",
    'employees': "SELECT stuffCode AS employee_code, FullName AS full_name, DepartmentCode AS department_code, DimissionDate AS dimission_date FROM dbo.V_Employee",
    'jobs': "SELECT stuffCode AS employee_code, DepartmentCode AS department_code, JobTitle AS job_title FROM dbo.V_Employee_JOB",
}


def _clean(value,limit=256):
    if value is None:return ''
    return str(value).strip()[:limit]


def _external_url(config):
    source=config.get('ehr_database') or {}
    if not source.get('enabled',False):
        raise RuntimeError('尚未配置 EHR 只读数据库连接')
    if source.get('engine','mssql')!='mssql':
        raise RuntimeError('EHR 数据源目前仅支持 SQL Server')
    return URL.create('mssql+pyodbc',username=source.get('username'),password=source.get('password'),
        host=source['host'],port=int(source.get('port',1433)),database=source.get('name','EHR_DATABASE'),
        query={'driver':source.get('driver','ODBC Driver 17 for SQL Server'),'Encrypt':'yes',
               'TrustServerCertificate':'yes' if source.get('trust_server_certificate',False) else 'no',
               'ApplicationIntent':'ReadOnly'})


def read_ehr(config):
    """Execute only the three fixed SELECT statements; no caller-supplied SQL."""
    engine=sa.create_engine(_external_url(config),pool_pre_ping=True,hide_parameters=True)
    @sa.event.listens_for(engine,'before_cursor_execute')
    def select_only(_conn,_cursor,statement,_parameters,_context,_many):
        if not statement.lstrip().upper().startswith(('SELECT','WITH')):
            raise PermissionError('EHR 连接只允许执行 SELECT')
    try:
        with engine.connect() as conn:
            result={}
            for name,sql in EHR_QUERIES.items():
                parameters={'org_code':str(config.get('ehr_org_code','ORG_ROOT'))} if name=='departments' else {}
                result[name]=[dict(v) for v in conn.execute(sa.text(sql),parameters).mappings()]
            return result
    finally:
        engine.dispose()


def _link(conn,entity_type,external_key,local_id,now):
    t=T['organization_external_links']
    old=conn.execute(sa.select(t).where(t.c.source_code==SOURCE,t.c.entity_type==entity_type,t.c.external_key==external_key)).mappings().first()
    values={'local_id':local_id,'last_seen_at':now,'updated_at':now}
    if old:conn.execute(t.update().where(t.c.id==old['id']).values(**values))
    else:insert_row(conn,'organization_external_links',{'source_code':SOURCE,'entity_type':entity_type,'external_key':external_key,'local_id':local_id,'last_seen_at':now})


def _linked_id(conn,entity_type,external_key):
    t=T['organization_external_links']
    return conn.execute(sa.select(t.c.local_id).where(t.c.source_code==SOURCE,t.c.entity_type==entity_type,t.c.external_key==external_key)).scalar()


def _dedupe(rows,key,errors,label):
    result={}
    for item in rows:
        k=key(item)
        if not k:
            errors.append(f'{label}存在缺少关键字段的记录')
        elif k in result:
            errors.append(f'{label}关键值重复：{k}')
        else:result[k]=item
    return result


def _apply(conn,data,actor_id=None):
    now=utcnow();state=T['organization_sync_state']
    sync_state=conn.execute(sa.select(state).where(state.c.source_code==SOURCE)).mappings().first()
    first_sync=not sync_state or not sync_state['first_success_at']
    errors=[];counts={'departments_created':0,'departments_updated':0,'users_created':0,'users_updated':0,
                      'users_disabled':0,'employees_outside_scope':0,'positions_created':0,'positions_updated':0,'assignments':0,'errors':0}

    departments=_dedupe(data['departments'],lambda r:_clean(r.get('department_code'),64),errors,'部门')
    department_ids={}
    dt=T['departments']
    for code,item in departments.items():
        name=_clean(item.get('department_name'),128)
        if not name:errors.append(f'部门 {code} 缺少名称');continue
        local_id=_linked_id(conn,'department',code)
        old=row(conn,'departments',local_id) if local_id else conn.execute(sa.select(dt).where(dt.c.code==code)).mappings().first()
        if old:
            values={'name':name,'is_enabled':True,'is_archived':False,'archived_at':None,'archived_by_user_id':None,
                    'updated_at':now,'updated_by_user_id':actor_id,'version':old['version']+1}
            conn.execute(dt.update().where(dt.c.id==old['id']).values(**values));local_id=old['id'];counts['departments_updated']+=1
        else:
            local_id=insert_row(conn,'departments',{'code':code,'name':name,'parent_id':None,'is_enabled':True},actor_id)['id'];counts['departments_created']+=1
        department_ids[code]=local_id;_link(conn,'department',code,local_id,now)
    for code,item in departments.items():
        if code not in department_ids:continue
        parent_code=_clean(item.get('parent_code'),64)
        parent_id=department_ids.get(parent_code)
        conn.execute(dt.update().where(dt.c.id==department_ids[code]).values(parent_id=parent_id))

    employees=_dedupe(data['employees'],lambda r:_clean(r.get('employee_code'),128).lower(),errors,'员工')
    users=T['users'];employee_role=conn.execute(sa.select(T['roles'].c.id).where(T['roles'].c.code=='employee',T['roles'].c.is_archived==False)).scalar()
    user_ids={}
    for login,item in employees.items():
        raw_code=_clean(item.get('employee_code'),64);name=_clean(item.get('full_name'),128);dept_code=_clean(item.get('department_code'),64)
        if not name or not dept_code:errors.append(f'员工 {raw_code or login} 缺少姓名或部门编号');continue
        department_id=department_ids.get(dept_code)
        if not department_id:counts['employees_outside_scope']+=1;continue
        if not re.fullmatch(r'[a-z0-9][a-z0-9_.@-]{0,127}',login):errors.append(f'员工工号 {raw_code} 不能作为系统登录名');continue
        if len(raw_code)<8 or len(raw_code)>256:errors.append(f'员工 {raw_code} 的工号不符合 8～256 位初始密码策略');continue
        local_id=_linked_id(conn,'user',raw_code)
        old=row(conn,'users',local_id) if local_id else conn.execute(sa.select(users).where(sa.or_(users.c.employee_no==raw_code,users.c.login_name==login))).mappings().first()
        departed=item.get('dimission_date') is not None and str(item.get('dimission_date')).strip()!=''
        if old:
            collision=conn.execute(sa.select(users.c.id).where(users.c.login_name==login,users.c.id!=old['id'])).first()
            if collision:errors.append(f'员工 {raw_code} 的工号登录名已被其他账号使用');continue
            values={'login_name':login,'display_name':name,'employee_no':raw_code,'department_id':department_id,'is_archived':False,
                    'archived_at':None,'archived_by_user_id':None,'updated_at':now,'updated_by_user_id':actor_id,'version':old['version']+1}
            if first_sync:
                values.update(password_hash=password_hash(raw_code),account_state='disabled' if departed else 'active',auth_version=old['auth_version']+1)
            elif departed and old['account_state']!='disabled':
                values.update(account_state='disabled',auth_version=old['auth_version']+1);counts['users_disabled']+=1
            conn.execute(users.update().where(users.c.id==old['id']).values(**values));local_id=old['id'];counts['users_updated']+=1
        else:
            local_id=insert_row(conn,'users',{'login_name':login,'display_name':name,'employee_no':raw_code,'department_id':department_id,
                'password_hash':password_hash(raw_code),'account_state':'disabled' if (departed or not first_sync) else 'active','auth_version':1},actor_id)['id']
            if employee_role:insert_row(conn,'user_roles',{'user_id':local_id,'role_id':employee_role},actor_id)
            counts['users_created']+=1
        user_ids[raw_code]=local_id;_link(conn,'user',raw_code,local_id,now)

    jobs=[];seen=set();positions={};pt=T['job_positions']
    for item in data['jobs']:
        employee_code=_clean(item.get('employee_code'),64);dept_code=_clean(item.get('department_code'),64);job_title=_clean(item.get('job_title'),160)
        if not employee_code or not dept_code or not job_title:continue
        signature=(employee_code,job_title)
        if signature in seen:continue
        seen.add(signature);user_id=user_ids.get(employee_code)
        if dept_code not in department_ids:continue
        key=job_title;local_id=positions.get(key)
        if not local_id:
            local_id=_linked_id(conn,'position',key)
            old=row(conn,'job_positions',local_id) if local_id else conn.execute(sa.select(pt).where(pt.c.title==job_title)).mappings().first()
            if old:
                conn.execute(pt.update().where(pt.c.id==old['id']).values(title=job_title,is_enabled=True,is_archived=False,
                    updated_at=now,updated_by_user_id=actor_id,version=old['version']+1));local_id=old['id'];counts['positions_updated']+=1
            else:
                local_id=insert_row(conn,'job_positions',{'title':job_title,'is_enabled':True},actor_id)['id'];counts['positions_created']+=1
            positions[key]=local_id;_link(conn,'position',key,local_id,now)
        if user_id:jobs.append((user_id,local_id))
    assignments=T['user_job_assignments']
    if user_ids:
        conn.execute(assignments.delete().where(assignments.c.source_type==SOURCE,assignments.c.user_id.in_(list(user_ids.values()))))
    for user_id,position_id in jobs:
        exists=conn.execute(sa.select(assignments.c.id).where(assignments.c.user_id==user_id,assignments.c.position_id==position_id)).first()
        if not exists:insert_row(conn,'user_job_assignments',{'user_id':user_id,'position_id':position_id,'source_type':SOURCE},actor_id)
        counts['assignments']+=1
    counts['errors']=len(errors)
    message=f"同步完成：部门 {len(department_ids)}、人员 {len(user_ids)}、岗位 {len(positions)}、任职 {counts['assignments']}"
    if errors:message+=f"；{len(errors)} 条数据提示"
    values={'first_success_at':sync_state['first_success_at'] if sync_state and sync_state['first_success_at'] else now,
            'last_success_at':now,'last_attempt_at':now,'last_status':'partial' if errors else 'success','last_message':message,'updated_at':now}
    if sync_state:conn.execute(state.update().where(state.c.source_code==SOURCE).values(**values))
    else:conn.execute(state.insert().values(source_code=SOURCE,**values))
    return {'message':message,'counts':counts,'errors':errors[:100],'first_sync':first_sync}


def sync_ehr(portal_engine,config,trigger_type='manual',actor=None,trigger_key=None):
    trigger_key=trigger_key or f'manual:{uuid.uuid4()}'
    run_id=str(uuid.uuid4());now=utcnow();runs=T['organization_sync_runs'];state=T['organization_sync_state']
    try:
        with portal_engine.begin() as conn:
            conn.execute(runs.insert().values(id=run_id,created_at=now,source_code=SOURCE,trigger_type=trigger_type,trigger_key=trigger_key,
                actor_user_id=actor['id'] if actor else None,status='running'))
            current=conn.execute(sa.select(state).where(state.c.source_code==SOURCE)).mappings().first()
            values={'last_attempt_at':now,'last_status':'running','last_message':'正在读取 EHR 只读视图','updated_at':now}
            if current:conn.execute(state.update().where(state.c.source_code==SOURCE).values(**values))
            else:conn.execute(state.insert().values(source_code=SOURCE,**values))
    except IntegrityError:
        return {'skipped':True,'message':'该时段同步任务已由另一个进程执行'}
    try:
        data=read_ehr(config)
        with portal_engine.begin() as conn:
            result=_apply(conn,data,actor['id'] if actor else None)
            conn.execute(runs.update().where(runs.c.id==run_id).values(completed_at=utcnow(),status='partial' if result['errors'] else 'success',
                message=result['message'],summary_json=json.dumps(result,ensure_ascii=False,default=str)))
            audit(conn,actor,'organization.sync.ehr','organization_sync_runs',run_id,result['counts'])
        return result
    except Exception as exc:
        message='EHR 同步失败：数据库连接不可用，或只读账号没有 EHR 数据库及指定视图的 SELECT 权限' if isinstance(exc,DBAPIError) else 'EHR 同步失败：'+str(exc)[:850]
        with portal_engine.begin() as conn:
            conn.execute(runs.update().where(runs.c.id==run_id).values(completed_at=utcnow(),status='error',message=message))
            conn.execute(state.update().where(state.c.source_code==SOURCE).values(last_attempt_at=utcnow(),last_status='error',last_message=message,updated_at=utcnow()))
        raise RuntimeError(message) from exc


def assign_positions(conn,actor,user_id,position_ids,source_type='manual'):
    if not isinstance(position_ids,list) or len(position_ids)!=len(set(position_ids)):fail('岗位选择无效或重复')
    table=T['user_job_assignments'];positions=T['job_positions']
    for key in position_ids:
        item=row(conn,'job_positions',key)
        if not item or item['is_archived'] or not item['is_enabled']:fail('岗位不存在或已停用')
    conn.execute(table.delete().where(table.c.user_id==user_id,table.c.source_type=='manual'))
    existing={r[0] for r in conn.execute(sa.select(table.c.position_id).where(table.c.user_id==user_id))}
    for key in position_ids:
        if key not in existing:insert_row(conn,'user_job_assignments',{'user_id':user_id,'position_id':key,'source_type':source_type},actor['id'])


def position_list(conn,q='',page=1,page_size=10):
    t=T['job_positions'];links=T['organization_external_links']
    query=sa.select(t).where(t.c.is_archived==False)
    if q:query=query.where(t.c.title.contains(q,autoescape=True))
    count=conn.execute(sa.select(sa.func.count()).select_from(query.subquery())).scalar_one()
    items=[dict(v) for v in conn.execute(query.order_by(t.c.title).offset((max(1,page)-1)*page_size).limit(page_size)).mappings()]
    keys=[v['id'] for v in items];linked={}
    if keys:
        for local_id,source_code in conn.execute(sa.select(links.c.local_id,links.c.source_code).where(
            links.c.entity_type=='position',links.c.source_code.in_(('ehr','ldap')),links.c.local_id.in_(keys))):
            linked.setdefault(local_id,set()).add(source_code)
    for item in items:
        sources=linked.get(item['id'],set());item['source_type']='ehr' if 'ehr' in sources else 'ldap' if 'ldap' in sources else 'manual'
    return {'items':items,'total':count,'page':max(1,page),'page_size':page_size}


def save_position(conn,actor,body,key=None):
    old=row(conn,'job_positions',key) if key else None
    if key and not old:fail('岗位不存在',404)
    values={'title':text(body.get('title'),'岗位名称',160,True),'is_enabled':body.get('is_enabled',True)}
    if not isinstance(values['is_enabled'],bool):fail('岗位状态无效')
    if old:
        if body.get('version')!=old['version']:fail('岗位已变化，请刷新',409)
        conn.execute(T['job_positions'].update().where(T['job_positions'].c.id==key,T['job_positions'].c.version==old['version']).values(**values,
            version=old['version']+1,updated_at=utcnow(),updated_by_user_id=actor['id']));result=row(conn,'job_positions',key)
    else:result=insert_row(conn,'job_positions',values,actor['id'])
    audit(conn,actor,'organization.position.edit','job_positions',result['id']);return dict(result)


def sync_status(conn,config):
    state=conn.execute(sa.select(T['organization_sync_state']).where(T['organization_sync_state'].c.source_code==SOURCE)).mappings().first()
    runs=conn.execute(sa.select(T['organization_sync_runs']).where(T['organization_sync_runs'].c.source_code==SOURCE).order_by(T['organization_sync_runs'].c.created_at.desc()).limit(10)).mappings().all()
    source=config.get('ehr_database') or {}
    return {'configured':bool(source.get('enabled')),'database':source.get('name','EHR_DATABASE'),'org_code':str(config.get('ehr_org_code','ORG_ROOT')),
            'schedule':'每天 00:00','allowed_views':list(ALLOWED_VIEWS),'state':dict(state) if state else None,'runs':[dict(v) for v in runs]}
