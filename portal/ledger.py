"""Five task-oriented ledgers over the existing resource identities.

Profiles contain form-only details; links enforce references in both database engines.
Legacy subtype records remain readable and retain their IDs on first edit.
"""
from datetime import date
from io import BytesIO
import hashlib
import ipaddress
import json
import zipfile
from uuid import UUID,uuid5,NAMESPACE_URL
import sqlalchemy as sa
from fastapi import Request, UploadFile, File, Form
from fastapi.responses import Response
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from .database import TABLES as T, SPECS, insert_row, row, utcnow, jsonable, uid
from .security import require, allow, fail, audit
from . import catalog, ledger_secrets

KINDS={'vlan':('VLAN 规划','vlans'),'wifi':('Wi-Fi 规划','wifi_networks'),'device':('网络设备','devices'),
       'circuit':('带宽线路','circuits'),'vpn':('VPN 隧道','vpn_connections')}


def f(name,label,type='text',required=False,**extra):
    return dict(name=name,label=label,type=type,required=required,**extra)


COMMON=[f('site_id','区域','ref',True,target='sites'),f('name','名称',ui_hidden=True),f('enabled','启用','bool')]
SCHEMAS={
 'vlan':[f('vlan_number','VLAN ID','int',True),f('networks','网段与网关','rows',columns=[f('cidr','网段 CIDR'),f('gateway','网关'),f('purpose','网段用途'),f('ipam_enabled','静态 IP 管理','bool',default=False),f('network_id','网段编号',ui_hidden=True)]),f('scope_name','网络范围',advanced=True,help='默认 default；独立网络中存在相同 VLAN ID 时再区分。')],
 'wifi':[f('ssid','SSID','text',True),f('purpose','用途'),f('coverage','覆盖位置'),f('auth_method','认证方式','enum',options=['none','password','password_mac']),f('wifi_password','Wi-Fi 密码','secret'),f('vlan_ids','关联 VLAN','refs',target='vlan',ui_hidden=True),f('vlan_network_ids','关联 VLAN 网段','refs',target='vlan_network',dropdowns=True),f('ap_ids','关联 AP','refs',target='device',advanced=True)],
 'device':[f('device_type','设备类型'),f('model','设备型号'),f('manufacturer','品牌'),f('esn','ESN码'),f('uplink_device_id','上联设备','ref',target='device'),f('uplink_port','上联设备接口'),f('local_port','本机上联接口'),f('management_ip','管理 IP'),f('login_username','用户名'),f('login_password','密码','secret'),f('installation_location','安装位置'),f('is_stacked','是否堆叠','bool',default=False),f('warranty_start','维保开始日期','date'),f('warranty_end','维保结束日期','date')],
 'circuit':[f('vendor_name','运营商'),f('monthly_fee','月租费用（元）','decimal',step='0.01'),f('support_phone','保障电话'),f('lines','主线 / 赠送线路','rows',columns=[f('line_type','线路类型','enum',options=['primary','gift']),f('number','线路号'),f('downstream','下行 Mbps','decimal'),f('upstream','上行 Mbps','decimal')]),f('connections','线路接入明细','rows',ui_embedded=True,columns=[f('connection_id','接入编号',ui_hidden=True),f('line_type','所属线路','enum',options=['primary','gift']),f('connection_method','连接方式','enum',options=['route','bridge','pppoe']),f('ip_address','可用 IP'),f('mask','掩码 / 前缀长度'),f('gateway','网关'),f('interface','接入接口'),f('dial_username','拨号账号'),f('dial_password','拨号密码','secret'),f('purpose','用途')]),f('ont_username','光猫管理用户名'),f('ont_password','光猫管理密码','secret'),f('expires_on','到期时间','date')],
 'vpn':[f('local_network_mode','本地 VPN 网段','enum',options=['selected','any'],default='selected'),f('local_vlan_ids','本地 VLAN','refs',target='vlan',ui_hidden=True),f('local_vlan_network_ids','本地 VLAN 网段','refs',target='vlan_network',dropdowns=True),f('local_gateway','本地网关'),f('remote_site_id','对端区域','ref',target='sites',global_ref=True),f('remote_network_mode','对端 VPN 网段','enum',options=['selected','any'],default='selected'),f('remote_vlan_ids','对端 VLAN','refs',target='vlan',ui_hidden=True,site_field='remote_site_id'),f('remote_vlan_network_ids','对端 VLAN 网段','refs',target='vlan_network',dropdowns=True,site_field='remote_site_id'),f('remote_networks','手动补充对端网段','rows',columns=[f('cidr','网段 CIDR'),f('notes','网段备注')]),f('tunnels','隧道','rows',columns=[f('remote_gateway','对端网关'),f('registered_state','登记状态','enum',options=['up','disabled'])])]

}


def schema(kind):
    if kind not in KINDS:fail('台账类型不存在',404)
    return [*COMMON,*SCHEMAS[kind],f('notes','备注','multiline')]


def rows(conn,table_name,**conditions):
    t=T[table_name]
    query=sa.select(t).where(*[t.c[k]==v for k,v in conditions.items()])
    if 'is_archived' in t.c:query=query.where(t.c.is_archived==False)
    return [dict(v) for v in conn.execute(query).mappings().all()]


