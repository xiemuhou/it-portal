"""Whitelisted business CRUD; the same validation is used by screens and imports."""
from datetime import date
from decimal import Decimal, InvalidOperation
import ipaddress
import json
import re
import sqlalchemy as sa

from .database import TABLES as T, SPECS, insert_row, row, utcnow, uid
from .security import fail, require, allow, grants, audit, digest
from .tickets import time_value

MODULES={
    'sites':'directory','departments':'directory',
    'network_scopes':'resource',
    'resources':'resource','devices':'resource','device_identifiers':'resource','device_interfaces':'resource',
    'device_endpoints':'resource','device_relations':'resource','circuits':'resource','circuit_endpoints':'resource',
    'vlans':'resource','subnets':'resource','subnet_gateways':'resource','wifi_networks':'resource','wifi_vlan_bindings':'resource',
    'vpn_connections':'resource','vpn_tunnels':'resource','vpn_routes':'resource','contracts':'resource','resource_contracts':'resource',
    'ticket_categories':'category','knowledge_categories':'knowledge','announcements':'announcement',
    'service_catalog':'directory',
}
MODULES={k:v for k,v in MODULES.items() if k in T}
LABELS={'id':'内部标识','resource_id':'资源编号','code':'业务编码','name':'名称','resource_code':'资源编号',
    'site_id':'站点','department_id':'部门','location_id':'位置','owner_user_id':'责任人','resource_kind':'资源类型',
    'lifecycle_status':'生命周期','verification_status':'核对状态','title':'标题','summary':'摘要','body':'正文',
    'publication_state':'发布状态','is_enabled':'启用','is_pinned':'置顶','sort_order':'排序','expires_at':'截止时间',
    'published_at':'发布时间','published_by_user_id':'发布人',
    'scope_id':'网络域','vlan_number':'VLAN编号','ssid':'SSID','device_type_code':'设备类型','manufacturer':'厂商',
    'model':'型号','hostname':'主机名','address':'地址','port':'端口','purpose':'用途','vendor_id':'供应商',
    'circuit_number':'线路号','downstream_mbps':'下行带宽Mbps','upstream_mbps':'上行带宽Mbps','role_code':'线路角色',
    'site_type':'站点类型','announcement_code':'公告编号','description':'说明','parent_id':'上级',
    'alias_name':'站点别名','connection_type':'连接类型','remote_site_id':'对端站点','remote_label':'对端名称',
    'is_published':'公开发布','service_code':'服务编号','project_code':'项目编号'}
ENUMS={
    'resource_kind':['device','circuit','vlan','subnet','wifi','vpn'],
    'lifecycle_status':['unknown','in_use','standby','maintenance','retired'],
    'verification_status':['draft','verified'],'publication_state':['draft','published','withdrawn'],
    'role_code':['primary','backup','unknown'],'registered_state':['unknown','up','down'],
    'connection_type':['site_to_site','aws','other'],
}
READONLY={'id','created_at','updated_at','created_by_user_id','updated_by_user_id','version','is_archived','archived_at','archived_by_user_id',
          'verified_at','verified_by_user_id','published_at','published_by_user_id','ssid_key','alias_key','cidr_key'}
AUTO_CODES={'code','resource_code','scope_code','announcement_code','service_code','project_code'}


def generated_code(name):
    return name.upper()[:12]+'-'+uid().replace('-','').upper()


def title(name):
    return SPECS[name]['title'].replace('站点','区域')


def scope_expression(conn,user,permission,table):
    parent_columns=[]
    if table.name!='resources' and table.name in SPECS:
        parent_columns=[table.c[f['name']] for f in SPECS[table.name]['fields'] if f['ref'] and f['ref'].split('.')[0] in ('resources','devices','circuits','vlans','subnets','wifi_networks','vpn_connections')]
    if parent_columns:
        permitted=sa.select(T['resources'].c.id).where(scope_expression(conn,user,permission,T['resources']))
        return sa.and_(*[sa.or_(c.is_(None),c.in_(permitted)) for c in parent_columns])
    expressions=[]
    for grant in grants(conn,user).get(permission,[]):
        scope=grant['scope']
        if scope=='all' or (scope=='none' and MODULES.get(table.name) in ('directory','category','knowledge','announcement')):
            return sa.true()
        key='requester_user_id' if 'requester_user_id' in table.c else 'created_by_user_id'
        if scope=='own' and key in table.c:expressions.append(table.c[key]==user['id'])
        owner='assignee_user_id' if 'assignee_user_id' in table.c else 'owner_user_id'
        if scope=='assigned' and owner in table.c:expressions.append(table.c[owner]==user['id'])
        if scope=='site':
            allowed=T['role_permission_sites']; sites=sa.select(allowed.c.site_id).where(allowed.c.role_permission_id==grant['id'])
            if 'site_id' in table.c:expressions.append(table.c.site_id.in_(sites))
            elif 'resource_id' in table.c:expressions.append(table.c.resource_id.in_(sa.select(T['resources'].c.id).where(T['resources'].c.site_id.in_(sites))))
        if scope=='department' and table.name=='tickets':
            allowed=T['role_permission_departments']; departments=sa.select(allowed.c.department_id).where(allowed.c.role_permission_id==grant['id'])
            expressions.append(table.c.requester_user_id.in_(sa.select(T['users'].c.id).where(T['users'].c.department_id.in_(departments))))
    return sa.or_(*expressions) if expressions else sa.false()


