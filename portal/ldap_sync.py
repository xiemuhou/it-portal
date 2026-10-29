"""Read-only LDAP/Active Directory synchronization for portal organization data."""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import ssl
import uuid

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from .database import TABLES as T,insert_row,row,utcnow
from .security import audit,password_hash


SOURCE='ldap'
DEFAULT_ATTRIBUTES={
    'stable_id':'objectGUID','login_name':'sAMAccountName','display_name':'displayName',
    'employee_no':'employeeID','department':'department','job_title':'title',
    'email':'mail','phone':'telephoneNumber','account_control':'userAccountControl',
}


def _clean(value,limit=256):
    if value is None:return ''
    if isinstance(value,(list,tuple)):value=value[0] if value else ''
    return str(value).strip()[:limit]


def _source(config):
    source=config.get('ldap') or {}
    if not source.get('enabled'):raise RuntimeError('尚未启用 LDAP/域用户同步')
    required=('host','base_dn','bind_dn','password')
    missing=[name for name in required if not source.get(name)]
    if missing:raise RuntimeError('LDAP 配置缺少：'+', '.join(missing))
    return source


def _stable_key(value,login):
    if isinstance(value,(bytes,bytearray)):
        try:return str(uuid.UUID(bytes_le=bytes(value)))
        except (ValueError,AttributeError):return bytes(value).hex()
    text=_clean(value,256)
    return text or login


def read_ldap(config,limit=None):
    """Bind with a read-only connection and execute only a configured LDAP search."""
    source=_source(config)
    try:
        from ldap3 import ALL,AUTO_BIND_NO_TLS,AUTO_BIND_TLS_BEFORE_BIND,Connection,NTLM,SIMPLE,Server,Tls
    except ImportError as exc:
        raise RuntimeError('服务器尚未安装 LDAP 同步依赖 ldap3') from exc
    use_ssl=bool(source.get('use_ssl',True));validate=bool(source.get('validate_certificate',True))
    tls=Tls(validate=ssl.CERT_REQUIRED if validate else ssl.CERT_NONE,version=ssl.PROTOCOL_TLS_CLIENT)
    server=Server(source['host'],port=int(source.get('port',636 if use_ssl else 389)),use_ssl=use_ssl,tls=tls,
        connect_timeout=int(source.get('connect_timeout_seconds',10)),get_info=ALL)
    authentication=NTLM if str(source.get('authentication','SIMPLE')).upper()=='NTLM' else SIMPLE
    auto_bind=AUTO_BIND_NO_TLS if use_ssl or not source.get('start_tls') else AUTO_BIND_TLS_BEFORE_BIND
    mapping={**DEFAULT_ATTRIBUTES,**(source.get('attributes') or {})}
    attributes=list(dict.fromkeys(value for value in mapping.values() if value))
    search_filter=str(source.get('user_filter') or '(&(objectCategory=person)(objectClass=user))')
    page_size=max(50,min(1000,int(source.get('page_size',500))))
    connection=Connection(server,user=source['bind_dn'],password=source['password'],authentication=authentication,
        auto_bind=auto_bind,read_only=True,raise_exceptions=True,receive_timeout=int(source.get('receive_timeout_seconds',30)))
    result=[]
    try:
        entries=connection.extend.standard.paged_search(search_base=source['base_dn'],search_filter=search_filter,
            search_scope='SUBTREE',attributes=attributes,paged_size=page_size,generator=True)
        for entry in entries:
            if entry.get('type')!='searchResEntry':continue
            values=entry.get('attributes') or {}
            login=_clean(values.get(mapping['login_name']),128).lower()
            if not login:continue
            raw_control=_clean(values.get(mapping.get('account_control')),32)
            try:disabled=bool(int(raw_control) & 2) if raw_control else False
            except ValueError:disabled=str(raw_control).lower() in ('true','disabled','inactive')
            result.append({'external_key':_stable_key(values.get(mapping.get('stable_id')),login),'login_name':login,
                'display_name':_clean(values.get(mapping['display_name']),128) or login,
                'employee_no':_clean(values.get(mapping.get('employee_no')),64) or None,
                'department_name':_clean(values.get(mapping.get('department')),128) or _clean(source.get('default_department'),128) or None,
                'job_title':_clean(values.get(mapping.get('job_title')),160) or None,
                'email':_clean(values.get(mapping.get('email')),254) or None,
                'phone':_clean(values.get(mapping.get('phone')),64) or None,'disabled':disabled})
            if limit and len(result)>=limit:break
        return {'users':result}
    finally:
        connection.unbind()


def test_connection(config):
    data=read_ldap(config,limit=5)
    return {'ok':True,'sample_count':len(data['users']),'message':'LDAP 只读连接及用户查询成功'}


def _linked_id(conn,entity_type,external_key):
    links=T['organization_external_links']
    return conn.execute(sa.select(links.c.local_id).where(links.c.source_code==SOURCE,
        links.c.entity_type==entity_type,links.c.external_key==external_key)).scalar()