def legacy(conn,r):
    kind=r['resource_kind'];d=dict(row(conn,KINDS[kind][1],r['id']) or {})
    result={}
    if kind=='vlan':
        scope=row(conn,'network_scopes',d.get('scope_id'))
        result=dict(vlan_number=d.get('vlan_number'),purpose=d.get('purpose'),scope_name=scope['scope_code'] if scope else 'default',networks=[])
        for n in rows(conn,'subnets',vlan_id=r['id']):
            gates=rows(conn,'subnet_gateways',subnet_id=n['resource_id'])
            result['networks'].append({'cidr':n['cidr_key'],'gateway':gates[0]['ip_address'] if gates else ''})
    elif kind=='wifi':result=dict(ssid=d.get('ssid'),purpose=d.get('purpose'),coverage=d.get('coverage'),auth_method=d.get('auth_method_code'),vlan_ids=[v['vlan_id'] for v in rows(conn,'wifi_vlan_bindings',wifi_id=r['id'])])
    elif kind=='device':
        endpoints=rows(conn,'device_endpoints',device_id=r['id']);identifiers=rows(conn,'device_identifiers',device_id=r['id'])
        result=dict(device_type=d.get('device_type_code'),model=d.get('model'),manufacturer=d.get('manufacturer'),warranty_start=d.get('warranty_start'),warranty_end=d.get('warranty_end'),management_ip=next((v['address'] for v in endpoints if v['endpoint_type']=='ip'),''),esn=next((v['display_value'] for v in identifiers if v['identifier_type'] in ('esn','serial','serial_number')),''))
    elif kind=='circuit':
        vendor=row(conn,'vendors',d.get('vendor_id'));ep=rows(conn,'circuit_endpoints',circuit_id=r['id'])
        result=dict(vendor_name=vendor['name'] if vendor else '',purpose=d.get('purpose'),role=d.get('role_code'),device_id=next((v['device_id'] for v in ep if v['device_id']),None),lines=[dict(line_type='primary',number=d.get('circuit_number'),downstream=d.get('downstream_mbps'),upstream=d.get('upstream_mbps'),usable_ips='\n'.join(v['ip_address'] for v in ep if v['ip_address']),mask=str(ep[0]['prefix_length']) if ep and ep[0]['prefix_length'] is not None else '',gateway=ep[0]['gateway'] if ep else '')])
    elif kind=='vpn':
        ts=sorted(rows(conn,'vpn_tunnels',connection_id=r['id']),key=lambda v:v['tunnel_number'])
        result=dict(remote_site_id=d.get('remote_site_id'),remote_label=d.get('remote_label'),local_device_id=d.get('local_device_id'),circuit_id=d.get('circuit_id'),purpose=d.get('purpose'),local_gateway=ts[0]['local_gateway'] if ts else '',tunnels=[dict(remote_gateway=t['remote_gateway'],registered_state=t['registered_state']) for t in ts],remote_cidrs='\n'.join(v['cidr_key'] or 'any' for v in rows(conn,'vpn_routes',connection_id=r['id']) if v['direction']=='remote'))
        local={v['cidr_key'] for v in rows(conn,'vpn_routes',connection_id=r['id']) if v['direction']=='local'}
        result['local_vlan_ids']=list({v['vlan_id'] for v in rows(conn,'subnets') if v['cidr_key'] in local and v['vlan_id']})
    return result


def circuit_projection(data):
    """Read earlier per-line IP lists as separate per-IP connections without writing."""
    data=dict(data);old_fields={'connection_method','usable_ips','mask','gateway','interface','purpose','dial_username','dial_password','dial_password_ciphertext','has_dial_password'}
    if not data.get('monthly_fee'):
        data['monthly_fee']=next((line.get('monthly_fee') for line in data.get('lines',[]) if line.get('monthly_fee') not in (None,'')),None)
    if 'connections' not in data:
        connections=[]
        for line in data.get('lines',[]):
            if not any(k in line for k in old_fields):continue
            for index,address in enumerate(strings(line.get('usable_ips')) or ['']):
                item={k:line[k] for k in old_fields if k in line and k not in ('usable_ips','has_dial_password')}
                item.update(connection_id='legacy-'+line['line_type']+'-'+str(index),line_type=line['line_type'],ip_address=address,connection_method={'static':'route'}.get(line.get('connection_method'),line.get('connection_method')) or 'route')
                item.setdefault('purpose',data.get('purpose'));connections.append(item)
        data['connections']=connections
    data['lines']=[{k:v for k,v in line.items() if k not in old_fields|{'notes','monthly_fee'}} for line in data.get('lines',[])]
    if 'support_phone' not in data and 'contact' in data:data['support_phone']=data.get('contact')
    return data


def protect_secrets(conn,kind,data,encrypt=False,include_secret=False):
    data=dict(data)
    def visit(values,fields):
        values=dict(values)
        for field in fields:
            name=field['name']
            if field['type']=='rows' and name in values:
                values[name]=[visit(v,field['columns']) for v in values[name] or []]
            elif field['type']=='secret':
                if encrypt:
                    if name in values:values[name+'_ciphertext']=ledger_secrets.encrypt(conn,values.pop(name))
                else:
                    present=name+'_ciphertext' in values or name in values
                    token=values.pop(name+'_ciphertext',None);plain=values.pop(name,None)
                    if include_secret:
                        if present:values[name]=ledger_secrets.decrypt(conn,token) if token else plain
                    else:values['has_'+name]=bool(token or plain)
        return values
    return visit(data,schema(kind))


NETWORK_BINDINGS={
    'wifi':[('vlan_ids','vlan_network_ids','site_id')],
    'vpn':[('local_vlan_ids','local_vlan_network_ids','site_id'),('remote_vlan_ids','remote_vlan_network_ids','remote_site_id')]
}


def network_key(vlan_id,network_id):return vlan_id+':'+network_id


def lock_vlan(conn,key):
    t=T['resources']
    conn.execute(sa.select(t.c.id).where(t.c.id==key).with_hint(t,'WITH (UPDLOCK, HOLDLOCK)','mssql').with_for_update()).all()


def binding_projection(conn,user,kind,data):
    data=dict(data)
    for parents,selection,_ in NETWORK_BINDINGS.get(kind,[]):
        if selection not in data:
            data[selection]=[network_key(key,n['network_id']) for key in data.get(parents,[]) for n in detail(conn,user,key,False).get('networks',[])]
    return data


def network_options(vlans):
    return [{'id':network_key(v['id'],n['network_id']),'vlan_id':v['id'],'vlan_number':v['vlan_number'],'network_id':n['network_id'],
             'site_id':v['site_id'],'site_name':v['site_name'],'scope_name':v.get('scope_name'),'enabled':v['enabled'],'archived':v['archived'],
             'networks':[n],**{k:n.get(k) for k in ('cidr','gateway','purpose')}} for v in vlans for n in v.get('networks',[])]


def network_details(conn,user,data,side):
    if data.get(side+'_network_mode')=='any':
        return [{'cidr':'0.0.0.0/0','purpose':'Any','any':True}]
    result=[]
    for key in data.get(side+'_vlan_ids',[]):
        v=detail(conn,user,key,False)
        selected=set(data.get(side+'_vlan_network_ids',[]))
        for n in v.get('networks',[]):
            if network_key(key,n['network_id']) not in selected:continue
            result.append({**n,'vlan_id':key,'vlan_number':v['vlan_number'],'purpose':n.get('purpose')})
    if side=='remote':result.extend({**n,'manual':True} for n in data.get('remote_networks',[]))
    return result