def module(name):
    if name not in MODULES:fail('此模块不支持通用维护',404)
    return MODULES[name]


def fields(name):
    module(name)
    result=[]
    for f in SPECS[name]['fields']:
        if f['name'] in READONLY:continue
        item=dict(f);item['label']=LABELS.get(f['name'],f['description'].split('；')[0].split('，')[0][:18])
        item['header']=item['label']+'（'+f['name']+'）'
        item['enum']=ENUMS.get(f['name'],[])
        item['ui_hidden']=f['name'] in AUTO_CODES or f['name']=='sort_order' or (name=='sites' and f['name']=='site_type') or (name=='locations' and f['name']=='location_type')
        item['ui_form_hidden']=f['name']=='publication_state'
        item['auto_generated']=f['name'] in AUTO_CODES
        # Keep template headers compatible with existing exports; UI terminology is independent.
        item['label']=item['label'].replace('站点','区域')
        item['description']=item['description'].replace('站点','区域')
        if name=='announcements' and f['name']=='expires_at':item['description']='可选；留空则长期展示。设置截止时间后，过期公告会自动从公开页面隐藏。'
        if f['name']=='publication_state':item['enum']=['draft','withdrawn']
        result.append(item)
    if name=='announcements':
        for field_name in ('published_at','published_by_user_id'):
            f=next(v for v in SPECS[name]['effective_fields'] if v['name']==field_name)
            item=dict(f);item.update(label=LABELS[field_name],header=LABELS[field_name]+'（'+field_name+'）',enum=[],ui_hidden=False,ui_form_hidden=True,auto_generated=True)
            result.append(item)
    return result


def contextual(conn,name,obj):
    result=dict(obj)
    if name!='resources':
        for f in SPECS[name]['fields']:
            if f['ref'] and f['ref'].split('.')[0] in ('resources','devices','circuits','vlans','subnets','wifi_networks','vpn_connections') and result.get(f['name']):
                parent=row(conn,'resources',result[f['name']])
                if parent:
                    result={**dict(parent),**result,'created_by_user_id':parent['created_by_user_id'],'owner_user_id':parent['owner_user_id'],'site_id':parent['site_id']}
                    break
    return result


def convert(value,f):
    kind=f['type']; label=LABELS.get(f['name'],f['name'])
    if value is None or value=='':
        if f['nullable']:return None
        fail(label+'为必填项')
    try:
        if kind=='bool':
            if value in (True,1,'1','true','是','启用'):return True
            if value in (False,0,'0','false','否','停用'):return False
            fail(label+'必须为是或否')
        if kind in ('int','bigint'):
            if isinstance(value,bool) or str(value).strip()!=str(int(value)):fail(label+'必须为整数')
            return int(value)
        if kind.startswith('decimal'):
            result=Decimal(str(value))
            scale=3 if kind=='decimal12_3' else 2
            if not result.is_finite() or result<0 or result.as_tuple().exponent < -scale:fail(label+'精度或数值无效')
            if result>=Decimal(10)**(9 if kind=='decimal12_3' else 16):fail(label+'超出范围')
            return result
        if kind=='date':return date.fromisoformat(value.isoformat()[:10] if hasattr(value,'isoformat') else str(value))
        if kind=='utc':return time_value(value)
        if kind=='json':return json.dumps(json.loads(value) if isinstance(value,str) else value,ensure_ascii=False)
        if not isinstance(value,str):value=str(value)
        value=value.strip()
        if not value or '\x00' in value:fail(label+'不能为空')
        if kind.startswith(('a','u')) and kind[1:].isdigit():
            if len(value.encode('utf-16-le'))//2>int(kind[1:]):fail(label+'长度超限')
            if kind.startswith('a') and not value.isascii():fail(label+'仅允许英文编码字符')
        if kind=='id' and not re.fullmatch(r'[0-9a-f-]{36}',value):fail(label+'请选择已有对象')
        if value in ENUMS.get(f['name'],[]) or f['name'] not in ENUMS:return value
        fail(label+'不在允许选项内')
    except (ValueError,TypeError,InvalidOperation,OverflowError):fail(label+'格式无效')