def _link(conn,entity_type,external_key,local_id,now):
    links=T['organization_external_links']
    old=conn.execute(sa.select(links).where(links.c.source_code==SOURCE,
        links.c.entity_type==entity_type,links.c.external_key==external_key)).mappings().first()
    values={'local_id':local_id,'last_seen_at':now,'updated_at':now}
    if old:conn.execute(links.update().where(links.c.id==old['id']).values(**values))
    else:insert_row(conn,'organization_external_links',{'source_code':SOURCE,'entity_type':entity_type,
        'external_key':external_key,'local_id':local_id,'last_seen_at':now})


def _department_code(name):
    digest=hashlib.sha256(name.casefold().encode('utf-8')).hexdigest()[:12].upper()
    return 'LDAP-'+digest


def _apply(conn,data,actor_id=None):
    now=utcnow();errors=[];counts={'departments_created':0,'departments_linked':0,'users_created':0,
        'users_updated':0,'users_disabled':0,'positions_created':0,'assignments':0,'errors':0}
    incoming={}
    for item in data.get('users',[]):
        key=_clean(item.get('external_key'),256)
        if not key:errors.append('域用户缺少稳定标识');continue
        if key in incoming:errors.append('域用户稳定标识重复：'+key);continue
        incoming[key]=item

    departments=T['departments'];department_rows=[dict(v) for v in conn.execute(sa.select(departments).where(departments.c.is_archived==False)).mappings()]
    department_by_name={v['name'].strip().casefold():v for v in department_rows};department_ids={}
    for name in sorted({_clean(v.get('department_name'),128) for v in incoming.values()}-set([''])):
        normalized=name.casefold();local_id=_linked_id(conn,'department',normalized);old=row(conn,'departments',local_id) if local_id else department_by_name.get(normalized)
        if old:
            local_id=old['id'];counts['departments_linked']+=1
        else:
            local_id=insert_row(conn,'departments',{'code':_department_code(name),'name':name,'parent_id':None,'is_enabled':True},actor_id)['id']
            department_by_name[normalized]=row(conn,'departments',local_id);counts['departments_created']+=1
        department_ids[normalized]=local_id;_link(conn,'department',normalized,local_id,now)

    users=T['users'];all_users=[dict(v) for v in conn.execute(sa.select(users)).mappings()]
    by_login={v['login_name'].lower():v for v in all_users};by_employee={str(v['employee_no']).strip().casefold():v for v in all_users if v.get('employee_no')}
    employee_role=conn.execute(sa.select(T['roles'].c.id).where(T['roles'].c.code=='employee',T['roles'].c.is_archived==False)).scalar()
    user_ids={};position_pairs=[]
    for external_key,item in incoming.items():
        login=_clean(item.get('login_name'),128).lower();display_name=_clean(item.get('display_name'),128);employee_no=_clean(item.get('employee_no'),64)
        if not re.fullmatch(r'[a-z0-9][a-z0-9_.@-]{0,127}',login):errors.append(f'域账号 {login or external_key} 格式无效');continue
        department_name=_clean(item.get('department_name'),128);department_id=department_ids.get(department_name.casefold()) if department_name else None
        if not department_id:errors.append(f'域账号 {login} 缺少可匹配部门');continue
        local_id=_linked_id(conn,'user',external_key);old=row(conn,'users',local_id) if local_id else by_employee.get(employee_no.casefold()) if employee_no else None
        old=old or by_login.get(login)
        if old:
            collision=conn.execute(sa.select(users.c.id).where(users.c.login_name==login,users.c.id!=old['id'])).first()
            if collision:errors.append(f'域账号 {login} 与其他门户账号冲突');continue
            values={'login_name':login,'display_name':display_name or login,'department_id':department_id,
                'email':item.get('email'),'phone':item.get('phone'),'is_archived':False,'archived_at':None,'archived_by_user_id':None,
                'updated_at':now,'updated_by_user_id':actor_id,'version':old['version']+1}
            if employee_no:values['employee_no']=employee_no
            if item.get('disabled') and old['account_state']!='disabled':
                values.update(account_state='disabled',auth_version=old['auth_version']+1);counts['users_disabled']+=1
            conn.execute(users.update().where(users.c.id==old['id']).values(**values));local_id=old['id'];counts['users_updated']+=1
        else:
            local_id=insert_row(conn,'users',{'login_name':login,'display_name':display_name or login,'employee_no':employee_no or None,
                'department_id':department_id,'email':item.get('email'),'phone':item.get('phone'),
                'password_hash':password_hash(secrets.token_urlsafe(32)),'account_state':'disabled','auth_version':1},actor_id)['id']
            if employee_role:insert_row(conn,'user_roles',{'user_id':local_id,'role_id':employee_role},actor_id)
            counts['users_created']+=1
        user_ids[external_key]=local_id;_link(conn,'user',external_key,local_id,now)
        title=_clean(item.get('job_title'),160)
        if title:position_pairs.append((local_id,title))

    positions=T['job_positions'];position_by_title={v['title'].casefold():dict(v) for v in conn.execute(sa.select(positions).where(positions.c.is_archived==False)).mappings()}
    assignments=T['user_job_assignments']
    if user_ids:conn.execute(assignments.delete().where(assignments.c.source_type==SOURCE,assignments.c.user_id.in_(list(user_ids.values()))))
    for user_id,title in position_pairs:
        normalized=title.casefold();old=position_by_title.get(normalized);local_id=_linked_id(conn,'position',normalized)
        if not local_id:
            if old:local_id=old['id']
            else:
                local_id=insert_row(conn,'job_positions',{'title':title,'is_enabled':True},actor_id)['id'];counts['positions_created']+=1
                position_by_title[normalized]=row(conn,'job_positions',local_id)
            _link(conn,'position',normalized,local_id,now)
        exists=conn.execute(sa.select(assignments.c.id).where(assignments.c.user_id==user_id,assignments.c.position_id==local_id)).first()
        if not exists:insert_row(conn,'user_job_assignments',{'user_id':user_id,'position_id':local_id,'source_type':SOURCE},actor_id)
        counts['assignments']+=1
    counts['errors']=len(errors)
    message=f"域同步完成：部门 {len(department_ids)}、人员 {len(user_ids)}、岗位 {len(set(v for _,v in position_pairs))}"
    if errors:message+=f"；{len(errors)} 条数据提示"
    return {'message':message,'counts':counts,'errors':errors[:100]}