def detail(conn,user,key,derived=True,include_secret=False):
    r=row(conn,'resources',key)
    if not r or r['resource_kind'] not in KINDS:fail('台账记录不存在',404)
    require(conn,user,'resource.view',r)
    profile=row(conn,'ledger_profiles',key)
    data=json.loads(profile['data_json']) if profile else jsonable(legacy(conn,r))
    if r['resource_kind']=='vlan':
        previous_purpose=data.pop('purpose',None)
        data['networks']=[{**n,'purpose':n.get('purpose',previous_purpose) or '',
            'ipam_enabled':n.get('ipam_enabled') in (True,1,'1','true','True','是','启用'),
            'network_id':n.get('network_id') or str(uuid5(NAMESPACE_URL,'it-portal:vlan:'+key+':'+n['cidr']))} for n in data.get('networks',[])]
    if r['resource_kind']=='vpn' and 'remote_networks' not in data:
        data['remote_networks']=[{'cidr':v,'notes':''} for v in strings(data.get('remote_cidrs'))]
    if r['resource_kind']=='vpn':
        data.pop('circuit_id',None)
        data.setdefault('local_network_mode','selected')
        data.setdefault('remote_network_mode','selected')
    if r['resource_kind']=='circuit':data=circuit_projection(data)
    data=protect_secrets(conn,r['resource_kind'],data,include_secret=include_secret)
    data=binding_projection(conn,user,r['resource_kind'],data)
    if r['resource_kind']=='wifi':data['has_password']=data.get('has_wifi_password',bool(data.get('wifi_password')))
    if r['resource_kind']=='device' and 'installation_location' not in data:
        location=row(conn,'locations',r['location_id']) if r['location_id'] else None
        data['installation_location']=' · '.join(v for v in [location['name'] if location else '',data.get('location_text')] if v)
    result={**data,'id':key,'code':r['resource_code'],'kind':r['resource_kind'],'site_id':r['site_id'],'name':r['name'],
            'owner_user_id':r['owner_user_id'],'location_id':r['location_id'],'version':r['version'],'archived':r['is_archived'],
            'enabled':data.get('enabled',r['lifecycle_status']!='retired'),'updated_at':r['updated_at']}
    site=row(conn,'sites',r['site_id']);result['site_name']=site['name'] if site else ''
    if derived:
        ids=result.get('vlan_ids',result.get('local_vlan_ids',[])) or []
        if result.get('management_vlan_id'):ids=[result['management_vlan_id']]
        selection=set(result.get('vlan_network_ids',result.get('local_vlan_network_ids',[])))
        result['vlan_details']=[]
        for v in ids:
            parent=detail(conn,user,v,False)
            parent['networks']=[n for n in parent.get('networks',[]) if network_key(v,n['network_id']) in selection]
            result['vlan_details'].append(parent)
        if r['resource_kind']=='vpn':
            result['local_network_details']=network_details(conn,user,data,'local')
            result['remote_network_details']=network_details(conn,user,data,'remote')
            result['remote_cidrs']='\n'.join(dict.fromkeys(v['cidr'] for v in result['remote_network_details']))
    return result


def list_items(conn,user,kind,q='',site_id='',archived=False,sort='vlan_asc'):
    schema(kind);require(conn,user,'resource.view')
    t=T['resources'];query=sa.select(t.c.id).where(t.c.resource_kind==kind,t.c.is_archived==archived,catalog.scope_expression(conn,user,'resource.view',t))
    if site_id:query=query.where(t.c.site_id==site_id)
    keys=conn.execute(query.order_by(t.c.name,t.c.id)).scalars().all()
    items=[detail(conn,user,k) for k in keys]
    if kind=='device':
        uplink_ids={v.get('uplink_device_id') for v in items if v.get('uplink_device_id')}
        uplinks={}
        if uplink_ids:
            p=T['ledger_profiles']
            for record in conn.execute(sa.select(p.c.resource_id,p.c.data_json).where(p.c.resource_id.in_(uplink_ids))).mappings():
                uplinks[record['resource_id']]=json.loads(record['data_json']).get('management_ip')
        for item in items:item['uplink_management_ip']=uplinks.get(item.get('uplink_device_id'))
    if q:items=[v for v in items if q.casefold() in json.dumps(jsonable(v),ensure_ascii=False).casefold()]
    if kind=='vlan':
        if sort not in ('vlan_asc','vlan_desc'):fail('VLAN 排序方式无效')
        items.sort(key=lambda v:(int(v.get('vlan_number') or 0),v['site_name'],v['id']),reverse=sort=='vlan_desc')
    return items


def strings(value):
    return [v.strip() for v in str(value or '').replace(';','\n').replace('；','\n').replace(',','\n').splitlines() if v.strip()]


def ip(value,label):
    try:return ipaddress.ip_address(value)
    except ValueError:fail(label+' IP 地址无效')


def network(value):
    try:
        if '/' not in value:fail('网段须包含掩码，例如 10.20.10.0/24')
        return ipaddress.ip_network(value,strict=True)
    except ValueError:fail('网段不是规范网络地址或掩码无效：'+str(value))


def references(data,kind):
    for field in schema(kind):
        if field['type'] in ('ref','refs') and field.get('target') in KINDS:
            values=data.get(field['name']) or ([] if field['type']=='refs' else None)
            for value in values if isinstance(values,list) else [values]:
                if value:yield field['name'],value,field['target']