def validate(conn,user,name,body,old=None,from_import=False):
    allowed={f['name']:f for f in fields(name)}
    if any(k not in allowed and k!='version' for k in body):fail('请求包含不允许维护的字段')
    values={k:convert(v,allowed[k]) for k,v in body.items() if k in allowed}
    if not old:
        for k in allowed:
            if k in AUTO_CODES and k not in values:values[k]=generated_code(name)
        defaults={'is_enabled':True,'sort_order':0,'is_pinned':False,'publication_state':'draft','is_published':False,
                  'lifecycle_status':'unknown','verification_status':'draft','site_type':'other','location_type':'other','role_code':'unknown','registered_state':'unknown'}
        for k,f in allowed.items():
            if k not in values and not f['nullable']:
                if k in defaults:values[k]=defaults[k]
                else:fail(LABELS.get(k,f['description'][:18])+'为必填项')
    combined={**dict(old or {}),**values}
    for k,f in allowed.items():
        value=combined.get(k)
        if f['ref'] and value:
            target=f['ref'].split('.')[0]
            obj=row(conn,target,value)
            if not obj or obj.get('is_archived',False):fail(LABELS.get(k,k)+'关联不存在或已归档')
            if target=='users' and obj['account_state']!='active':fail('关联用户已停用')
            if target=='resources':require(conn,user,'resource.view',obj)
            elif target in MODULES and MODULES[target]=='resource':require(conn,user,'resource.view',contextual(conn,target,obj))
    if 'publication_state' in values and values['publication_state']=='published':fail('请使用独立发布操作')
    if name=='announcements' and combined.get('publication_state')=='published' and combined.get('expires_at') and combined['expires_at']<=utcnow():fail('公告截止时间已过，请清空截止时间或选择未来时间')
    if from_import and 'publication_state' in allowed:values['publication_state']='draft'
    if 'is_published' in values and values['is_published'] and not allow(conn,user,'directory.edit'):fail('没有发布权限',403)
    if name=='resources':
        if old and values.get('resource_kind',old['resource_kind'])!=old['resource_kind']:fail('资源类型创建后不能更换')
        if combined.get('verification_status')=='verified':values.update(verified_at=utcnow(),verified_by_user_id=user['id'])
    if name in ('devices','circuits','vlans','subnets','wifi_networks','vpn_connections'):
        parent=row(conn,'resources',combined['resource_id'])
        kind={'devices':'device','circuits':'circuit','vlans':'vlan','subnets':'subnet','wifi_networks':'wifi','vpn_connections':'vpn'}[name]
        if parent['resource_kind']!=kind:fail('资源类型与详情模块不匹配')
        if 'site_id' in combined and combined['site_id']!=parent['site_id']:fail('区域须与资源一致')
    if combined.get('scope_id') and combined.get('resource_id'):
        scope=row(conn,'network_scopes',combined['scope_id']);parent=row(conn,'resources',combined['resource_id'])
        if scope['site_id']!=parent['site_id']:fail('网络域与资源所属区域不一致')
    if name=='vlans' and not 1<=combined['vlan_number']<=4094:fail('VLAN 编号须为 1～4094')
    if name=='wifi_networks':
        if len(combined['ssid'].encode('utf-8'))>32:fail('SSID 不得超过 32 字节')
        values['ssid_key']=digest(combined['ssid'])
    if name=='site_aliases':values['alias_key']=digest(combined['alias_name'])
    if name=='subnets':
        try:
            network=ipaddress.ip_network(f"{combined['network_address']}/{combined['prefix_length']}",strict=True)
            if network.version!=combined['ip_version']:fail('IP 版本与网段不一致')
            values['cidr_key']=str(network)
        except ValueError:fail('网段或掩码无效，网络地址须规范填写')
    for k in ('local_gateway','remote_gateway','gateway_address','ip_address'):
        if combined.get(k):
            try:ipaddress.ip_address(combined[k])
            except ValueError:fail('IP 地址格式无效')
    for k in ('port',):
        if combined.get(k) is not None and not 1<=combined[k]<=65535:fail('端口须为 1～65535')
    for a,b in [('warranty_start','warranty_end'),('start_date','finish_date'),('start_date','end_date')]:
        if combined.get(a) and combined.get(b) and combined[a]>combined[b]:fail('结束日期不得早于开始日期')
    if old and name in ('departments','locations','ticket_categories','knowledge_categories') and combined.get('parent_id'):
        seen={old['id']};p=combined['parent_id']
        while p:
            if p in seen:fail('上级关系不能形成循环')
            seen.add(p);obj=row(conn,name,p);p=obj.get('parent_id') if obj else None
    return values


