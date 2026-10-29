"""FastAPI application for the database-backed portal."""
from contextlib import asynccontextmanager
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import quote
import hashlib
import json
import mimetypes
import os
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timezone as datetime_timezone
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError, DataError, DBAPIError

from .database import ROOT, TABLES as T, SPECS, metadata, settings, database_url, make_engine, insert_row, row, utcnow, jsonable, uid
from .security import fail, require, allow, grants, seed, audit, current_user, public_user, password_hash, verify, digest, csrf, login_limited, reset_failures, PERMISSIONS
from . import tickets, catalog, transfers, ledger, ipam, organization, ldap_sync, ai, consumables, memos
from .content import register_content
from .operations import FileStorage,configure_logging,close_logging,cleanup_logs,purge_expired,set_request_id,reset_request_id,current_request_id
from document_library import KnowledgeLibrary, SUPPORTED


def output(data,status=200):
    return JSONResponse(jsonable(data),status_code=status)


BASIC_DATA_NO_TRANSFER={'sites','locations','vendors','dictionary_items','ticket_categories','knowledge_categories','service_catalog','improvement_projects'}


def checked_version(conn,name,old,body,values,user):
    if body.get('version')!=old['version']:fail('内容已变化，请刷新后重试',409)
    t=T[name]
    count=conn.execute(t.update().where(t.c.id==old['id'],t.c.version==old['version']).values(**values,
        version=old['version']+1,updated_at=utcnow(),updated_by_user_id=user['id'])).rowcount
    if count!=1:fail('保存冲突，请刷新后重试',409)


def prevent_last_admin(conn,target_id,new_roles=None,disabling=False):
    users,roles,ur=(T[x] for x in ('users','roles','user_roles'))
    admin=conn.execute(sa.select(roles).where(roles.c.code=='admin',roles.c.is_archived==False)).mappings().one()
    existing={v[0] for v in conn.execute(sa.select(ur.c.role_id).where(ur.c.user_id==target_id))}
    if admin['id'] not in existing:return
    if not disabling and (new_roles is None or admin['id'] in new_roles):return
    # Serialize this invariant on the shared administrator role (both engines).
    result=conn.execute(roles.update().where(roles.c.id==admin['id'],roles.c.version==admin['version']).values(version=admin['version']+1))
    if result.rowcount!=1:fail('管理员状态已变化，请重试',409)
    count=conn.execute(sa.select(sa.func.count()).select_from(users.join(ur,users.c.id==ur.c.user_id)).where(
        ur.c.role_id==admin['id'],users.c.account_state=='active',users.c.is_archived==False,users.c.id!=target_id)).scalar_one()
    if not count:fail('必须保留至少一个有效管理员')


def assign_roles(conn,user,target_id,role_ids):
    require(conn,user,'user.roles')
    if not isinstance(role_ids,list) or not role_ids or len(role_ids)!=len(set(role_ids)):fail('至少选择一个有效角色，且不能重复')
    for key in role_ids:
        role=row(conn,'roles',key)
        if not role or role['is_archived']:fail('角色不存在或已停用')
    prevent_last_admin(conn,target_id,role_ids)
    table=T['user_roles'];conn.execute(table.delete().where(table.c.user_id==target_id))
    for key in role_ids:insert_row(conn,'user_roles',{'user_id':target_id,'role_id':key},user['id'])


def create_user(conn,user,body):
    require(conn,user,'user.create')
    allowed={'login_name','display_name','department_id','email','phone','role_ids','position_ids','password'}
    if set(body)-allowed:fail('用户字段不受支持')
    login=tickets.text(body.get('login_name'),'账号',128,True).lower()
    import re
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.@-]{0,127}',login):fail('账号仅允许英文字母、数字及 _.@-')
    department=row(conn,'departments',body.get('department_id'))
    if not department or not department['is_enabled'] or department['is_archived']:fail('请选择有效部门')
    initial=body.get('password') or secrets.token_urlsafe(12)
    target=insert_row(conn,'users',{'login_name':login,'display_name':tickets.text(body.get('display_name'),'姓名',128,True),
        'department_id':department['id'],'email':tickets.text(body.get('email'),'邮箱',254) or None,'phone':tickets.text(body.get('phone'),'电话',64) or None,
        'password_hash':password_hash(initial),'account_state':'active','auth_version':1},user['id'])
    if 'role_ids' in body:
        assign_roles(conn,user,target['id'],body['role_ids'])
    else:
        employee=conn.execute(sa.select(T['roles'].c.id).where(T['roles'].c.code=='employee',T['roles'].c.is_archived==False)).first()
        if not employee:fail('请由管理员配置可分配的员工角色')
        insert_row(conn,'user_roles',{'user_id':target['id'],'role_id':employee[0]},user['id'])
    if 'position_ids' in body:organization.assign_positions(conn,user,target['id'],body['position_ids'])
    audit(conn,user,'user.create','users',target['id'])
    return {'id':target['id'],'login_name':login,'initial_password':initial}