def clean(conn,user,kind,body,old=None):
    if kind=='vpn' and 'circuit_id' in body:
        body=dict(body);body.pop('circuit_id',None)
    if kind=='vlan':
        body=dict(body);previous_purpose=body.pop('purpose',None)
        if isinstance(body.get('networks'),list):
            old_networks=(old or {}).get('networks',[])
            purposes={n['cidr']:n.get('purpose','') for n in old_networks}
            entries=body['networks']
            body['networks']=[{**n,'purpose':n.get('purpose',previous_purpose if previous_purpose is not None else purposes.get(n.get('cidr'),'')),
                'network_id':n.get('network_id') or next((v['network_id'] for v in old_networks if v['cidr']==n.get('cidr')),old_networks[i]['network_id'] if len(entries)==len(old_networks) else uid())} if isinstance(n,dict) else n for i,n in enumerate(entries)]
    if kind=='circuit' and 'lines' in body and isinstance(body['lines'],list) and any(isinstance(v,dict) and any(k in v for k in ('connection_method','usable_ips','dial_password')) for v in body['lines']):body=circuit_projection(body)
    fs=schema(kind);allowed={v['name']:v for v in fs}
    if any(k not in allowed and k not in ('version','acknowledge_impacts','code') for k in body):fail('包含不允许维护的台账字段')
    data={k:body.get(k,old.get(k) if old else None) for k in allowed}
    for k,field in allowed.items():
        value=data[k];typ=field['type']
        if field['required'] and value in (None,'',[]):fail('请填写'+field['label'])
        if typ in ('refs','rows'):
            if value is None:value=[]
            if not isinstance(value,list) or len(value)>100:fail(field['label']+'格式无效或条目过多')
            if typ=='refs' and (any(not isinstance(v,str) for v in value) or len(value)!=len(set(value))):fail(field['label']+'包含无效或重复选择')
            if typ=='rows':
                keys={v['name'] for v in field['columns']}
                if kind=='circuit' and k=='connections' and old:
                    previous_connections={v.get('connection_id'):v for v in old.get('connections',[])}
                    value=[{**({'dial_password':previous_connections.get(v.get('connection_id'),{}).get('dial_password')} if 'dial_password' not in v else {}),**v} if isinstance(v,dict) else v for v in value]
                if kind=='vlan' and k=='networks':value=[{n:x for n,x in v.items() if n not in ('dhcp_start','dhcp_end')} if isinstance(v,dict) else v for v in value]
                if any(not isinstance(v,dict) or any(n not in keys for n in v) for v in value):fail(field['label']+'列格式无效')
                def cell(column,item):
                    raw=item.get(column['name'])
                    if column['type']=='bool':return raw in (True,1,'1','true','True','是','启用')
                    return str(raw or '') if column['type']=='secret' else str(raw or '').strip()
                value=[{c['name']:cell(c,v) for c in field['columns']} for v in value]
                if any(isinstance(x,str) and len(x)>10000 for v in value for x in v.values()):fail(field['label']+'内容过长')
            data[k]=value
        elif typ=='bool':
            if value is None:value=field.get('default',True)
            if not isinstance(value,bool):fail(field['label']+'选项无效')
            data[k]=value
        elif typ=='int':
            if isinstance(value,bool) or not str(value).isdigit():fail(field['label']+'须为整数')
            data[k]=int(value)
        else:
            if value is not None and not isinstance(value,str):fail(field['label']+'格式无效')
            value=(value or '') if typ=='secret' else (value or '').strip()
            if len(value)> (10000 if typ=='multiline' else 512) or '\x00' in value:fail(field['label']+'内容过长或无效')
            if typ=='enum':
                value=value or field.get('default') or ('none' if k=='auth_method' else 'unknown')
                if value not in field['options'] and not (k=='auth_method' and old and value==old.get(k)):fail(field['label']+'选项无效')
            if typ=='date' and value:
                try:date.fromisoformat(value)
                except ValueError:fail(field['label']+'日期无效')
            data[k]=value or None
    if kind=='vpn':
        for side in ('local','remote'):
            if data[side+'_network_mode']=='any':
                data[side+'_vlan_ids']=[]
                data[side+'_vlan_network_ids']=[]
        if data['remote_network_mode']=='any':data['remote_networks']=[]
    for parents,selection,area in NETWORK_BINDINGS.get(kind,[]):
        # Legacy callers replacing parent VLANs retain their former whole-VLAN selection.
        if parents in body and selection not in body:
            data[selection]=[network_key(key,n['network_id']) for key in data[parents] for n in detail(conn,user,key,False).get('networks',[])]
        parent_keys=[]
        for value in data[selection]:
            if ':' not in value:fail('VLAN 网段选择无效')
            key,network_id=value.split(':',1);parent_keys.append(key)
        for key in sorted(set(parent_keys)):lock_vlan(conn,key)
        previous=set((old or {}).get(selection,[]))
        for value in data[selection]:
            key,network_id=value.split(':',1);v=detail(conn,user,key,False)
            if v['kind']!='vlan' or v['site_id']!=data.get(area):fail('VLAN 网段须属于对应区域')
            if not any(n['network_id']==network_id for n in v.get('networks',[])):fail('所选 VLAN 网段已变化，请刷新后重新选择',409)
            if (v['archived'] or not v['enabled']) and value not in previous:fail('不能新增关联已停用或归档的 VLAN 网段')
        data[parents]=list(dict.fromkeys(parent_keys))
    if not data.get('name'):
        identifier={'vlan':'VLAN '+str(data.get('vlan_number','')),'wifi':data.get('ssid'),'device':data.get('model') or data.get('esn') or data.get('management_ip'),'circuit':data.get('vendor_name'),'vpn':data.get('remote_label') or data.get('local_gateway')}.get(kind)
        data['name']=(identifier or KINDS[kind][0])[:180]+' · '+catalog.generated_code(kind)[-6:]
    if len(data['name'])>200:fail('名称最多 200 字')
    site=row(conn,'sites',data['site_id'])
    if not site or site['is_archived'] or not site['is_enabled']:fail('区域不存在或已停用')
    for k,target in [('location_id','locations'),('owner_user_id','users'),('remote_site_id','sites')]:
        if data.get(k):
            obj=row(conn,target,data[k])
            if not obj or obj.get('is_archived'):fail('关联资料不存在或已归档')
            if k=='location_id' and obj['site_id']!=data['site_id']:fail('安装位置须属于所选区域')
    previous={(field,key) for field,key,_ in references(old or {},kind)}
    for field,key,target in references(data,kind):
        obj=detail(conn,user,key,False)
        if obj['kind']!=target or (old and key==old['id']):fail('关联资料类型不符或不能关联自身')
        expected_site=data.get('remote_site_id') if field=='remote_vlan_ids' else data['site_id']
        if obj['site_id']!=expected_site:fail('所选 VLAN、设备或线路须属于对应区域')
        if (obj['archived'] or not obj['enabled']) and (field,key) not in previous:fail('不能新增关联已停用或归档的资料')
    if kind=='vlan':
        if not 1<=data['vlan_number']<=4094:fail('VLAN ID 须为 1～4094')
        data['scope_name']=data.get('scope_name') or 'default'
        if len(data['scope_name'])>64 or not data['scope_name'].isascii():fail('网络范围使用 64 位以内英文、数字或符号')
        seen=set();seen_ids=set()
        for n in data['networks']:
            try:n['network_id']=str(UUID(n['network_id']))
            except (ValueError,TypeError,AttributeError):fail('网段编号无效，请刷新后重试')
            if n['network_id'] in seen_ids:fail('网段编号重复')
            seen_ids.add(n['network_id'])
            if not n.get('cidr'):fail('已添加的网段行须填写 CIDR；未知可删除该行后保存')
            net=network(n['cidr']);n['cidr']=str(net)
            if n.get('ipam_enabled') and (net.version!=4 or net.num_addresses>65536):fail('静态 IP 管理当前支持 IPv4，单个受管网段最多 65536 个地址')
            if str(net) in seen:fail('VLAN 网段重复')
            if any(net.version==network(v).version and net.overlaps(network(v)) for v in seen):fail('同一 VLAN 的多个网段不能相互重叠')
            seen.add(str(net))
            if n.get('gateway') and ip(n['gateway'],'网关') not in net:fail('网关须属于对应网段')
        for other in rows(conn,'resources',resource_kind='vlan',site_id=data['site_id']):
            if old and other['id']==old['id']:continue
            stored=row(conn,'ledger_profiles',other['id'])
            peer=json.loads(stored['data_json']) if stored else legacy(conn,other)
            if (peer.get('scope_name') or 'default')!=data['scope_name']:continue
            if any(network(a['cidr']).overlaps(network(b['cidr'])) for a in data['networks'] for b in peer.get('networks',[]) if network(a['cidr']).version==network(b['cidr']).version):fail('网段与当前区域及网络范围内已有 VLAN 规划重叠，请检查或区分独立网络范围')
    if kind=='wifi' and len(data['ssid'].encode('utf-8'))>32:fail('SSID 最多 32 个 UTF-8 字节')
    if kind=='wifi' and data.get('auth_method')=='none':data['wifi_password']=None
    if kind=='device':
        if data.get('management_ip'):
            address=ip(data['management_ip'],'管理')
            if data.get('management_vlan_id'):
                ns=detail(conn,user,data['management_vlan_id'],False).get('networks',[])
                if ns and not any(address in network(n['cidr']) for n in ns):fail('管理 IP 不属于所选 VLAN 的网段')
        if data.get('warranty_start') and data.get('warranty_end') and data['warranty_start']>data['warranty_end']:fail('维保结束日期不得早于开始日期')
    if kind=='circuit':
        if data.get('monthly_fee'):
            try:
                from decimal import Decimal
                fee=Decimal(data['monthly_fee'])
                if not fee.is_finite() or fee<0 or fee>=1000000000 or fee.as_tuple().exponent < -2:raise ValueError()
            except Exception:fail('月租费用须为不小于 0、最多两位小数的有效金额')
        types=[line.get('line_type') for line in data['lines']]
        if len(types)!=len(set(types)) or len(types)>2:fail('一组带宽线路最多维护一条主线和一条赠送线路')
        for line in data['lines']:
            if line.get('line_type') not in ('primary','gift'):fail('请选择主线或赠送线路')
            for key in ('downstream','upstream'):
                if line.get(key):
                    try:
                        from decimal import Decimal
                        number=Decimal(line[key])
                        if not number.is_finite() or number<=0 or number>=1000000000 or number.as_tuple().exponent < -3:raise ValueError()
                    except Exception:fail('带宽须为大于 0、最多三位小数的有效 Mbps 数值')
        seen_ids=set()
        for connection in data['connections']:
            if connection.get('line_type') not in types:fail('接入明细必须属于已添加的主线或赠送线路')
            key=connection.get('connection_id') or uid();connection['connection_id']=key
            if len(key)>64 or key in seen_ids:fail('接入编号无效或重复')
            seen_ids.add(key)
            method=connection.get('connection_method') or 'route';connection['connection_method']=method
            if method not in ('route','bridge','pppoe'):fail('连接方式请选择路由、桥接或拨号')
            if len(connection.get('dial_password') or '')>512:fail('拨号密码过长')
            if method=='pppoe':
                for field in ('ip_address','mask','gateway'):connection[field]=''
            else:connection['dial_username']='';connection['dial_password']=''
            address=ip(connection['ip_address'],'接入') if connection.get('ip_address') else None
            gateway=ip(connection['gateway'],'接入网关') if connection.get('gateway') else None
            if connection.get('mask'):
                try:net=ipaddress.ip_network(f"{address or gateway or '0.0.0.0'}/{connection['mask']}",strict=False)
                except ValueError:fail('接入掩码 / 前缀长度无效')
                if (address and address not in net) or (gateway and gateway not in net):fail('接入 IP、掩码和网关不在同一网段')
    if kind=='vpn':
        if data.get('local_gateway'):ip(data['local_gateway'],'本地网关')
        for field in ('remote_networks',):
            seen=set()
            for n in data[field]:
                if not n.get('cidr'):fail('已添加的网段须填写 CIDR')
                n['cidr']=str(network(n['cidr'])) if n['cidr']!='any' else 'any'
                if n['cidr'] in seen:fail('同一列表中网段不能重复')
                seen.add(n['cidr'])
        if len(data['tunnels'])>2:fail('一条 VPN 连接最多维护两个隧道')
        for tunnel in data['tunnels']:
            state=tunnel.get('registered_state') or 'disabled'
            tunnel['registered_state']={'正常':'up','停用':'disabled'}.get(state,state)
            if tunnel.get('remote_gateway'):ip(tunnel['remote_gateway'],'对端网关')
            if tunnel['registered_state'] not in ('up','disabled'):
                unchanged=old and any((v.get('registered_state') or 'unknown')==tunnel['registered_state'] and (v.get('remote_gateway') or '')==(tunnel.get('remote_gateway') or '') for v in old.get('tunnels',[]))
                if not unchanged or tunnel['registered_state'] not in ('down','unknown'):fail('隧道登记状态请选择正常或停用')
    return data


