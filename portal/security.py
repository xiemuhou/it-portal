"""Passwords, sessions and per-operation data scopes. No credentials in responses/logs."""
from datetime import timedelta
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import time
import threading

from fastapi import HTTPException
import sqlalchemy as sa
from .database import TABLES as T, insert_row, row, utcnow
from .operations import current_request_id


def fail(message, code=422):
    raise HTTPException(code, message)


def password_hash(password):
    if not isinstance(password, str) or not 8 <= len(password) <= 256:
        fail('密码长度必须为 8～256 位')
    salt = secrets.token_hex(16)
    return f'pbkdf2_sha256$600000${salt}$' + hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()


def verify(password, encoded):
    try:
        algorithm, count, salt, digest = encoded.split('$')
        return algorithm == 'pbkdf2_sha256' and hmac.compare_digest(digest, hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(count)).hex())
    except (ValueError, TypeError, AttributeError):
        return False


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def csrf(token):
    return hmac.new(token.encode(), b'portal-csrf-v2', 'sha256').hexdigest()


FUNCTIONAL = {'user', 'role', 'category', 'settings', 'audit', 'knowledge', 'announcement', 'directory', 'quicklink', 'consumable', 'memo'}
PERMISSIONS = {}
for module, actions in {
    'ticket': 'view create edit comment internal_note claim assign transfer close cancel reopen correct export delete',
    'resource': 'view create edit archive import export delete',
    'user': 'view create edit password roles import export delete',
    'role': 'view edit', 'category': 'view edit import export delete',
    'knowledge': 'view edit publish import export delete',
    'announcement': 'view edit publish delete',
    'directory': 'view edit publish import export delete',
    'report': 'view export', 'audit': 'view', 'settings': 'edit',
    'quicklink': 'edit delete', 'consumable': 'view edit receive issue', 'memo': 'view edit secret_view delete',
}.items():
    for action in actions.split():
        PERMISSIONS[f'{module}.{action}'] = (module, module not in FUNCTIONAL)


def audit(conn, actor, action, target_type, target_id=None, changes=None, reason=None):
    insert_row(conn, 'audit_logs', {'actor_user_id': actor['id'] if actor else None,
        'actor_name_snapshot': actor['display_name'] if actor else '系统', 'action_code': action,
        'target_type': target_type, 'target_id': target_id, 'request_id': current_request_id(),
        'occurred_at': utcnow(), 'result_code': 'success',
        'changes_json': json.dumps(changes, ensure_ascii=False, default=str) if changes else None, 'reason': reason})


def seed(conn, data_dir):
    """Only initial dictionaries/admin. No sample tickets, announcements or resources."""
    if conn.execute(sa.select(T['users'].c.id).limit(1)).first():
        existing={r[0] for r in conn.execute(sa.select(T['permissions'].c.code))}
        admin_role=conn.execute(sa.select(T['roles']).where(T['roles'].c.code=='admin')).mappings().one()
        it_role=conn.execute(sa.select(T['roles']).where(T['roles'].c.code=='it')).mappings().first()
        for code,(module,scoped) in PERMISSIONS.items():
            if code in existing:continue
            permission=insert_row(conn,'permissions',{'code':code,'name':code,'module_code':module,'supports_data_scope':scoped})
            insert_row(conn,'role_permissions',{'role_id':admin_role['id'],'permission_id':permission['id'],'data_scope':'all' if scoped else 'none'})
            if module in ('consumable','memo') and it_role:
                insert_row(conn,'role_permissions',{'role_id':it_role['id'],'permission_id':permission['id'],'data_scope':'none'})
        return
    department = insert_row(conn, 'departments', {'code':'it', 'name':'IT', 'is_enabled':True})
    admin = insert_row(conn, 'users', {'login_name':'admin', 'display_name':'系统管理员', 'department_id':department['id'],
        'password_hash':password_hash(os.getenv('IT_PORTAL_BOOTSTRAP_PASSWORD') or (initial := secrets.token_urlsafe(12))),
        'account_state':'active', 'auth_version':1})
    # Environment-supplied passwords never appear in the handover file.
    if not os.getenv('IT_PORTAL_BOOTSTRAP_PASSWORD'):
        folder = Path(data_dir); folder.mkdir(parents=True, exist_ok=True)
        p = folder / 'initial-account.txt'
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write('新版门户首次管理员账号：admin\n密码：' + initial + '\n请妥善交接并删除此文件。\n')
    roles = {}
    for code, name in [('employee','员工'),('it','IT 运维'),('admin','管理员')]:
        roles[code] = insert_row(conn, 'roles', {'code':code, 'name':name, 'is_builtin':True}, admin['id'])
    for code, (module, scoped) in PERMISSIONS.items():
        permission = insert_row(conn, 'permissions', {'code':code, 'name':code, 'module_code':module, 'supports_data_scope':scoped}, admin['id'])
        grants = {'admin':'all' if scoped else 'none'}
        if code in ('ticket.view','ticket.create','ticket.edit','ticket.comment','ticket.cancel','ticket.reopen','report.view'):
            grants['employee'] = 'own'
        if module in ('ticket','resource','report') and code not in ('ticket.delete','ticket.correct','resource.delete','resource.import'):
            grants['it'] = 'assigned' if code == 'ticket.close' else 'all'
        if code in ('category.view','category.edit','knowledge.view','knowledge.edit','knowledge.publish','directory.view'):
            grants['it'] = 'none'
        if module in ('consumable','memo'):grants['it']='none'
        for role_code, scope in grants.items():
            insert_row(conn, 'role_permissions', {'role_id':roles[role_code]['id'],'permission_id':permission['id'],'data_scope':scope}, admin['id'])
    insert_row(conn, 'user_roles', {'user_id':admin['id'],'role_id':roles['admin']['id']}, admin['id'])
    site = insert_row(conn, 'sites', {'code':'external_warehouse','name':'外仓','site_type':'warehouse','is_enabled':True}, admin['id'])
    for name in ['仓库','外仓','水南仓']:
        insert_row(conn,'site_aliases', {'site_id':site['id'], 'alias_name':name, 'alias_key':digest(name)},admin['id'])
    for i, name in enumerate(['账号与权限','电脑与软件','网络连接','打印与会议','文件与系统','其他']):
        insert_row(conn, 'ticket_categories', {'code':f'category_{i+1}','name':name,'is_enabled':True,'sort_order':i},admin['id'])
    insert_row(conn, 'knowledge_categories', {'code':'general','name':'通用手册','sort_order':0,'is_enabled':True},admin['id'])
    audit(conn, admin, 'system.initialized', 'system')