def make_app(url=None,data_dir=None,initialize=None):
    config=settings()
    if data_dir:config['data_dir']=str(data_dir)
    folder=Path(config['data_dir']);folder.mkdir(parents=True,exist_ok=True)
    engine=make_engine(url or database_url(config))
    engine.ai_data_dir=str(folder)
    if initialize is None:initialize=engine.dialect.name=='sqlite'
    organization_sync_lock=threading.Lock()
    maintenance_lock=threading.Lock()
    log_retention_days=int(config.get('log_retention_days',90))
    audit_retention_days=int(config.get('audit_retention_days',180))
    notification_retention_days=int(config.get('notification_retention_days',180))
    logger=configure_logging(folder,log_retention_days)
    storage=FileStorage(folder)

    def organization_sync_worker(source,trigger_type,actor=None,trigger_key=None,lock_held=False):
        acquired=lock_held or organization_sync_lock.acquire(blocking=False)
        if not acquired:return False
        try:
            if source=='ehr':organization.sync_ehr(engine,config,trigger_type,actor,trigger_key)
            elif source=='ldap':ldap_sync.sync_ldap(engine,config,trigger_type,actor,trigger_key)
            else:raise ValueError('组织同步来源无效')
        except Exception:pass
        finally:organization_sync_lock.release()
        return True

    def maintenance_worker():
        if not maintenance_lock.acquire(blocking=False):return None
        try:
            report=storage.reconcile(engine,T)
            counts=purge_expired(engine,T,audit_retention_days,notification_retention_days)
            counts['logs']=cleanup_logs(folder/'logs',log_retention_days)
            with engine.begin() as conn:
                audit(conn,None,'system.retention','system',changes={'retention_days':{
                    'logs':log_retention_days,'audit':audit_retention_days,'notifications':notification_retention_days},'deleted':counts})
            logger.info('maintenance.completed',extra={'event':'maintenance.completed','job':'daily-governance','counts':{
                **counts,'file_missing':len(report['missing_files']),'file_mismatch':len(report['hash_mismatches']),
                'file_orphans':len(report['orphan_files']),'asset_orphans':len(report['orphan_knowledge_assets']),
                'file_recovered':len(report['recovered_pending']),'credential_key_present':report['credential_key']['exists']}})
            return {'files':report,'deleted':counts}
        except Exception as exc:
            logger.exception('maintenance.failed',extra={'event':'maintenance.failed','job':'daily-governance','error_type':type(exc).__name__})
            return None
        finally:maintenance_lock.release()

    @asynccontextmanager
    async def lifespan(app):
        if initialize:
            metadata.create_all(engine)
        elif not sa.inspect(engine).has_table('users'):
            raise RuntimeError('数据库尚未初始化，请先按部署说明执行 Alembic upgrade head 和管理员初始化。')
        with engine.begin() as conn:seed(conn,folder)
        stop_scheduler=threading.Event()
        def scheduled_organization_sync():
            try:timezone=ZoneInfo(config.get('timezone','Asia/Shanghai'))
            except Exception:timezone=datetime_timezone(timedelta(hours=8))
            while not stop_scheduler.is_set():
                now=datetime.now(timezone);key='schedule:'+now.date().isoformat()
                try:
                    organization_sync_worker('ehr','schedule',None,key)
                except Exception:
                    pass
                delay=max(30,min(3600,((now.replace(hour=0,minute=0,second=0,microsecond=0)+timedelta(days=1))-now).total_seconds()))
                stop_scheduler.wait(delay)
        def scheduled_ldap_sync():
            try:timezone=ZoneInfo(config.get('timezone','Asia/Shanghai'))
            except Exception:timezone=datetime_timezone(timedelta(hours=8))
            hour=max(0,min(23,int((config.get('ldap') or {}).get('schedule_hour',1))))
            while not stop_scheduler.is_set():
                now=datetime.now(timezone);target=now.replace(hour=hour,minute=0,second=0,microsecond=0)
                if target<=now:target+=timedelta(days=1)
                if stop_scheduler.wait(max(30,(target-now).total_seconds())):break
                organization_sync_worker('ldap','schedule',None,'schedule:'+target.date().isoformat())
        def scheduled_maintenance():
            maintenance_worker()
            try:timezone=ZoneInfo(config.get('timezone','Asia/Shanghai'))
            except Exception:timezone=datetime_timezone(timedelta(hours=8))
            while not stop_scheduler.is_set():
                now=datetime.now(timezone);target=now.replace(hour=2,minute=30,second=0,microsecond=0)
                if target<=now:target+=timedelta(days=1)
                if stop_scheduler.wait(max(30,(target-now).total_seconds())):break
                maintenance_worker()
        organization_scheduler=threading.Thread(target=scheduled_organization_sync,name='organization-sync',daemon=True) if url is None and (config.get('ehr_database') or {}).get('enabled') else None
        ldap_scheduler=threading.Thread(target=scheduled_ldap_sync,name='ldap-sync',daemon=True) if url is None and (config.get('ldap') or {}).get('enabled') and (config.get('ldap') or {}).get('schedule_enabled') else None
        maintenance_scheduler=threading.Thread(target=scheduled_maintenance,name='daily-governance',daemon=True) if url is None else None
        if organization_scheduler:organization_scheduler.start()
        if ldap_scheduler:ldap_scheduler.start()
        if maintenance_scheduler:maintenance_scheduler.start()
        try:yield
        finally:
            stop_scheduler.set()
            if organization_scheduler:organization_scheduler.join(timeout=2)
            if ldap_scheduler:ldap_scheduler.join(timeout=2)
            if maintenance_scheduler:maintenance_scheduler.join(timeout=2)
            engine.dispose()
            close_logging(logger)

    app=FastAPI(title='IT 门户与工单系统',version='2.0.0',lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
    app.state.engine=engine;app.state.config=config;app.state.storage=storage;app.state.run_maintenance=maintenance_worker;app.state.logger=logger

    @app.middleware('http')
    async def headers(request,call_next):
        request_id=secrets.token_hex(16);token=set_request_id(request_id);started=time.perf_counter();status=500
        try:
            try:
                if int(request.headers.get('content-length','0'))>transfers.MAX_BYTES+1024*1024:
                    response=output({'error':'请求体过大'},413);status=413;return response
            except ValueError:
                response=output({'error':'请求长度无效'},400);status=400;return response
            if request.method not in ('GET','HEAD','OPTIONS'):
                origin=request.headers.get('origin')
                if origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):
                    response=output({'error':'拒绝跨站请求'},403);status=403;return response
            response=await call_next(request);status=response.status_code
            response.headers['X-Content-Type-Options']='nosniff'
            response.headers['Referrer-Policy']='same-origin'
            response.headers['Cache-Control']='no-store'
            response.headers['X-Request-ID']=request_id
            response.headers.setdefault('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'")
            return response
        except Exception as exc:
            logger.exception('http.unhandled',extra={'event':'http.unhandled','request_id':request_id,'method':request.method,
                'path':request.url.path,'error_type':type(exc).__name__})
            raise
        finally:
            logger.info('http.request',extra={'event':'http.request','request_id':request_id,'method':request.method,'path':request.url.path,
                'status':status,'duration_ms':round((time.perf_counter()-started)*1000,2),'client':request.client.host if request.client else None})
            reset_request_id(token)

    @app.exception_handler(HTTPException)
    async def http_error(request,exc):return output({'error':str(exc.detail)},exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request,exc):return output({'error':'请求格式不正确，请检查输入'},422)

    @app.exception_handler(IntegrityError)
    async def integrity_error(request,exc):return output({'error':'业务编号重复、关联仍在使用或数据发生冲突，请核对后重试'},409)

    @app.exception_handler(DataError)
    async def data_error(request,exc):return output({'error':'字段类型或长度超出限制'},422)

    @app.exception_handler(DBAPIError)
    async def database_error(request,exc):
        logger.error('database.error',extra={'event':'database.error','request_id':current_request_id(),'path':request.url.path,'error_type':type(exc).__name__})
        return output({'error':'数据库暂不可用，请稍后重试'},503)

    @app.get('/api/health')
    def health():return output({'status':'ok','version':'2.0.0','database':engine.dialect.name,'legacy_sync':False})

    @app.get('/api/system/file-integrity')
    def file_integrity(request:Request):
        with engine.begin() as conn:require(conn,current_user(conn,request),'audit.view')
        latest=storage.reports/'latest.json'
        return output(json.loads(latest.read_text(encoding='utf-8')) if latest.is_file() else {'status':'尚未执行巡检'})

    @app.post('/api/system/maintenance')
    def run_system_maintenance(request:Request,body:dict):
        with engine.begin() as conn:require(conn,current_user(conn,request),'settings.edit')
        result=maintenance_worker()
        if result is None:fail('维护任务正在运行或本次执行失败，请查看结构化日志',409)
        return output(result)

    @app.get('/api/session')
    def session(request:Request):
        with engine.begin() as conn:
            user=current_user(conn,request,True)
            return output({'user':public_user(conn,user,request.cookies.get('portal_v2_session','')) if user else None,'database':engine.dialect.name})

    @app.post('/api/auth/login')
    def login(request:Request,body:dict):
        login=tickets.text(body.get('login_name'),'账号',128).lower();password=body.get('password','')
        if not isinstance(password,str) or len(password)>256:fail('账号或密码错误',401)
        limit_key=(request.client.host if request.client else 'local',login)
        login_limited(limit_key)
        with engine.begin() as conn:
            users=T['users'];user=conn.execute(sa.select(users).where(users.c.login_name==login)).mappings().first()
            if not user or not verify(password,user['password_hash']) or user['account_state']!='active' or user['is_archived']:fail('账号或密码错误',401)
            reset_failures(limit_key);token=secrets.token_urlsafe(32);now=utcnow()
            insert_row(conn,'user_sessions',{'user_id':user['id'],'token_hash':digest(token),'csrf_hash':digest(csrf(token)),
                'auth_version':user['auth_version'],'expires_at':now+timedelta(hours=8),'idle_expires_at':now+timedelta(minutes=10),'last_seen_at':now})
            conn.execute(users.update().where(users.c.id==user['id']).values(last_login_at=now))
            audit(conn,user,'auth.login','users',user['id'])
            response=output({'user':public_user(conn,user,token)})
            response.set_cookie('portal_v2_session',token,max_age=28800,httponly=True,samesite='strict',secure=bool(config.get('secure_cookie',False)))
            return response

    @app.post('/api/auth/logout')
    def logout(request:Request,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);s=T['user_sessions']
            conn.execute(s.update().where(s.c.token_hash==digest(request.cookies.get('portal_v2_session',''))).values(revoked_at=utcnow()))
            response=output({'ok':True});response.delete_cookie('portal_v2_session');return response

    @app.post('/api/auth/password')
    def change_password(request:Request,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request)
            if not verify(body.get('old_password',''),user['password_hash']):fail('当前密码不正确')
            new=password_hash(body.get('password'));u=T['users']
            conn.execute(u.update().where(u.c.id==user['id']).values(password_hash=new,auth_version=user['auth_version']+1))
            audit(conn,user,'user.password.self','users',user['id'])
            response=output({'ok':True});response.delete_cookie('portal_v2_session');return response

    @app.get('/api/lookups')
    def lookups(request:Request):
        with engine.begin() as conn:
            user=current_user(conn,request);result={}
            for name in ['departments','sites','ticket_categories']:
                t=T[name];result[name]=[dict(v) for v in conn.execute(sa.select(t.c.id,t.c.name,t.c.code).where(t.c.is_archived==False,t.c.is_enabled==True).order_by(t.c.name)).mappings()]
            if allow(conn,user,'ticket.assign') or allow(conn,user,'ticket.transfer'):
                # Drain the cursor before per-user permission queries (ODBC without MARS).
                users=conn.execute(sa.select(T['users']).where(T['users'].c.account_state=='active',T['users'].c.is_archived==False)).mappings().all()
                result['handlers']=[{'id':v['id'],'name':v['display_name']} for v in users if allow(conn,v,'ticket.claim')]
            if allow(conn,user,'user.view'):
                p=T['job_positions']
                result['positions']=[{'id':v['id'],'name':v['title']}
                    for v in conn.execute(sa.select(p.c.id,p.c.title).where(
                        p.c.is_archived==False,p.c.is_enabled==True).order_by(p.c.title)).mappings()]
            return output(result)

    @app.get('/api/users')
    def users(request:Request,page:int=1,page_size:int=10,q:str='',department_id:str='',account_state:str='',source_type:str=''):
        if page_size not in (10,20,50):fail('每页条数仅支持 10、20、50',422)
        if account_state not in ('','active','disabled'):fail('筛选账号状态无效',422)
        if source_type not in ('','ehr','ldap','manual'):fail('筛选人员来源无效',422)
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'user.view');t=T['users']
            departments=[dict(v) for v in conn.execute(sa.select(T['departments'].c.id,T['departments'].c.name,T['departments'].c.parent_id)).mappings()]
            department_map={v['id']:v for v in departments}
            query=sa.select(t).where(t.c.is_archived==False)
            if q:query=query.where(sa.or_(t.c.login_name.contains(q,autoescape=True),t.c.display_name.contains(q,autoescape=True)))
            if account_state:query=query.where(t.c.account_state==account_state)
            external=T['organization_external_links']
            ehr_link=sa.exists(sa.select(1).where(external.c.source_code=='ehr',external.c.entity_type=='user',external.c.local_id==t.c.id))
            ldap_link=sa.exists(sa.select(1).where(external.c.source_code=='ldap',external.c.entity_type=='user',external.c.local_id==t.c.id))
            if source_type=='ehr':query=query.where(ehr_link)
            elif source_type=='ldap':query=query.where(ldap_link)
            elif source_type=='manual':query=query.where(~ehr_link,~ldap_link)
            if department_id:
                if department_id not in department_map:fail('筛选部门不存在',422)
                selected={department_id};changed=True
                while changed:
                    before=len(selected);selected.update(v['id'] for v in departments if v['parent_id'] in selected);changed=len(selected)>before
                query=query.where(t.c.department_id.in_(selected))
            count=conn.execute(sa.select(sa.func.count()).select_from(query.subquery())).scalar_one()
            rows=[dict(v) for v in conn.execute(query.order_by(t.c.created_at,t.c.id).offset((max(1,page)-1)*page_size).limit(page_size)).mappings()]
            links=conn.execute(sa.select(T['organization_external_links'].c.local_id,T['organization_external_links'].c.source_code).where(
                T['organization_external_links'].c.entity_type=='user',T['organization_external_links'].c.source_code.in_(('ehr','ldap')))).all()
            linked={};
            for local_id,source_code in links:linked.setdefault(local_id,set()).add(source_code)
            for r in rows:
                r.pop('password_hash',None)
                sources=linked.get(r['id'],set());r['source_type']='ehr' if 'ehr' in sources else 'ldap' if 'ldap' in sources else 'manual'
                r['role_ids']=[v[0] for v in conn.execute(sa.select(T['user_roles'].c.role_id).where(T['user_roles'].c.user_id==r['id']))]
                r['position_ids']=[v[0] for v in conn.execute(sa.select(T['user_job_assignments'].c.position_id).where(T['user_job_assignments'].c.user_id==r['id']))]
                department=department_map.get(r.get('department_id'));r['department_name']=department['name'] if department else None
                seen=set()
                while department and department.get('parent_id') in department_map and department['id'] not in seen:
                    seen.add(department['id']);department=department_map[department['parent_id']]
                r['top_department_id']=department['id'] if department else None;r['top_department_name']=department['name'] if department else None
            return output({'items':rows,'total':count,'page':max(1,page),'page_size':page_size})

    @app.post('/api/users')
    def users_create(request:Request,body:dict):
        with engine.begin() as conn:return output(create_user(conn,current_user(conn,request),body),201)

    @app.put('/api/users/{key}')
    def users_edit(request:Request,key:str,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'user.edit');old=row(conn,'users',key)
            if not old:fail('用户不存在',404)
            if set(body)-{'version','display_name','department_id','email','phone','account_state','role_ids','position_ids'}:fail('字段不受支持')
            values={}
            for k,n in [('display_name',128),('email',254),('phone',64)]:
                if k in body:values[k]=tickets.text(body[k],k,n,k=='display_name') or None
            if 'department_id' in body:
                department=row(conn,'departments',body['department_id'])
                if not department or not department['is_enabled']:fail('部门无效')
                values['department_id']=department['id']
            state=body.get('account_state',old['account_state'])
            if state not in ('active','disabled'):fail('账号状态无效')
            if state=='disabled':
                prevent_last_admin(conn,key,disabling=True)
                active=conn.execute(sa.select(T['tickets'].c.id).where(T['tickets'].c.assignee_user_id==key,T['tickets'].c.status.in_(['pending','in_progress']))).first()
                if active:fail('请先转派此用户的未结束工单或解除预分派')
            if 'role_ids' in body:assign_roles(conn,user,key,body['role_ids'])
            if 'position_ids' in body:organization.assign_positions(conn,user,key,body['position_ids'])
            values.update(account_state=state,auth_version=old['auth_version']+1)
            checked_version(conn,'users',old,body,values,user);audit(conn,user,'user.edit','users',key)
            return output({'ok':True})

    @app.get('/api/organization/positions')
    def organization_positions(request:Request,page:int=1,page_size:int=10,q:str=''):
        if page_size not in (10,20,50):fail('每页条数仅支持 10、20、50',422)
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'user.view')
            return output(organization.position_list(conn,q,page,page_size))

    @app.post('/api/organization/positions')
    def organization_position_create(request:Request,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'directory.edit')
            return output(organization.save_position(conn,user,body),201)

    @app.put('/api/organization/positions/{key}')
    def organization_position_update(request:Request,key:str,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'directory.edit')
            return output(organization.save_position(conn,user,body,key))

    @app.get('/api/organization/sync-status')
    def organization_sync_status(request:Request):
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'user.view')
            return output(organization.sync_status(conn,config))

    @app.post('/api/organization/sync-ehr')
    def organization_sync_ehr(request:Request,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'user.import');require(conn,user,'directory.import')
        if not organization_sync_lock.acquire(blocking=False):fail('组织数据同步正在运行，请稍后查看同步状态',409)
        worker=threading.Thread(target=organization_sync_worker,args=('ehr','manual',dict(user),None,True),name='organization-sync-manual',daemon=True)
        worker.start()
        return output({'started':True,'message':'EHR 同步任务已开始，可在本页查看进度'},202)

    @app.get('/api/organization/ldap-status')
    def organization_ldap_status(request:Request):
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'user.view')
            result=ldap_sync.sync_status(conn,config)
            result['message']='LDAP 已配置，只执行只读查询。' if result['configured'] else 'LDAP 尚未启用，请先在 business.local.json 配置只读连接。'
            return output(result)

    @app.post('/api/organization/test-ldap')
    def organization_test_ldap(request:Request,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'user.import');require(conn,user,'directory.import')
        try:return output(ldap_sync.test_connection(config))
        except Exception as exc:fail('LDAP 连接测试失败：'+str(exc)[:850],409)

    @app.post('/api/organization/sync-ldap')
    def organization_sync_ldap(request:Request,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'user.import');require(conn,user,'directory.import')
        if not (config.get('ldap') or {}).get('enabled'):fail('LDAP 尚未启用，请先完成本机只读连接配置',409)
        if not organization_sync_lock.acquire(blocking=False):fail('组织数据同步正在运行，请稍后查看同步状态',409)
        worker=threading.Thread(target=organization_sync_worker,args=('ldap','manual',dict(user),None,True),name='ldap-sync-manual',daemon=True)
        worker.start();return output({'started':True,'message':'LDAP 域用户同步任务已开始，可在本页查看进度'},202)

    @app.post('/api/users/{key}/password')
    def users_password(request:Request,key:str,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'user.password');old=row(conn,'users',key)
            if not old:fail('用户不存在',404)
            new=body.get('password') or secrets.token_urlsafe(12)
            checked_version(conn,'users',old,body,{'password_hash':password_hash(new),'auth_version':old['auth_version']+1},user)
            audit(conn,user,'user.password.admin','users',key)
            return output({'initial_password':new,'login_name':old['login_name']})

    @app.delete('/api/users/{key}')
    def users_delete(request:Request,key:str,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'user.delete');old=row(conn,'users',key)
            if not old:fail('用户不存在',404)
            if body.get('confirm')!=key:fail('请确认删除对象')
            reason=tickets.text(body.get('reason'),'删除原因',1024,True)
            prevent_last_admin(conn,key,disabling=True)
            active=conn.execute(sa.select(T['tickets'].c.id).where(T['tickets'].c.assignee_user_id==key,T['tickets'].c.status.in_(['pending','in_progress']))).first()
            if active:fail('先转派未结束工单，再删除用户')
            if conn.execute(sa.select(T['computer_assets'].c.id).where(T['computer_assets'].c.user_id==key,T['computer_assets'].c.is_archived==False).limit(1)).first():
                fail('该人员仍被电脑设备台账引用，请先把电脑转移给其他人员',409)
            if conn.execute(sa.select(T['static_ip_records'].c.id).where(T['static_ip_records'].c.user_id==key,T['static_ip_records'].c.occupancy_status.in_(('occupied','conflict'))).limit(1)).first():
                fail('该人员仍被静态 IP 占用记录引用，请先调整责任人员',409)
            checked_version(conn,'users',old,body,{'login_name':'deleted-'+key,'display_name':'已删除用户','employee_no':None,'email':None,'phone':None,
                'password_hash':password_hash(secrets.token_urlsafe(32)),'account_state':'disabled','auth_version':old['auth_version']+1,
                'is_archived':True,'archived_at':utcnow(),'archived_by_user_id':user['id']},user)
            conn.execute(T['user_roles'].delete().where(T['user_roles'].c.user_id==key))
            conn.execute(T['tickets'].update().where(T['tickets'].c.requester_user_id==key).values(requester_name_snapshot='已删除用户',contact_snapshot=None))
            for name,id_field,name_field in [('ticket_events','actor_user_id','actor_name_snapshot'),('ticket_cycles','final_handler_id','final_handler_name_snapshot'),
                ('ticket_handling_segments','handler_user_id','handler_name_snapshot'),('audit_logs','actor_user_id','actor_name_snapshot')]:
                conn.execute(T[name].update().where(T[name].c[id_field]==key).values(**{name_field:'已删除用户'}))
            audit(conn,user,'user.deleted_anonymized','users',key,reason=reason)
            return output({'ok':True,'mode':'anonymized','message':'身份资料和凭据已清除，保留匿名标识维护历史关系'})

    @app.get('/api/roles')
    def roles(request:Request):
        with engine.begin() as conn:
            user=current_user(conn,request)
            if not any(allow(conn,user,p) for p in ('role.view','user.roles','user.view','user.create')):fail('没有角色查看权限',403)
            rows=[dict(v) for v in conn.execute(sa.select(T['roles']).order_by(T['roles'].c.code)).mappings()]
            editable=allow(conn,user,'role.view')
            for item in rows:
                item['permissions']=[]
                if editable:
                    rp=T['role_permissions'];p=T['permissions']
                    role_grants=conn.execute(sa.select(rp,p.c.code).select_from(rp.join(p,rp.c.permission_id==p.c.id)).where(rp.c.role_id==item['id'])).mappings().all()
                    for grant in role_grants:
                        g=dict(grant)
                        for n,field in [('role_permission_sites','site_id'),('role_permission_departments','department_id')]:
                            g[field+'s']=[r[0] for r in conn.execute(sa.select(T[n].c[field]).where(T[n].c.role_permission_id==g['id']))]
                        item['permissions'].append(g)
            return output({'items':rows,'permissions':[{'code':k,'module':v[0],'supports_data_scope':v[1]} for k,v in PERMISSIONS.items()] if editable else []})

    def save_role(conn,user,body,key=None):
        require(conn,user,'role.edit');old=row(conn,'roles',key) if key else None
        if old and old['code']=='admin':fail('系统管理员角色保留全部管理能力，请新增自定义角色')
        if key and not old:fail('角色不存在',404)
        values={'name':tickets.text(body.get('name'),'角色名',128,True),'description':tickets.text(body.get('description'),'角色说明',512) or None}
        if old:
            checked_version(conn,'roles',old,body,values,user);result=dict(row(conn,'roles',key))
        else:
            code=tickets.text(body.get('code'),'角色编码',64,True)
            if not code.isascii() or not all(c.isalnum() or c=='_' for c in code):fail('角色编码须为英文、数字或下划线')
            result=insert_row(conn,'roles',{**values,'code':code,'is_builtin':False},user['id'])
        rp=T['role_permissions'];existing=[v[0] for v in conn.execute(sa.select(rp.c.id).where(rp.c.role_id==result['id']))]
        for name in ['role_permission_sites','role_permission_departments']:
            conn.execute(T[name].delete().where(T[name].c.role_permission_id.in_(existing)))
        conn.execute(rp.delete().where(rp.c.role_id==result['id']))
        seen=set()
        for grant in body.get('permissions',[]):
            code=grant.get('code');scope=grant.get('scope','none')
            if code not in PERMISSIONS or code in seen:fail('权限无效或重复')
            seen.add(code)
            if scope not in ('own','assigned','site','department','all','none'):fail('数据范围无效')
            scoped=PERMISSIONS[code][1]
            if scoped and scope=='none' or not scoped and scope!='none':fail('功能权限/数据权限范围不匹配')
            permission=conn.execute(sa.select(T['permissions'].c.id).where(T['permissions'].c.code==code)).scalar_one()
            r=insert_row(conn,'role_permissions',{'role_id':result['id'],'permission_id':permission,'data_scope':scope},user['id'])
            if scope in ('site','department'):
                name,field,target=('role_permission_sites','site_id','sites') if scope=='site' else ('role_permission_departments','department_id','departments')
                ids=grant.get(field+'s',[])
                if not ids:fail('请为指定范围选择至少一个对象')
                for value in set(ids):
                    if not row(conn,target,value):fail('范围对象不存在')
                    insert_row(conn,name,{'role_permission_id':r['id'],field:value},user['id'])
        audit(conn,user,'role.edit','roles',result['id'])
        return result

    @app.post('/api/roles')
    def roles_create(request:Request,body:dict):
        with engine.begin() as conn:return output(save_role(conn,current_user(conn,request),body),201)

    @app.put('/api/roles/{key}')
    def roles_update(request:Request,key:str,body:dict):
        with engine.begin() as conn:return output(save_role(conn,current_user(conn,request),body,key))

    @app.post('/api/roles/{key}/state')
    def role_state(request:Request,key:str,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'role.edit');old=row(conn,'roles',key)
            if not old:fail('角色不存在',404)
            if old['code']=='admin':fail('不能停用系统管理员角色')
            archive=body.get('disabled')
            if not isinstance(archive,bool):fail('状态无效')
            checked_version(conn,'roles',old,body,{'is_archived':archive,'archived_at':utcnow() if archive else None,'archived_by_user_id':user['id'] if archive else None},user)
            audit(conn,user,'role.state','roles',key)
            return output({'ok':True})

    @app.get('/api/tickets')
    def tickets_list(request:Request,page:int=1,page_size:int=10,q:str='',status:str='',mine:bool=False,site_id:str='',category_id:str=''):
        if page_size not in (10,20,50):fail('每页条数仅支持 10、20、50',422)
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'ticket.view');t=T['tickets']
            query=sa.select(t).where(catalog.scope_expression(conn,user,'ticket.view',t))
            if status:query=query.where(t.c.status==status)
            if mine:query=query.where(t.c.assignee_user_id==user['id'])
            if site_id:query=query.where(t.c.site_id==site_id)
            if category_id:query=query.where(t.c.category_id==category_id)
            if q:query=query.where(sa.or_(t.c.title.contains(q,autoescape=True),t.c.ticket_number.contains(q,autoescape=True),t.c.description.contains(q,autoescape=True)))
            total=conn.execute(sa.select(sa.func.count()).select_from(query.subquery())).scalar_one()
            items=[dict(v) for v in conn.execute(query.order_by(t.c.submitted_at.desc(),t.c.id).offset((max(page,1)-1)*page_size).limit(page_size)).mappings()]
            return output({'items':items,'total':total,'page':max(page,1),'page_size':page_size})

    @app.post('/api/tickets')
    def tickets_create(request:Request,body:dict):
        with engine.begin() as conn:return output(tickets.create(conn,current_user(conn,request),body,request.headers.get('idempotency-key','')),201)

    @app.get('/api/tickets/{key}')
    def tickets_detail(request:Request,key:str):
        with engine.begin() as conn:return output(tickets.details(conn,current_user(conn,request),key))

    @app.post('/api/tickets/{key}/actions')
    def tickets_action(request:Request,key:str,body:dict):
        with engine.begin() as conn:return output(tickets.action(conn,current_user(conn,request),key,body))

    @app.put('/api/tickets/{key}')
    def tickets_edit(request:Request,key:str,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);old=tickets.ticket(conn,key,user,'ticket.edit')
            if old['status']!='pending':fail('接单后请通过留言补充，不直接修改问题描述',409)
            values={'title':tickets.text(body.get('title'),'标题',200,True),'description':tickets.text(body.get('description'),'问题描述',required=True)}
            tickets.update_parent(conn,old,values,body.get('version'),user);tickets.event(conn,old,None,user,'edited','问题描述已补充')
            audit(conn,user,'ticket.edit','tickets',key)
            return output(dict(row(conn,'tickets',key)))

    @app.post('/api/tickets/{key}/events')
    def tickets_comment(request:Request,key:str,body:dict):
        with engine.begin() as conn:return output(tickets.comment(conn,current_user(conn,request),key,body),201)

    @app.get('/api/catalog')
    def catalog_schema(request:Request):
        with engine.begin() as conn:
            user=current_user(conn,request)
            return output({'modules':[{'table':name,'module':mod,'title':catalog.title(name),'pk':SPECS[name]['pk'],
                'fields':catalog.fields(name),'has_version':'version' in T[name].c,'actions':[a for a in ['view','create','edit','archive','import','export','delete','publish'] if not ((name=='announcements' or name in BASIC_DATA_NO_TRANSFER) and a in ('import','export')) and allow(conn,user,mod+'.'+a)]}
                for name,mod in catalog.MODULES.items() if allow(conn,user,mod+'.view') or allow(conn,user,mod+'.edit')]})

    @app.get('/api/data/{name}')
    def data_list(request:Request,name:str,page:int=1,page_size:int=10,q:str='',archived:bool=False,kind:str='',status:str=''):
        if page_size not in (10,20,50):fail('每页条数仅支持 10、20、50',422)
        with engine.begin() as conn:
            user=current_user(conn,request);mod=catalog.module(name);require(conn,user,mod+'.view')
            table=T[name];query=sa.select(table).where(catalog.scope_expression(conn,user,mod+'.view',table))
            if 'is_archived' in table.c:query=query.where(table.c.is_archived==archived)
            if name=='resources' and kind:query=query.where(table.c.resource_kind==kind)
            if name=='announcements' and status:
                if status not in ('published','draft'):fail('公告状态筛选无效')
                query=query.where(table.c.publication_state==status)
            if q:
                cols=[table.c[f['name']] for f in SPECS[name]['fields'] if f['type'].startswith('u') or f['name'].endswith('_code') or f['name']=='code']
                if cols:query=query.where(sa.or_(*[c.contains(q,autoescape=True) for c in cols]))
            total=conn.execute(sa.select(sa.func.count()).select_from(query.subquery())).scalar_one()
            pk=SPECS[name]['pk']
            order=(table.c.published_at.desc(),table.c.updated_at.desc(),table.c[pk].desc()) if name=='announcements' else (table.c[pk],)
            items=[dict(v) for v in conn.execute(query.order_by(*order).offset((max(1,page)-1)*page_size).limit(page_size)).mappings()]
            if name=='departments':
                links=conn.execute(sa.select(T['organization_external_links'].c.local_id,T['organization_external_links'].c.source_code).where(
                    T['organization_external_links'].c.entity_type=='department',T['organization_external_links'].c.source_code.in_(('ehr','ldap')))).all();linked={}
                for local_id,source_code in links:linked.setdefault(local_id,set()).add(source_code)
                for item in items:
                    sources=linked.get(item['id'],set());item['source_type']='ehr' if 'ehr' in sources else 'ldap' if 'ldap' in sources else 'manual'
            if pk=='resource_id':
                for item in items:item['version']=row(conn,'resources',item['resource_id'])['version']
            return output({'items':items,'total':total,'page':max(1,page),'page_size':page_size})

    @app.get('/api/options/{name}')
    def data_options(request:Request,name:str):
        with engine.begin() as conn:
            user=current_user(conn,request)
            if name=='users':
                if not any(allow(conn,user,v) for v in ('user.view','ticket.assign','resource.edit','resource.create')):fail('无权读取用户选项',403)
                t=T[name];items=conn.execute(sa.select(t.c.id,t.c.display_name.label('name'),t.c.login_name.label('code')).where(t.c.is_archived==False,t.c.account_state=='active').order_by(t.c.display_name).limit(1000)).mappings()
                return output(list(items))
            mod=catalog.module(name);require(conn,user,mod+'.view');t=T[name];pk=SPECS[name]['pk']
            query=sa.select(t).where(catalog.scope_expression(conn,user,mod+'.view',t))
            if 'is_archived' in t.c:query=query.where(t.c.is_archived==False)
            rows=conn.execute(query.order_by(t.c[pk]).limit(5000)).mappings()
            return output([{'id':v[pk],'name':v.get('name') or v.get('title') or v.get('ssid') or v.get('label') or v.get('address') or str(v.get('vlan_number','')) or v[pk],
                'code':v.get('code') or v.get('resource_code') or v.get('scope_code') or ''} for v in rows])

    @app.post('/api/data/{name}')
    def data_create(request:Request,name:str,body:dict):
        with engine.begin() as conn:return output(catalog.save(conn,current_user(conn,request),name,body),201)

    @app.get('/api/resources/{key}/full')
    def resource_full(request:Request,key:str):
        with engine.begin() as conn:
            user=current_user(conn,request);parent=row(conn,'resources',key)
            if not parent:fail('资源不存在',404)
            require(conn,user,'resource.view',parent)
            names={'device':'devices','circuit':'circuits','vlan':'vlans','subnet':'subnets','wifi':'wifi_networks','vpn':'vpn_connections'}
            return output({'resource':dict(parent),'details':dict(row(conn,names[parent['resource_kind']],key) or {})})

    @app.post('/api/resources/{kind}')
    def resource_create(request:Request,kind:str,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);names={'device':'devices','circuit':'circuits','vlan':'vlans','subnet':'subnets','wifi':'wifi_networks','vpn':'vpn_connections'}
            if kind not in names:fail('资源类型无效')
            parent=catalog.save(conn,user,'resources',{**body.get('resource',{}),'resource_kind':kind})
            detail={**body.get('details',{}),'resource_id':parent['id']}
            if kind=='wifi':detail['site_id']=parent['site_id']
            child=catalog.save(conn,user,names[kind],detail)
            return output({'resource':parent,'details':child},201)

    @app.put('/api/resources/{key}/full')
    def resource_edit(request:Request,key:str,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);old=row(conn,'resources',key)
            if not old:fail('资源不存在',404)
            names={'device':'devices','circuit':'circuits','vlan':'vlans','subnet':'subnets','wifi':'wifi_networks','vpn':'vpn_connections'}
            parent=catalog.save(conn,user,'resources',body.get('resource',{}),key)
            detail={**body.get('details',{}),'resource_id':key,'version':parent['version']}
            if old['resource_kind']=='wifi':detail['site_id']=parent['site_id']
            table=names[old['resource_kind']];child=catalog.save(conn,user,table,detail,key if row(conn,table,key) else None)
            return output({'resource':dict(row(conn,'resources',key)),'details':child})

    @app.put('/api/data/{name}/{key}')
    def data_update(request:Request,name:str,key:str,body:dict):
        with engine.begin() as conn:return output(catalog.save(conn,current_user(conn,request),name,body,key))

    @app.post('/api/data/{name}/{key}/publish')
    def data_publish(request:Request,name:str,key:str,body:dict):
        with engine.begin() as conn:return output(catalog.publish(conn,current_user(conn,request),name,key,body))

    @app.post('/api/data/{name}/{key}/archive')
    def data_archive(request:Request,name:str,key:str,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);mod=catalog.module(name);old=row(conn,name,key)
            if not old:fail('记录不存在',404)
            require(conn,user,mod+'.archive',catalog.contextual(conn,name,old))
            if 'is_archived' not in T[name].c:fail('子记录请通过父资源归档')
            archive=body.get('archive')
            if not isinstance(archive,bool):fail('归档状态无效')
            checked_version(conn,name,old,body,{'is_archived':archive,'archived_at':utcnow() if archive else None,'archived_by_user_id':user['id'] if archive else None},user)
            audit(conn,user,mod+'.archive',name,key);return output({'ok':True})

    @app.delete('/api/data/{name}/{key}')
    def data_delete(request:Request,name:str,key:str,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);mod=catalog.module(name);old=row(conn,name,key)
            if not old:fail('记录不存在',404)
            require(conn,user,mod+'.delete',catalog.contextual(conn,name,old))
            reason=tickets.text(body.get('reason'),'删除原因',1024,True)
            if body.get('confirm')!=key:fail('请确认要永久删除的记录')
            if name=='announcements' and old['publication_state']=='published':fail('请先撤下公告再删除')
            if 'version' in old and body.get('version')!=old['version']:fail('记录已变化',409)
            if name=='ticket_categories':
                for table in T.values():
                    for column in table.c:
                        if any(fk.target_fullname=='ticket_categories.id' for fk in column.foreign_keys):
                            if conn.execute(sa.select(column).where(column==key).limit(1)).first():fail('此分类已被工单、历史记录或下级分类使用，不能删除；可在编辑中将“启用”设为“否”',409)
            if name=='departments':
                references=[('departments','parent_id','下级部门'),('users','department_id','人员'),('computer_assets','department_id','电脑设备'),
                    ('static_ip_records','department_id','静态 IP'),('role_permission_departments','department_id','角色数据范围')]
                used=[]
                for table_name,column,label in references:
                    if conn.execute(sa.select(T[table_name].c[column]).where(T[table_name].c[column]==key).limit(1)).first():used.append(label)
                if used:fail('该部门仍被'+ '、'.join(used) +'引用，请先调整关联数据',409)
                conn.execute(T['organization_external_links'].delete().where(T['organization_external_links'].c.entity_type=='department',T['organization_external_links'].c.local_id==key))
            if name=='announcements':
                relations=list(conn.execute(sa.select(T['announcement_files']).where(T['announcement_files'].c.announcement_id==key)).mappings())
                file_ids=[v['file_id'] for v in relations]
                files=list(conn.execute(sa.select(T['file_objects']).where(T['file_objects'].c.id.in_(file_ids))).mappings()) if file_ids else []
                conn.execute(T['notifications'].delete().where(T['notifications'].c.announcement_id==key))
                conn.execute(T['announcement_files'].delete().where(T['announcement_files'].c.announcement_id==key))
                if file_ids:conn.execute(T['file_objects'].delete().where(T['file_objects'].c.id.in_(file_ids)))
                for file in files:storage.delete(file['storage_key'],file['purpose'])
            t=T[name];conn.execute(t.delete().where(t.c[SPECS[name]['pk']]==key))
            audit(conn,user,mod+'.delete',name,key,reason=reason);return output({'ok':True})

    @app.get('/api/import-templates/{name}')
    def template_download(request:Request,name:str):
        with engine.begin() as conn:
            if name=='announcements':fail('公告不提供导入模板',404)
            if name in BASIC_DATA_NO_TRANSFER:fail('基础资料不提供导入模板',404)
            user=current_user(conn,request);require(conn,user,catalog.module(name)+'.import')
            return Response(transfers.workbook(name),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename="{name}-template-v1.xlsx"'})

    @app.get('/api/exports/{name}')
    def export(request:Request,name:str,q:str=''):
        with engine.begin() as conn:
            if name=='announcements':fail('公告不提供数据导出',404)
            if name in BASIC_DATA_NO_TRANSFER:fail('基础资料不提供数据导出',404)
            user=current_user(conn,request);mod=catalog.module(name);require(conn,user,mod+'.export');t=T[name]
            query=sa.select(t).where(catalog.scope_expression(conn,user,mod+'.export',t))
            if 'is_archived' in t.c:query=query.where(t.c.is_archived==False)
            if q:
                cols=[t.c[f['name']] for f in SPECS[name]['fields'] if f['type'].startswith('u')]
                if cols:query=query.where(sa.or_(*[c.contains(q,autoescape=True) for c in cols]))
            items=[dict(v) for v in conn.execute(query.order_by(t.c[SPECS[name]['pk']]).limit(50001)).mappings()]
            if len(items)>50000:fail('结果超过 50000 条，请缩小范围')
            result=transfers.workbook(name,items,conn);audit(conn,user,mod+'.export',name,changes={'count':len(items)})
            return Response(result,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename="{name}-data.xlsx"'})

    @app.post('/api/imports/{name}')
    def import_preview(request:Request,name:str,file:UploadFile=File(...),mode:str=Form('create_only')):
        with engine.begin() as conn:
            if name=='announcements':fail('公告不提供数据导入',404)
            if name in BASIC_DATA_NO_TRANSFER:fail('基础资料不提供数据导入',404)
            user=current_user(conn,request);raw=file.file.read(transfers.MAX_BYTES+1)
            batch=transfers.preview(conn,user,name,raw,file.filename or '',mode)
            return output(batch,201)

    @app.get('/api/imports/batches/{key}')
    def import_rows(request:Request,key:str):
        with engine.begin() as conn:
            user=current_user(conn,request);batch=row(conn,'import_batches',key)
            if not batch or batch['requested_by_user_id']!=user['id']:fail('批次不存在',404)
            info=json.loads(batch['summary_json']);require(conn,user,catalog.module(info['module'])+'.import')
            t=T['import_rows'];rows=[dict(v) for v in conn.execute(sa.select(t).where(t.c.batch_id==key).order_by(t.c.source_row_key)).mappings()]
            return output({'batch':dict(batch),'rows':rows})

    @app.post('/api/imports/batches/{key}/commit')
    def import_confirm(request:Request,key:str,body:dict):
        with engine.begin() as conn:return output(transfers.commit(conn,current_user(conn,request),key,body.get('valid_only') is True))

    # Knowledge and reports are registered below, before the static application.
    ledger.register(app,engine,output,current_user,folder)
    ipam.register(app,engine,output,current_user)
    consumables.register(app,engine,output,current_user)
    memos.register(app,engine,output,current_user)
    ai.register(app,engine,output,logger)
    register_content(app,engine,folder,config,storage,logger)
    app.mount('/assets',StaticFiles(directory=ROOT/'portal_static'),name='assets')

    @app.get('/')
    def index():return FileResponse(ROOT/'portal_static'/'index.html')

    return app