def dependents(conn,user,key):
    keys=set(conn.execute(sa.select(T['ledger_links'].c.source_id).where(T['ledger_links'].c.target_id==key)).scalars().all())
    # Include untouched legacy relations as well as new ledger links.
    for name,col in [('wifi_vlan_bindings','vlan_id'),('subnets','vlan_id'),('vpn_connections','local_device_id'),('vpn_connections','circuit_id')]:
        t=T[name];pk='wifi_id' if name=='wifi_vlan_bindings' else 'resource_id'
        for k in conn.execute(sa.select(t.c[pk]).where(t.c[col]==key)).scalars().all():
            if name=='subnets':continue  # These are owned by the VLAN, not external dependents.
            keys.add(k)
    result=[]
    for k in sorted(keys):
        r=row(conn,'resources',k)
        if r:result.append({'id':k,'name':r['name'] if allow(conn,user,'resource.view',r) else '受权限限制的关联资料','kind':r['resource_kind'],'version':r['version']})
    return result


def assert_networks_unreferenced(conn,user,key,old_networks,removed):
    if not removed:return
    if 'static_ip_records' in T:
        for value in removed:
            vlan_id,network_id=value.split(':',1)
            records=conn.execute(sa.select(T['static_ip_records'].c.id,T['static_ip_records'].c.occupancy_status).where(T['static_ip_records'].c.vlan_id==vlan_id,T['static_ip_records'].c.network_id==network_id)).all()
            if any(v.occupancy_status!='available' for v in records):
                fail('网段已有静态 IP 管理记录，请先释放并清理相关记录',409)
            ids=[v.id for v in records]
            if ids:
                conn.execute(T['static_ip_history'].delete().where(T['static_ip_history'].c.ip_record_id.in_(ids)))
                conn.execute(T['static_ip_records'].delete().where(T['static_ip_records'].c.id.in_(ids)))
    for dependent in dependents(conn,user,key):
        if dependent['kind'] not in NETWORK_BINDINGS:continue
        profile=row(conn,'ledger_profiles',dependent['id'])
        raw=json.loads(profile['data_json']) if profile else legacy(conn,row(conn,'resources',dependent['id']))
        for parents,selection,_ in NETWORK_BINDINGS[dependent['kind']]:
            selected=set(raw.get(selection,[])) if selection in raw else ({network_key(key,n['network_id']) for n in old_networks} if key in raw.get(parents,[]) else set())
            if selected & removed:fail('网段仍被 '+dependent['name']+' 引用，请先调整引用后再移除网段',409)