def save(conn,user,name,body,key=None,from_import=False,expected_version=None):
    mod=module(name); permission=mod+'.'+('edit' if key else 'create')
    if mod not in ('resource','user'):permission=mod+'.edit'
    old=row(conn,name,key) if key else None
    if key and not old:fail('记录不存在',404)
    # Authorization must use the ORIGINAL scope, never a client-supplied new owner/site.
    if old:require(conn,user,permission,contextual(conn,name,old))
    values=validate(conn,user,name,body,old,from_import)
    context=contextual(conn,name,{**dict(old or {}),**values,'created_by_user_id':old['created_by_user_id'] if old and 'created_by_user_id' in old else user['id']})
    if not old:require(conn,user,permission,context)
    # Related resource parameters inherit their parent's scope. A child-row creator
    # must not obtain authority over somebody else's resource by creating a link.
    for f in SPECS[name]['fields']:
        if f['ref'] and f['ref'].split('.')[0] in ('resources','devices','circuits','vlans','subnets','wifi_networks','vpn_connections'):
            key_value=values.get(f['name'],old.get(f['name']) if old else None)
            if key_value:
                parent=row(conn,'resources',key_value)
                if parent:require(conn,user,permission,parent)
    if old:
        t=T[name];pk=SPECS[name]['pk']
        q=t.update().where(t.c[pk]==key)
        if 'version' in t.c:
            ver=expected_version if expected_version is not None else body.get('version')
            if ver!=old['version']:fail('记录已变化，请刷新后重试',409)
            q=q.where(t.c.version==ver);values.update(version=ver+1,updated_at=utcnow(),updated_by_user_id=user['id'])
        elif 'resource_id' in t.c:
            parent=row(conn,'resources',key)
            ver=expected_version if expected_version is not None else body.get('version')
            if ver!=parent['version']:fail('资源已变化，请刷新',409)
            result=conn.execute(T['resources'].update().where(T['resources'].c.id==key,T['resources'].c.version==ver).values(version=ver+1,updated_at=utcnow(),updated_by_user_id=user['id']))
            if result.rowcount!=1:fail('资源修改冲突',409)
        result=conn.execute(q.values(**values))
        if result.rowcount!=1:fail('记录已变化，请刷新后重试',409)
        result=dict(row(conn,name,key))
    else:result=insert_row(conn,name,values,user['id'])
    audit(conn,user,mod+'.'+('edit' if key else 'create'),name,str(result[SPECS[name]['pk']]),{'fields':list(values)})
    return result


def publish(conn,user,name,key,body):
    mod=module(name); require(conn,user,mod+'.publish')
    if name!='announcements':fail('此模块使用专用发布流程')
    old=row(conn,name,key)
    if not old:fail('公告不存在',404)
    state=body.get('state')
    if state not in ('published','withdrawn'):fail('发布状态无效')
    t=T[name]
    if old['version']!=body.get('version'):fail('公告已变化，请刷新',409)
    if state=='published' and old['is_archived']:fail('请先恢复已归档的内容')
    if name=='announcements' and state=='published' and old['expires_at'] and old['expires_at']<=utcnow():fail('公告截止时间已过，请先编辑并清空截止时间，或选择未来时间后再发布')
    values={'publication_state':state,'published_at':utcnow() if state=='published' else old['published_at'],
            'updated_at':utcnow(),'updated_by_user_id':user['id'],'version':old['version']+1}
    if 'published_by_user_id' in t.c:values['published_by_user_id']=user['id']
    count=conn.execute(t.update().where(t.c.id==key,t.c.version==old['version']).values(**values)).rowcount
    if count!=1:fail('公告修改冲突',409)
    if name=='announcements' and state=='published':
        users=T['users'];recipients=list(conn.execute(sa.select(users.c.id).where(users.c.is_archived==False,users.c.account_state=='active')).scalars())
        for recipient_id in recipients:
            insert_row(conn,'notifications',{'recipient_user_id':recipient_id,
                'event_key':f'announcement:{key}:{old["version"]+1}','announcement_id':key,
                'title':'新公告：'+old['title'],'message_text':'公司发布了新公告，请查看公告详情。','read_at':None},user['id'])
    audit(conn,user,'announcement.'+state,name,key)
    return dict(row(conn,name,key))