def grants(conn, user):
    if isinstance(user,dict) and '_permission_grants' in user:
        return user['_permission_grants']
    ur, rp, p, roles = (T[x] for x in ('user_roles','role_permissions','permissions','roles'))
    query = sa.select(p.c.code, rp.c.data_scope, rp.c.id).select_from(ur.join(roles,ur.c.role_id==roles.c.id).join(rp,rp.c.role_id==roles.c.id).join(p,rp.c.permission_id==p.c.id)).where(ur.c.user_id==user['id'],roles.c.is_archived==False,p.c.is_archived==False)
    result = {}
    for r in conn.execute(query).mappings():
        result.setdefault(r['code'],[]).append({'scope':r['data_scope'],'id':r['id']})
    if isinstance(user,dict):user['_permission_grants']=result
    return result


def allow(conn, user, permission, obj=None):
    gs = grants(conn,user).get(permission,[])
    if not gs:
        return False
    if obj is None:
        return True
    for g in gs:
        scope = g['scope']
        if scope == 'all' or (scope == 'none' and permission.split('.')[0] in FUNCTIONAL):
            return True
        if scope == 'own' and obj.get('requester_user_id',obj.get('created_by_user_id')) == user['id']:
            return True
        if scope == 'assigned' and obj.get('assignee_user_id',obj.get('owner_user_id')) == user['id']:
            return True
        if scope in ('site','department'):
            name = 'role_permission_sites' if scope == 'site' else 'role_permission_departments'
            key = 'site_id' if scope == 'site' else 'department_id'
            target = obj.get(key)
            if scope == 'department' and obj.get('requester_user_id'):
                owner = row(conn,'users',obj['requester_user_id']); target = owner['department_id'] if owner else None
            t = T[name]
            if target and conn.execute(sa.select(t.c.id).where(t.c.role_permission_id==g['id'],t.c[key]==target)).first():
                return True
    return False


def require(conn, user, permission, obj=None):
    if not user:
        fail('请先登录',401)
    if not allow(conn,user,permission,obj):
        fail('当前账号没有此操作或数据范围的权限',403)


def current_user(conn, request, optional=False):
    token = request.cookies.get('portal_v2_session','')
    s = T['user_sessions']; u = T['users']; now=utcnow()
    session = conn.execute(sa.select(s).where(s.c.token_hash==digest(token),s.c.revoked_at.is_(None),s.c.expires_at>now,s.c.idle_expires_at>now)).mappings().first() if token else None
    user = row(conn,'users',session['user_id']) if session else None
    if not user or user['account_state']!='active' or user['is_archived'] or user['auth_version']!=session['auth_version']:
        if optional:return None
        fail('登录已过期，请重新登录',401)
    if request.method not in ('GET','HEAD','OPTIONS'):
        origin=request.headers.get('origin')
        if origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):
            fail('拒绝跨站请求',403)
        supplied=request.headers.get('x-csrf-token','')
        if not hmac.compare_digest(digest(supplied),session['csrf_hash']):fail('请求校验失败，请刷新页面',403)
    if request.headers.get('x-portal-activity')=='1':
        conn.execute(s.update().where(s.c.id==session['id']).values(last_seen_at=now,idle_expires_at=now+timedelta(minutes=10)))
    return dict(user)


def public_user(conn,user,token=''):
    safe={k:user[k] for k in ('id','login_name','display_name','department_id','email','phone')}
    safe['grants']=grants(conn,user)
    safe['csrf']=csrf(token) if token else None
    return safe


_failures={}
_failure_lock=threading.Lock()
def login_limited(key):
    with _failure_lock:
        t=time.monotonic()
        _failures[key]=[v for v in _failures.get(key,[]) if v>t-600]
        if len(_failures[key])>=10:fail('尝试次数过多，请 10 分钟后重试',429)
        if len(_failures)>10000:_failures.clear()
        _failures.setdefault(key,[]).append(t)


def reset_failures(key):
    with _failure_lock:_failures.pop(key,None)