def delete_network(conn,user,key,network_id,body):
    lock_vlan(conn,key)
    obj=detail(conn,user,key,False);parent=row(conn,'resources',key)
    if obj['kind']!='vlan':fail('只能删除 VLAN 网段',422)
    require(conn,user,'resource.delete',parent)
    if type(body.get('version')) is not int or obj['version']!=body['version']:fail('资料已变化，请刷新后重试',409)
    if body.get('confirm')!=network_id or not str(body.get('reason','')).strip():fail('请确认要删除的网段并填写原因')
    target=next((n for n in obj['networks'] if n['network_id']==network_id),None)
    if not target:fail('网段不存在或已删除，请刷新后重试',404)
    assert_networks_unreferenced(conn,user,key,obj['networks'],{network_key(key,network_id)})
    remaining=[n for n in obj['networks'] if n['network_id']!=network_id]
    t=T['resources'];version=parent['version']+1
    result=conn.execute(t.update().where(t.c.id==key,t.c.version==body['version']).values(version=version,updated_at=utcnow(),updated_by_user_id=user['id']))
    if result.rowcount!=1:fail('资料已变化，请刷新后重试',409)
    profile=row(conn,'ledger_profiles',key)
    data=json.loads(profile['data_json']) if profile else jsonable(legacy(conn,parent))
    data.pop('purpose',None);data['networks']=remaining
    encoded=json.dumps(data,ensure_ascii=False)
    if profile:conn.execute(T['ledger_profiles'].update().where(T['ledger_profiles'].c.resource_id==key).values(data_json=encoded))
    else:insert_row(conn,'ledger_profiles',{'resource_id':key,'data_json':encoded})
    conn.execute(T['vlans'].update().where(T['vlans'].c.resource_id==key).values(purpose='；'.join(dict.fromkeys(n.get('purpose') for n in remaining if n.get('purpose')))[:500] or None))
    audit(conn,user,'resource.ledger_network_delete','resources',key,{'network_id':network_id,'cidr':target['cidr'],'remaining_networks':len(remaining)},reason=body['reason'])
    return {'ok':True,'vlan_id':key,'version':version,'remaining_networks':len(remaining)}