def sync_ldap(portal_engine,config,trigger_type='manual',actor=None,trigger_key=None):
    trigger_key=trigger_key or f'manual:{uuid.uuid4()}';run_id=str(uuid.uuid4());now=utcnow()
    runs,state=T['organization_sync_runs'],T['organization_sync_state']
    try:
        with portal_engine.begin() as conn:
            conn.execute(runs.insert().values(id=run_id,created_at=now,source_code=SOURCE,trigger_type=trigger_type,
                trigger_key=trigger_key,actor_user_id=actor['id'] if actor else None,status='running'))
            current=conn.execute(sa.select(state).where(state.c.source_code==SOURCE)).mappings().first()
            values={'last_attempt_at':now,'last_status':'running','last_message':'正在读取 LDAP/Active Directory','updated_at':now}
            if current:conn.execute(state.update().where(state.c.source_code==SOURCE).values(**values))
            else:conn.execute(state.insert().values(source_code=SOURCE,**values))
    except IntegrityError:
        return {'skipped':True,'message':'该时段域同步任务已由另一个进程执行'}
    try:
        data=read_ldap(config)
        with portal_engine.begin() as conn:
            result=_apply(conn,data,actor['id'] if actor else None);current=conn.execute(sa.select(state).where(state.c.source_code==SOURCE)).mappings().one()
            status='partial' if result['errors'] else 'success';completed=utcnow()
            conn.execute(state.update().where(state.c.source_code==SOURCE).values(first_success_at=current['first_success_at'] or completed,
                last_success_at=completed,last_attempt_at=completed,last_status=status,last_message=result['message'],updated_at=completed))
            conn.execute(runs.update().where(runs.c.id==run_id).values(completed_at=completed,status=status,
                message=result['message'],summary_json=json.dumps(result,ensure_ascii=False,default=str)))
            audit(conn,actor,'organization.sync.ldap','organization_sync_runs',run_id,result['counts'])
        return result
    except Exception as exc:
        message='域同步失败：'+str(exc)[:850]
        with portal_engine.begin() as conn:
            conn.execute(runs.update().where(runs.c.id==run_id).values(completed_at=utcnow(),status='error',message=message))
            conn.execute(state.update().where(state.c.source_code==SOURCE).values(last_attempt_at=utcnow(),last_status='error',last_message=message,updated_at=utcnow()))
        raise RuntimeError(message) from exc


def sync_status(conn,config):
    source=config.get('ldap') or {};state=T['organization_sync_state'];runs=T['organization_sync_runs']
    current=conn.execute(sa.select(state).where(state.c.source_code==SOURCE)).mappings().first()
    recent=conn.execute(sa.select(runs).where(runs.c.source_code==SOURCE).order_by(runs.c.created_at.desc()).limit(10)).mappings().all()
    return {'configured':bool(source.get('enabled')),'host':source.get('host'),'base_dn':source.get('base_dn'),
        'use_ssl':bool(source.get('use_ssl',True)),'validate_certificate':bool(source.get('validate_certificate',True)),
        'schedule':'每天 '+str(source.get('schedule_hour',1)).zfill(2)+':00' if source.get('schedule_enabled') else '仅手动',
        'mode':'read_only_import','state':dict(current) if current else None,'runs':[dict(v) for v in recent]}