def save(conn,user,kind,body,key=None):
    schema(kind)
    if kind=='vlan' and key:lock_vlan(conn,key)
    old=detail(conn,user,key,False,include_secret=True) if key else None
    if old and old['kind']!=kind:fail('台账类型不能更换')
    permission='resource.edit' if old else 'resource.create'
    if old:require(conn,user,permission,row(conn,'resources',key))
    if old and (type(body.get('version')) is not int or body['version']!=old['version']):fail('资料已变化，请刷新后重试',409)
    data=clean(conn,user,kind,body,old)
    if kind=='vlan' and old:
        before={n['network_id']:n for n in old.get('networks',[])}
        for n in data.get('networks',[]):
            if before.get(n['network_id'],{}).get('cidr')!=n.get('cidr'):
                if conn.execute(sa.select(T['static_ip_records'].c.id).where(T['static_ip_records'].c.vlan_id==key,T['static_ip_records'].c.network_id==n['network_id']).limit(1)).first():
                    fail('此网段已有静态 IP 历史，不能修改 CIDR；请先释放记录后删除网段并重新添加',409)
            if before.get(n['network_id'],{}).get('ipam_enabled') and not n.get('ipam_enabled'):
                if conn.execute(sa.select(T['static_ip_records'].c.id).where(T['static_ip_records'].c.vlan_id==key,T['static_ip_records'].c.network_id==n['network_id'],T['static_ip_records'].c.occupancy_status!='available').limit(1)).first():
                    fail('此网段仍有静态 IP 占用或预留记录，不能关闭静态 IP 管理',409)
    if old:data['owner_user_id']=old.get('owner_user_id')
    require(conn,user,permission,{**dict(row(conn,'resources',key) or {}),'site_id':data['site_id'],'owner_user_id':data.get('owner_user_id'),'created_by_user_id':old and row(conn,'resources',key)['created_by_user_id'] or user['id']})
    if kind=='vlan' and old:
        old_networks=[{k:v.get(k,'') for k in ('cidr','gateway')} for v in old.get('networks',[])]
        new_networks=[{k:v.get(k,'') for k in ('cidr','gateway')} for v in data['networks']]
        changed=old_networks!=new_networks or old.get('scope_name','default')!=data['scope_name'] or old['site_id']!=data['site_id'] or old.get('vlan_number')!=data['vlan_number']
        affected=dependents(conn,user,key) if changed else []
        removed={network_key(key,n['network_id']) for n in old.get('networks',[])}-{network_key(key,n['network_id']) for n in data['networks']}
        assert_networks_unreferenced(conn,user,key,old.get('networks',[]),removed)
        if affected and body.get('acknowledge_impacts') is not True:fail('修改 VLAN 将影响 '+ '、'.join(v['name'] for v in affected)+'；请先查看关联资料并确认影响',409)
        if affected and (old['site_id']!=data['site_id']):fail('被引用的 VLAN 不能更换区域')
        for item in affected:
            if item['kind']=='device':
                dependent=detail(conn,user,item['id'],False)
                if dependent.get('management_ip') and data['networks'] and not any(ip(dependent['management_ip'],'管理') in network(n['cidr']) for n in data['networks']):fail('新网段不包含关联设备的管理 IP：'+item['name'])
    values=dict(name=data['name'],site_id=data['site_id'],owner_user_id=data.get('owner_user_id'),location_id=old.get('location_id') if old and kind!='device' else None,lifecycle_status='in_use' if data['enabled'] else 'retired')
    if old:values['version']=body.get('version')
    else:
        values['resource_kind']=kind
        if body.get('code'):values['resource_code']=body['code']
    parent=catalog.save(conn,user,'resources',values,key)
    key=parent['id'];sub=KINDS[kind][1];existing=row(conn,sub,key)
    child={'resource_id':key,'version':parent['version']}
    if kind=='vlan':
        scopes=rows(conn,'network_scopes',site_id=data['site_id'],scope_code=data['scope_name'])
        scope=scopes[0] if scopes else insert_row(conn,'network_scopes',{'site_id':data['site_id'],'scope_code':data['scope_name'],'name':data['scope_name']},user['id'])
        child.update(scope_id=scope['id'],vlan_number=data['vlan_number'],purpose='；'.join(dict.fromkeys(v['purpose'] for v in data['networks'] if v.get('purpose')))[:500] or None)
    elif kind=='wifi':child.update(ssid=data['ssid'],site_id=data['site_id'],purpose=data.get('purpose'),coverage=data.get('coverage'),auth_method_code=data.get('auth_method'))
    elif kind=='device':child.update(device_type_code=(data.get('device_type') if (data.get('device_type') or '').isascii() else None) or 'unknown',model=data.get('model'),manufacturer=data.get('manufacturer'),warranty_start=data.get('warranty_start'),warranty_end=data.get('warranty_end'))
    elif kind=='circuit':
        vendor_name=data.get('vendor_name') or '未登记运营商';vendors=rows(conn,'vendors',name=vendor_name)
        vendor=vendors[0] if vendors else insert_row(conn,'vendors',{'code':catalog.generated_code('vendors'),'name':vendor_name},user['id'])
        main=next((v for v in data['lines'] if v['line_type']=='primary'),{})
        child.update(vendor_id=vendor['id'],circuit_number=main.get('number') or None,downstream_mbps=main.get('downstream') or None,upstream_mbps=main.get('upstream') or None,role_code='unknown',purpose=next((v.get('purpose') for v in data['connections'] if v['line_type']=='primary'),None))
    else:child.update(connection_type='aws',remote_site_id=data.get('remote_site_id'),remote_label=None,local_device_id=None,circuit_id=data.get('circuit_id'),purpose=data.get('purpose'))
    catalog.save(conn,user,sub,child,key if existing else None)
    # Parent CAS is the transaction mutex for profiles and every link.
    stored=protect_secrets(conn,kind,data,encrypt=True)
    profile=T['ledger_profiles'];encoded=json.dumps(jsonable(stored),ensure_ascii=False)
    if row(conn,'ledger_profiles',key):conn.execute(profile.update().where(profile.c.resource_id==key).values(data_json=encoded))
    else:insert_row(conn,'ledger_profiles',{'resource_id':key,'data_json':encoded})
    links=T['ledger_links'];conn.execute(links.delete().where(links.c.source_id==key))
    for field,target,_ in references(data,kind):insert_row(conn,'ledger_links',{'source_id':key,'target_id':target,'relation':field})
    if kind=='wifi':
        t=T['wifi_vlan_bindings'];conn.execute(t.delete().where(t.c.wifi_id==key))
        for target in data['vlan_ids']:insert_row(conn,'wifi_vlan_bindings',{'wifi_id':key,'vlan_id':target,'binding_role':'default'},user['id'])
    audit(conn,user,'resource.ledger_save','resources',key,{'kind':kind})
    return detail(conn,user,key,include_secret=True)


def delete(conn,user,key,body):
    parent=row(conn,'resources',key)
    if parent and parent['resource_kind']=='vlan':lock_vlan(conn,key)
    obj=detail(conn,user,key,False);parent=row(conn,'resources',key);require(conn,user,'resource.delete',parent)
    if obj['version']!=body.get('version'):fail('资料已变化，请刷新后重试',409)
    if body.get('confirm')!=key or not str(body.get('reason','')).strip():fail('请确认删除并填写原因')
    affected=dependents(conn,user,key)
    if affected:fail('仍被以下资料引用，不能删除：'+'、'.join(v['name'] for v in affected)+'。可改为停用。',409)
    if obj['kind']=='vlan' and obj.get('networks'):fail('此 VLAN 仍有网段，请使用删除网段；只允许删除没有网段的空 VLAN',409)
    # External legacy FKs are checked before removing owned child rows.
    owned={'vlan':{'subnets','subnet_gateways'},'wifi':{'wifi_vlan_bindings'},'device':{'device_identifiers','device_interfaces','device_endpoints'},'circuit':{'circuit_endpoints'},'vpn':{'vpn_tunnels','vpn_routes'}}[obj['kind']]
    for name,t in T.items():
        if name in owned or name in ('ledger_links','ledger_profiles',KINDS[obj['kind']][1]):continue
        for col in t.c:
            if any(fk.target_fullname in ('resources.id',KINDS[obj['kind']][1]+'.resource_id') for fk in col.foreign_keys):
                if conn.execute(sa.select(col).where(col==key).limit(1)).first():fail('资料仍有历史或业务引用，不能删除，可停用',409)
    conn.execute(T['ledger_links'].delete().where(T['ledger_links'].c.source_id==key))
    conn.execute(T['ledger_profiles'].delete().where(T['ledger_profiles'].c.resource_id==key))
    if obj['kind']=='vlan':
        for n in rows(conn,'subnets',vlan_id=key):
            conn.execute(T['subnet_gateways'].delete().where(T['subnet_gateways'].c.subnet_id==n['resource_id']))
            conn.execute(T['subnets'].delete().where(T['subnets'].c.resource_id==n['resource_id']))
            conn.execute(T['resources'].delete().where(T['resources'].c.id==n['resource_id']))
    owned_columns={'wifi_vlan_bindings':'wifi_id','device_identifiers':'device_id','device_interfaces':'device_id','device_endpoints':'device_id','circuit_endpoints':'circuit_id','vpn_tunnels':'connection_id','vpn_routes':'connection_id'}
    for name in owned:
        if name in owned_columns:conn.execute(T[name].delete().where(T[name].c[owned_columns[name]]==key))
    conn.execute(T[KINDS[obj['kind']][1]].delete().where(T[KINDS[obj['kind']][1]].c.resource_id==key))
    result=conn.execute(T['resources'].delete().where(T['resources'].c.id==key,T['resources'].c.version==body['version']))
    if result.rowcount!=1:fail('资料已变化，请刷新',409)
    audit(conn,user,'resource.delete','resources',key,reason=body['reason'])


def register(app,engine,out,current_user,data_dir=None):
    if data_dir is not None:engine.ledger_data_dir=data_dir
    from . import ledger_transfers as transfer

    @app.get('/api/ledger/{kind}/template')
    def template(request:Request,kind:str):
        with engine.begin() as conn:
            u=current_user(conn,request);require(conn,u,'resource.import');schema(kind)
            return Response(transfer.workbook(conn,u,kind),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename="ledger-{kind}.xlsx"'})

    @app.get('/api/ledger/{kind}/export')
    def export(request:Request,kind:str,q:str='',site_id:str='',sort:str='vlan_asc'):
        with engine.begin() as conn:
            u=current_user(conn,request);require(conn,u,'resource.export')
            items=[v for v in list_items(conn,u,kind,q,site_id,sort=sort) if allow(conn,u,'resource.export',row(conn,'resources',v['id']))]
            return Response(transfer.workbook(conn,u,kind,items),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename="ledger-{kind}-export.xlsx"'})

    @app.post('/api/ledger/{kind}/imports')
    async def import_file(request:Request,kind:str,file:UploadFile=File(...),mode:str=Form('create_only')):
        raw=await file.read(20*1024*1024+1)
        with engine.begin() as conn:return out(transfer.preview(conn,current_user(conn,request),kind,raw,file.filename or '',mode),201)

    @app.get('/api/ledger/schema')
    def schemas(request:Request):
        with engine.begin() as conn:
            u=current_user(conn,request);require(conn,u,'resource.view')
            return out({'modules':[{'kind':k,'title':v[0],'fields':schema(k)} for k,v in KINDS.items()],'actions':[a for a in ('create','edit','delete','import','export') if allow(conn,u,'resource.'+a)]})

    @app.get('/api/ledger/options')
    def options(request:Request):
        with engine.begin() as conn:
            u=current_user(conn,request);require(conn,u,'resource.view')
            data={k:list_items(conn,u,k) for k in KINDS}
            data['vlan_network']=network_options(data['vlan'])
            data['sites']=[{'id':v['id'],'name':v['name']} for v in rows(conn,'sites') if v['is_enabled']]
            data['locations']=[{'id':v['id'],'name':v['name'],'site_id':v['site_id']} for v in rows(conn,'locations')]
            if any(allow(conn,u,p) for p in ('resource.create','resource.edit')):
                data['users']=[{'id':v['id'],'name':v['display_name']} for v in rows(conn,'users') if v['account_state']=='active']
            return out(data)

    @app.get('/api/ledger/{kind}')
    def listing(request:Request,kind:str,page:int=1,page_size:int=10,q:str='',site_id:str='',archived:bool=False,sort:str='vlan_asc'):
        if page_size not in (10,20,50):fail('每页条数仅支持 10、20、50',422)
        with engine.begin() as conn:
            items=list_items(conn,current_user(conn,request),kind,'' if kind=='vlan' else q,site_id,archived,sort);page=max(1,page)
            if kind=='vlan':
                items=[{**v,'networks':[n] if n else [],'network_id':n and n['network_id'],'network_count':len(v['networks'])} for v in items for n in v['networks'] or [None]]
                if q:items=[v for v in items if q.casefold() in json.dumps(jsonable(v),ensure_ascii=False).casefold()]
            return out({'items':items[(page-1)*page_size:page*page_size],'total':len(items),'page':page,'page_size':page_size})

    @app.get('/api/ledger/item/{key}')
    def item(request:Request,key:str):
        with engine.begin() as conn:
            u=current_user(conn,request);data=detail(conn,u,key,include_secret=True);data['dependents']=dependents(conn,u,key);return out(data)

    @app.post('/api/ledger/{kind}')
    def create(request:Request,kind:str,body:dict):
        with engine.begin() as conn:return out(save(conn,current_user(conn,request),kind,body),201)

    @app.put('/api/ledger/{kind}/{key}')
    def update(request:Request,kind:str,key:str,body:dict):
        with engine.begin() as conn:return out(save(conn,current_user(conn,request),kind,body,key))

    @app.delete('/api/ledger/vlan/{key}/networks/{network_id}')
    def remove_network(request:Request,key:str,network_id:str,body:dict):
        with engine.begin() as conn:return out(delete_network(conn,current_user(conn,request),key,network_id,body))

    @app.delete('/api/ledger/item/{key}')
    def remove(request:Request,key:str,body:dict):
        with engine.begin() as conn:delete(conn,current_user(conn,request),key,body);return out({'ok':True})
