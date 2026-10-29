/* Five complete business forms. Internal resource/subtype tables stay off the menu. */
let ledgerSpec=null,ledgerOptions=null,ledgerOptionsReady=false,ledgerCurrent=null,ledgerFilters={q:'',site_id:'',sort:'vlan_asc'};
function resetLedger(){ledgerSpec=null;ledgerOptions=null;ledgerOptionsReady=false;ledgerCurrent=null;ledgerFilters={q:'',site_id:'',sort:'vlan_asc'};}
const ledgerLabels={unknown:'未登记',up:'正常',down:'异常',primary:'主线',gift:'赠送普通线路',backup:'备用',none:'不认证',password:'密码',password_mac:'密码+MAC',static:'固定 IP',pppoe:'拨号',route:'路由',bridge:'桥接',disabled:'停用',selected:'指定 VLAN 网段',any:'Any - 0.0.0.0/0'};
const ledgerText=v=>ledgerLabels[v]||v||'—';

async function ledgerLoad(includeOptions=false){
  const tasks=[];
  if(!ledgerSpec)tasks.push(api('/api/ledger/schema').then(value=>ledgerSpec=value));
  if(includeOptions&&!ledgerOptionsReady)tasks.push(api('/api/ledger/options').then(value=>{ledgerOptions=value;ledgerOptionsReady=true;}));
  await Promise.all(tasks);
  if(!ledgerOptions)ledgerOptions={sites:state.lookup.sites||[]};
}
function ledgerNetworkHTML(v){return (v.networks||[]).map(n=>`<div class="ledger-network-line">${esc(n.purpose||'未登记用途')} - ${esc(n.cidr)}${n.gateway?` · 网关 ${esc(n.gateway)}`:''}${n.ipam_enabled?' <span class="tag">静态IP管理</span>':''}</div>`).join('')||'尚未登记网段';}
function ledgerRefLabel(target,v){
  if(target==='vlan'||target==='vlan_network')return `${v.site_name||''} · VLAN ${v.vlan_number} · ${(v.networks||[]).map(n=>(n.purpose?n.purpose+' - ':'')+n.cidr).join('、')||'未登记网段'}${v.scope_name&&v.scope_name!=='default'?' · '+v.scope_name:''}`;
  if(target==='device')return [v.model,v.management_ip,v.esn].filter(Boolean).join(' · ')||'未登记设备信息';
  if(target==='circuit')return [v.vendor_name,...(v.lines||[]).map(l=>l.number)].filter(Boolean).join(' · ')||'未登记线路信息';
  if(target==='wifi')return v.ssid||'未登记 SSID';
  if(target==='vpn')return [v.remote_label,v.local_gateway].filter(Boolean).join(' · ')||'VPN 隧道';
  return v.name||v.ssid||'未登记';
}
async function ledgerPage(kind='vlan'){
  await ledgerLoad();
  if(!ledgerSpec.modules.some(v=>v.kind===kind))throw Error('台账类型不存在');
  const data=await api('/api/ledger/'+kind+'?'+new URLSearchParams({page:state.page,page_size:state.pageSize,...ledgerFilters}));
  ledgerCurrent={kind,items:data.items};
  const spec=ledgerSpec.modules.find(v=>v.kind===kind),actions=ledgerSpec.actions;
  const buttons=(actions.includes('create')?'<button class="primary" data-action="ledger-create">＋ 新增'+esc(spec.title)+'</button>':'')
    +(actions.includes('import')?'<button data-action="ledger-import">导入数据</button><button data-action="ledger-template">下载标准模板</button>':'')
    +(actions.includes('export')?'<button data-action="ledger-export">导出数据</button>':'');
  const actionsHTML=v=>{
    const deletion=kind==='vlan'&&v.network_id?`<button data-action="ledger-delete-network" data-id="${v.id}" data-network-id="${esc(v.network_id)}">删除网段</button>`:`<button data-action="ledger-delete" data-id="${v.id}">${kind==='vlan'?'删除空 VLAN':'删除'}</button>`;
    const ipam=kind==='vlan'&&v.network_id&&v.networks?.[0]?.ipam_enabled?`<button data-action="ipam-open" data-network="${esc(v.id+':'+v.network_id)}">IP占用</button>`:'';
    return `<div class="table-actions"><button data-action="ledger-edit" data-id="${v.id}">${kind==='vlan'?'VLAN 详情':'详情'}${actions.includes('edit')?' / 编辑':''}</button>${ipam}${actions.includes('delete')?deletion:''}</div>`;
  };
  const defs={vlan:['区域','VLAN ID','网段用途 / CIDR / 网关','备注','启用'],wifi:['区域','SSID','密码','认证方式','关联 VLAN','用途 / 备注','启用'],
    device:['区域','设备类型','管理 IP','设备型号 / 品牌','上联设备','用户名','密码','安装位置','堆叠','维保信息','备注','启用'],
    vpn:['区域','本地网段','对端区域','对端网段','本地网关','隧道 1 / 隧道 2','备注','启用']};
  let content;
  if(kind==='circuit')content=ledgerCircuitTable(data.items,actionsHTML);
  else content=ledgerTable([...defs[kind],'操作'],data.items,data.items.map(v=>{
    const enabled=ledgerStatus(v.enabled);let values;
    if(kind==='vlan')values=[esc(v.site_name),`<strong>${esc(v.vlan_number)}</strong>`,ledgerNetworkHTML(v),ledgerNotes(v.notes),enabled];
    if(kind==='wifi')values=[esc(v.site_name),esc(v.ssid),ledgerPassword(v,'wifi_password'),esc(ledgerText(v.auth_method||'none')),(v.vlan_details||[]).map(n=>`<div><strong>VLAN ${esc(n.vlan_number)}</strong>${ledgerNetworkHTML(n)}</div>`).join('')||'未关联',`<div>${esc(v.purpose||'—')}</div>${v.notes?`<div class="help">${ledgerNotes(v.notes)}</div>`:''}`,enabled];
    if(kind==='device')values=[esc(v.site_name),esc(v.device_type||'—'),esc(v.management_ip||'—'),esc([v.model,v.manufacturer].filter(Boolean).join(' · ')||'—'),ledgerUplink(v),esc(v.login_username||'—'),ledgerPassword(v,'login_password'),esc(v.installation_location||'—'),v.is_stacked?'已堆叠':'未堆叠',`${esc(v.warranty_start||'未登记')}<br>至 ${esc(v.warranty_end||'未登记')}`,ledgerNotes(v.notes),enabled];
    if(kind==='vpn')values=[esc(v.site_name),ledgerNetworkDetails(v.local_network_details),esc(ledgerOptions.sites.find(x=>x.id===v.remote_site_id)?.name||'未选择'),ledgerNetworkDetails(v.remote_network_details),esc(v.local_gateway||'—'),(v.tunnels||[]).map((t,i)=>`<div>Tunnel ${i+1}：${esc(t.remote_gateway||'—')} ${ledgerTunnelStatus(t.registered_state)}</div>`).join('')||'未登记',ledgerNotes(v.notes),enabled];
    return [...values,actionsHTML(v)];
  }));
  setPage(head('基础信息台账',kind==='vlan'?'每行显示一个网段；同一 VLAN 的网段在编辑页统一维护。':'按日常运维工作维护五类资料；关联信息自动带出。',buttons)+`<div class="tabs">${ledgerSpec.modules.map(v=>`<a href="#ledger/${v.kind}" class="${kind===v.kind?'active':''}">${esc(v.title)}</a>`).join('')}</div><section class="panel">${ledgerFilterHTML(kind)}${content}${pager(data)}</section>`,'基础信息台账');
}
function ledgerUplinkLabel(v){return v.management_ip||'未登记管理 IP';}
function ledgerUplink(v){const upstream=ledgerOptions.device?.find(x=>x.id===v.uplink_device_id);return `${esc(v.uplink_management_ip||(upstream?ledgerUplinkLabel(upstream):'—'))}<div class="help">上联接口：${esc(v.uplink_port||'—')}<br>本机接口：${esc(v.local_port||'—')}</div>`;}
function ledgerStatus(enabled){return `<span class="ledger-status ${enabled?'is-enabled':'is-disabled'}">${enabled?'● 启用':'⏸ 已停用'}</span>`;}
function ledgerTunnelStatus(value){
  const known=['up','disabled'].includes(value),normal=value==='up';
  return `<span class="ledger-status ${known?(normal?'is-enabled':'is-disabled'):'is-pending'}" title="${known?(normal?'正常':'停用'):'原状态：'+ledgerText(value||'unknown')}">${known?(normal?'✓ 正常':'⏸ 停用'):'? 待确认'}</span>`;
}
function ledgerTable(headers,items,rows){return rows.length?`<div class="table-scroll"><table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map((cells,i)=>`<tr class="${items[i].enabled?'':'ledger-disabled'}">${cells.map(v=>`<td>${v}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:empty();}
function ledgerNetworkDetails(items){return (items||[]).map(n=>n.any?`<div class="ledger-route"><strong>Any</strong> - 0.0.0.0/0</div>`:`<div class="ledger-route">${esc((n.manual?n.notes:n.purpose)|| (n.manual?'未备注':'未登记用途'))} - ${esc(n.cidr)}</div>`).join('')||'未登记';}
function ledgerCircuitTable(items,actionsHTML){
  if(!items.length)return empty('暂无带宽线路');
  const headers=['区域','运营商 / 保障电话','线路类型 / 线路号','带宽','连接方式','可用 IP / 拨号信息','接入接口','用途','备注','启用','操作'];
  const body=items.map(v=>{
    const entries=(v.lines?.length?v.lines:[{}]).map(line=>({line,connections:(v.connections||[]).map((c,i)=>({...c,sourceIndex:i})).filter(c=>c.line_type===line.line_type)}));
    const span=entries.reduce((total,item)=>total+Math.max(1,item.connections.length),0);let groupIndex=0;
    return entries.map(({line,connections})=>(connections.length?connections:[{}]).map((connection,index)=>{
      const first=groupIndex++===0,lineSpan=Math.max(1,connections.length);
      return `<tr class="${first?'ledger-group-start ':''}${v.enabled?'':'ledger-disabled'}">${first?`<td rowspan="${span}">${esc(v.site_name)}</td><td rowspan="${span}">${esc(v.vendor_name||'未登记')}<div class="help">保障电话：${esc(v.support_phone||'未登记')}</div></td>`:''}${index===0?`<td rowspan="${lineSpan}">${esc(ledgerText(line.line_type))}<div class="help">${esc(line.number||'未登记线路号')}</div></td><td rowspan="${lineSpan}">↓${esc(line.downstream||'—')} / ↑${esc(line.upstream||'—')} Mbps</td>`:''}<td>${esc(ledgerText(connection.connection_method))}</td><td>${connection.connection_method==='pppoe'?`<div>账号：${esc(connection.dial_username||'—')}</div>${ledgerPassword(connection,'dial_password',v.id,'connections.'+connection.sourceIndex+'.dial_password')}`:`${esc(connection.ip_address||'—')}${connection.mask||connection.gateway?`<div class="help">掩码：${esc(connection.mask||'—')}<br>网关：${esc(connection.gateway||'—')}</div>`:''}`}</td><td>${esc(connection.interface||'—')}</td><td>${ledgerNotes(connection.purpose)}</td>${first?`<td rowspan="${span}">${ledgerNotes(v.notes)}</td><td rowspan="${span}">${ledgerStatus(v.enabled)}</td><td rowspan="${span}">${actionsHTML(v)}</td>`:''}</tr>`;
    }).join('')).join('');
  }).join('');
  return `<div class="table-scroll"><table class="ledger-circuit-table"><thead><tr>${headers.map(v=>`<th>${v}</th>`).join('')}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function ledgerVlanDropdowns(f,value,name,site){
  const ids=value?.length?value:[''];
  return `<div class="ledger-vlan-selects" data-vlan-field="${name}">${ids.map((id,i)=>ledgerVlanChoice(name,id,i,site)).join('')}<button type="button" class="small" data-action="ledger-add-vlan" data-field="${name}">＋ 添加网段</button></div>`;
}
function ledgerVlanChoice(name,id,index,site){
  const list=(ledgerOptions.vlan_network||[]).filter(v=>v.site_id===site&&((!v.archived&&v.enabled!==false)||v.id===id));
  const any=['local_vlan_network_ids','remote_vlan_network_ids'].includes(name)?`<option value="__any__" ${id==='__any__'?'selected':''}>Any - 0.0.0.0/0</option>`:'';
  return `<div class="ledger-vlan-choice"><select name="${name}.${index}" data-ref-field="${name}"><option value="">请选择 VLAN 网段</option>${any}${list.map(v=>`<option value="${esc(v.id)}" ${v.id===id?'selected':''}>${esc(ledgerRefLabel('vlan_network',v))}</option>`).join('')}</select><button type="button" class="small" data-action="ledger-remove-vlan" aria-label="移除 VLAN 关联">移除</button></div>`;
}
function ledgerControl(f,value,name,site,selected=true){
  const required=f.required?'required':'';
  if(f.dropdowns)return ledgerVlanDropdowns(f,value,name,site);
  if(f.type==='secret')return `<div class="ledger-password"><input name="${esc(name)}" type="password" autocomplete="off" value="${esc(value||'')}"><button type="button" data-action="ledger-toggle-password" data-field="${esc(name)}">显示</button></div>`;
  if(f.type==='ref'||f.type==='refs'){
    const multi=f.type==='refs';let list=ledgerOptions[f.target]||[];
    if(f.target!=='sites'&&f.target!=='users'&&!f.global_ref)list=list.filter(v=>v.site_id===site);
    const values=multi?value||[]:[value];
    list=list.filter(v=>(!v.archived||values.includes(v.id))&&(v.enabled!==false||values.includes(v.id)));
    const options=list.map(v=>`<option value="${esc(v.id)}" ${values.includes(v.id)?'selected':''}>${esc(f.name==='uplink_device_id'?ledgerUplinkLabel(v):ledgerRefLabel(f.target,v))}${v.enabled===false?'（已停用）':''}</option>`).join('');
    return `<select name="${esc(name)}" data-ledger-target="${esc(f.target)}" ${multi?'multiple size="5"':''} ${required}>${multi?'':`<option value="">${f.required?'请选择':'不选择'}</option>`}${options}</select>${multi?'<small class="help">按住 Ctrl 可选择多个。</small>':''}`;
  }
  if(f.type==='bool')return select(name,[{value:'1',name:f.name==='enabled'?'启用':'是'},{value:'0',name:f.name==='enabled'?'停用':'否'}],(value??f.default??true)?'1':'0',true);
  if(f.type==='enum'&&f.name==='registered_state'&&f.options.includes('disabled')){
    const legacy=value&&!f.options.includes(value);return select(name,[{value:'up',name:'✓ 正常'},{value:'disabled',name:'⏸ 停用'}],legacy?'':value||'disabled',true)+(legacy?`<small class="help">原登记状态为${esc(ledgerText(value))}，请选择正常或停用。</small>`:'');
  }
  if(f.type==='enum'){const options=f.options.includes(value)||!value?f.options:[...f.options,value];return select(name,options.map(v=>({value:v,name:ledgerText(v)})),value||f.options[0],true);}
  if(f.type==='multiline')return `<textarea name="${esc(name)}" rows="3" ${required}>${esc(value||'')}</textarea>`;
  return `<input name="${esc(name)}" type="${f.type==='date'?'date':['int','decimal'].includes(f.type)?'number':'text'}" ${required} ${f.type==='decimal'?`step="${esc(f.step||'0.001')}" min="0"`:''} value="${esc(value??'')}">`;
}
let ledgerConnectionCounter=0;
function ledgerRow(f,value,index,site,connections=[]){
  const title=f.name==='tunnels'?'Tunnel '+(index+1):f.name==='lines'?ledgerText(value.line_type||'primary'):f.name==='connections'?'接入信息':'网段 '+(index+1);
  return `<div class="ledger-repeat-row" data-row="${esc(f.name)}"><div class="ledger-row-title"><strong>${esc(title)}</strong><button type="button" class="small" data-action="ledger-remove-row">移除此行</button></div><div class="form-grid">${f.columns.map(c=>{
    const mode=['dial_username','dial_password'].includes(c.name)?'pppoe':['ip_address','mask','gateway'].includes(c.name)?'ip':'';
    if(c.ui_hidden||(f.name==='connections'&&c.name==='line_type'))return `<input type="hidden" name="${f.name}.${index}.${c.name}" value="${esc(value[c.name]||'')}">`;
    const control=ledgerControl(c,value[c.name],`${f.name}.${index}.${c.name}`,site);
    return `<div ${mode?`data-line-mode="${mode}"`:''}>${field(c.label,control,false)}</div>`;
  }).join('')}</div>${f.name==='lines'?ledgerLineConnections(value,connections,site):''}</div>`;
}
function ledgerLineConnections(line,connections,site){
  const f=ledgerSpec.modules.find(v=>v.kind==='circuit').fields.find(v=>v.name==='connections');
  return `<section class="ledger-line-connections"><h4>IP / 接入信息</h4><div data-line-connections>${connections.filter(c=>c.line_type===line.line_type).map(c=>ledgerRow(f,c,ledgerConnectionCounter++,site)).join('')}</div><button type="button" data-action="ledger-add-connection">＋ 添加 IP / 接入信息</button></section>`;
}
function ledgerConnectionMode(row,editable=true){
  const mode=row.querySelector('[name$=".connection_method"]')?.value||'route';
  row.querySelectorAll('[data-line-mode]').forEach(holder=>{holder.hidden=(holder.dataset.lineMode==='ip'?mode==='pppoe':mode!=='pppoe');holder.querySelectorAll('input,textarea,button').forEach(el=>el.disabled=holder.hidden||(!editable&&el.tagName!=='BUTTON'));});
}
function ledgerRead(form,spec){
  const data={};
  for(const f of spec.fields){
    if(f.ui_hidden)continue;
    if(f.dropdowns){
      const selected=[...form.querySelectorAll(`[data-ref-field="${f.name}"]`)].map(v=>v.value).filter(Boolean);
      if(['local_vlan_network_ids','remote_vlan_network_ids'].includes(f.name)){
        const side=f.name.startsWith('local_')?'local':'remote';
        data[side+'_network_mode']=selected.includes('__any__')?'any':'selected';
        data[f.name]=selected.filter(v=>v!=='__any__');
      }else data[f.name]=selected;
      continue;
    }
    if(f.type==='rows'){
      data[f.name]=[...form.querySelectorAll(`[data-row="${f.name}"]`)].map(row=>{
        const item={};for(const c of f.columns){const el=row.querySelector(`[name$=".${c.name}"]`);item[c.name]=c.type==='bool'?el?.value==='1':el?.value||'';}return item;
      });continue;
    }
    const el=form.elements.namedItem(f.name);if(!el)continue;
    data[f.name]=f.type==='refs'?[...el.selectedOptions].map(v=>v.value):f.type==='bool'?el.value==='1':f.type==='int'?(el.value===''?null:Number(el.value)):el.value||null;
  }
  return data;
}
async function ledgerForm(kind,key=null,draft=null){
  await ledgerLoad(true);const spec=ledgerSpec.modules.find(v=>v.kind===kind);
  const item=key?await api('/api/ledger/item/'+key):{};
  const values={enabled:true,...item,...draft};const editable=key?ledgerSpec.actions.includes('edit'):ledgerSpec.actions.includes('create');
  for(const f of spec.fields.filter(v=>['ref','refs'].includes(v.type)&&ledgerSpec.modules.some(m=>m.kind===v.target))){
    const ids=f.type==='refs'?values[f.name]||[]:[values[f.name]].filter(Boolean);
    for(const id of ids)if(!ledgerOptions[f.target].some(v=>v.id===id))ledgerOptions[f.target].push(await api('/api/ledger/item/'+id));
  }
  ledgerOptions.vlan_network=(ledgerOptions.vlan||[]).flatMap(v=>(v.networks||[]).map(n=>({...v,id:v.id+':'+n.network_id,vlan_id:v.id,networks:[n]})));
  ledgerConnectionCounter=0;
  let normal=kind==='vpn'?'<div class="ledger-form-section full"><h3>本地信息</h3></div>':'',advanced='';
  for(const f of spec.fields){
    if(f.ui_hidden||f.ui_embedded||(kind==='vpn'&&['local_network_mode','remote_network_mode'].includes(f.name)))continue;
    let part;
    if(f.type==='rows'){
      let entries=values[f.name];
      if(!entries)entries=f.name==='lines'?[{line_type:'primary'}]:f.name==='tunnels'?[{registered_state:'disabled'},{registered_state:'disabled'}]:[];
      const label=f.name==='lines'?'添加主线 / 赠送线路':f.name==='tunnels'?'添加隧道（最多两个）':'添加网段';
      part=`<section class="ledger-repeat full"><h3>${esc(f.label)}</h3><div data-rows="${f.name}">${entries.map((v,i)=>ledgerRow(f,v,i,values.site_id,values.connections||[])).join('')}</div><button type="button" data-action="ledger-add-row" data-field="${f.name}">＋ ${label}</button></section>`;
    }else{
      const value=kind==='vpn'&&['local_vlan_network_ids','remote_vlan_network_ids'].includes(f.name)&&values[f.name.replace('_vlan_network_ids','_network_mode')]==='any'?['__any__']:values[f.name];
      part=field(f.label,ledgerControl(f,value,f.name,values[f.site_field||'site_id']),f.required,f.help||'');
    }
    if(kind==='vpn'&&f.name==='remote_site_id')normal+='<div class="ledger-form-section is-remote full"><h3>对端信息</h3></div>';
    if(f.advanced)advanced+=part;else normal+=part;
  }
  const dependencies=item.dependents||[];
  const impact=kind==='vlan'&&dependencies.length?`<div class="callout">关联资料：${dependencies.map(v=>esc(v.name)).join('、')}。修改网段前请检查影响。</div><label class="checkbox-row"><input name="acknowledge_impacts" type="checkbox">我已检查上述关联资料，确认此次 VLAN 修改的影响</label>`:'';
  formModal((key?'详情 / 编辑':'新增')+spec.title,`<p class="help">${kind==='vpn'?'状态为人工登记，以更新时间为准；实时状态请查看运维态势。':'选填资料可后续补齐。'}</p><div class="form-grid" id="ledger-fields">${normal}</div>${advanced?`<details><summary>高级关联</summary><div class="form-grid">${advanced}</div></details>`:''}<div class="callout" id="ledger-derived"></div>${impact}<input type="hidden" name="ledger_kind" value="${kind}">`,async form=>{
    if(!editable){$('#modal').close();return;}
    const body=ledgerRead(form,spec);if(key)body.version=item.version;
    if(form.elements.acknowledge_impacts?.checked)body.acknowledge_impacts=true;
    const saved=await api('/api/ledger/'+kind+(key?'/'+key:''),{method:key?'PUT':'POST',body});
    $('#modal').close();ledgerOptions=null;ledgerOptionsReady=false;await ledgerPage(kind);toast('已保存');
  },false,key&&!editable?'关闭':'保存');
  if(!editable){for(const el of $('#modal-form').elements)if(el.type!=='submit')el.disabled=true;}
  $('#modal-form').querySelectorAll('[data-action="ledger-toggle-password"]').forEach(button=>button.disabled=false);
  const form=$('#modal-form');form.dataset.ledgerKey=key||'';
  function vpnIntegratedAny(){
    if(kind!=='vpn')return;
    for(const side of ['local','remote']){
      const holder=form.querySelector(`[data-vlan-field="${side}_vlan_network_ids"]`);
      const choices=[...(holder?.querySelectorAll('.ledger-vlan-choice')||[])];
      const anyChoice=choices.find(row=>row.querySelector('select')?.value==='__any__');
      if(anyChoice)choices.filter(row=>row!==anyChoice).forEach(row=>row.remove());
      const any=!!anyChoice;
      const add=holder?.querySelector('[data-action="ledger-add-vlan"]');if(add)add.hidden=any;
      if(side==='remote'){
        const manual=form.querySelector('[data-rows="remote_networks"]')?.closest('.ledger-repeat');
        if(manual)manual.hidden=any;
      }
    }
  }
  function derived(){
    const data=ledgerRead(form,spec),ids=data.vlan_network_ids||data.local_vlan_network_ids||[];
    const selected=ids.map(id=>ledgerOptions.vlan_network.find(v=>v.id===id)).filter(Boolean);
    let html=data.local_network_mode==='any'?'<strong>本地 VPN 网段</strong><div>Any - 0.0.0.0/0</div>':selected.length?'<strong>关联 VLAN 网络参数（只读）</strong>'+selected.map(v=>`<div><strong>${esc(v.site_name)} · VLAN ${esc(v.vlan_number)}</strong>${ledgerNetworkHTML(v)}</div>`).join(''):'选择区域和具体 VLAN 网段后自动显示用途、网关信息。';
    const device=ledgerOptions.device.find(v=>v.id===(data.local_device_id||data.device_id||data.uplink_device_id));
    if(device)html+=`<div>关联设备：${esc(kind==='device'?ledgerUplinkLabel(device):ledgerRefLabel('device',device))}</div>`;
    if(kind==='vpn'){const remote=(data.remote_vlan_network_ids||[]).map(id=>ledgerOptions.vlan_network.find(v=>v.id===id)).filter(Boolean);html+='<hr><strong>对端 VPN 网段（只读）</strong>'+(data.remote_network_mode==='any'?'<div>Any - 0.0.0.0/0</div>':remote.map(v=>`<div>${esc(ledgerRefLabel('vlan_network',v))}${ledgerNetworkHTML(v)}</div>`).join('')||'<div>未选择 VLAN 网段，可使用手动补充对端网段。</div>');}
    $('#ledger-derived').hidden=['device','circuit'].includes(kind);
    $('#ledger-derived').innerHTML=kind==='vlan'?'在此按网段维护用途和网关，关联的 Wi-Fi 和 VPN 隧道记录会自动显示更新值。':html;
  }
  form.addEventListener('change',event=>{
    const fieldName=event.target.name||'';
    if(['site_id','remote_site_id'].includes(fieldName)){
      for(const f of spec.fields.filter(f=>['ref','refs'].includes(f.type)&&!f.ui_hidden&&!f.global_ref&&!['sites','users'].includes(f.target)&&(f.site_field||'site_id')===fieldName)){
        if(f.dropdowns){
          const holder=form.querySelector(`[data-vlan-field="${f.name}"]`),current=[...holder.querySelectorAll(`[data-ref-field="${f.name}"]`)].map(v=>v.value);
          holder.outerHTML=ledgerControl(f,current.includes('__any__')?['__any__']:[],f.name,event.target.value);
        }else{
          const el=form.elements.namedItem(f.name),fieldHolder=el.closest('.field'),rendered=document.createElement('template');
          fieldHolder?.querySelectorAll(':scope > small.help').forEach(v=>v.remove());rendered.innerHTML=ledgerControl(f,f.type==='refs'?[]:null,f.name,event.target.value);
          (el.closest('.searchable-select')||el).replaceWith(rendered.content);form.elements.namedItem(f.name).id='field-'+f.name;
        }
      }
    }
    if(fieldName.endsWith('.connection_method'))ledgerConnectionMode(event.target.closest('[data-row="connections"]'),editable);
    if(fieldName.startsWith('lines.')&&fieldName.endsWith('.line_type'))event.target.closest('[data-row="lines"]').querySelectorAll('[data-row="connections"] [name$=".line_type"]').forEach(el=>el.value=event.target.value);
    vpnIntegratedAny();derived();
  });
  form.querySelectorAll('[data-row="connections"]').forEach(row=>ledgerConnectionMode(row,editable));
  function passwordMode(){
    const el=form.elements.wifi_password;if(!el)return;
    const disabled=form.elements.auth_method.value==='none';el.disabled=disabled||!editable;if(disabled)el.value='';
    const toggle=form.querySelector('[data-action="ledger-toggle-password"]');toggle.disabled=disabled;el.type='password';toggle.textContent='显示';
  }
  form.elements.auth_method?.addEventListener('change',passwordMode);passwordMode();vpnIntegratedAny();derived();
}

async function ledgerAction(action,key,button){
  const kind=ledgerCurrent?.kind||'vlan';
  if(action==='ledger-reset-filter'){ledgerFilters={q:'',site_id:'',sort:'vlan_asc'};state.page=1;return ledgerPage(kind);}
  if(action==='ledger-list-password'){
    const holder=button.closest('.ledger-list-password'),value=holder.querySelector('span');
    if(button.dataset.revealed){value.textContent='••••••••';delete button.dataset.revealed;button.textContent='显示';return;}
    const item=await api('/api/ledger/item/'+key);value.textContent=button.dataset.field.split('.').reduce((value,key)=>value?.[key],item)||'未登记';button.dataset.revealed='1';button.textContent='隐藏';return;
  }
  if(action==='ledger-toggle-password'){
    const el=$('#modal-form').elements.namedItem(button.dataset.field);el.type=el.type==='password'?'text':'password';button.textContent=el.type==='password'?'显示':'隐藏';return;
  }
  if(action==='ledger-add-vlan'){
    const form=$('#modal-form'),holder=form.querySelector(`[data-vlan-field="${button.dataset.field}"]`),next=holder.querySelectorAll('select').length;
    const f=ledgerSpec.modules.find(v=>v.kind===form.elements.ledger_kind.value).fields.find(v=>v.name===button.dataset.field);
    button.insertAdjacentHTML('beforebegin',ledgerVlanChoice(button.dataset.field,'',Date.now(),form.elements.namedItem(f.site_field||'site_id').value));return;
  }
  if(action==='ledger-remove-vlan'){const holder=button.closest('[data-vlan-field]');button.closest('.ledger-vlan-choice').remove();holder.dispatchEvent(new Event('change',{bubbles:true}));return;}
  if(action==='ledger-add-connection'){
    const form=$('#modal-form'),line=button.closest('[data-row="lines"]'),holder=line.querySelector('[data-line-connections]'),f=ledgerSpec.modules.find(v=>v.kind==='circuit').fields.find(v=>v.name==='connections');
    holder.insertAdjacentHTML('beforeend',ledgerRow(f,{line_type:line.querySelector('[name$=".line_type"]').value,connection_method:'route'},ledgerConnectionCounter++,form.elements.site_id.value));ledgerConnectionMode(holder.lastElementChild);return;
  }
  if(action==='ledger-create'){return ledgerForm(kind);}
  if(action==='ledger-edit'){return ledgerForm(kind,key);}
  if(action==='ledger-template')return download('/api/ledger/'+kind+'/template',kind+'-template.xlsx');
  if(action==='ledger-export')return download('/api/ledger/'+kind+'/export?'+new URLSearchParams(ledgerFilters),kind+'-export.xlsx');
  if(action==='ledger-import')return formModal('导入'+ledgerSpec.modules.find(v=>v.kind===kind).title,`<p>使用本台账标准模板，先预览确认再提交。${kind==='device'?'上联设备可填同区域管理 IP，同批设备自动关联。已有设备请选择更新模式，编号留空时按区域和管理 IP 匹配。':'关联资料请先维护。'}</p><button type="button" data-action="ledger-template">下载模板</button>${field('文件','<input type="file" name="file" accept=".xlsx" required>',true)}${field('导入模式',select('mode',[{value:'create_only',name:'仅新增'},{value:'upsert',name:kind==='device'?'按编号或管理 IP 新增或更新':'按导出编号新增或更新'}],'create_only',true),true)}`,async form=>{const b=await api('/api/ledger/'+kind+'/imports',{method:'POST',body:new FormData(form)});await importReview(b.id);},false,'预览导入');
  if(action==='ledger-delete-network'){
    const obj=await api('/api/ledger/item/'+key),networkId=button.dataset.networkId,n=obj.networks.find(v=>v.network_id===networkId);
    if(!n)throw Error('网段已变化，请刷新后重试');
    return formModal('删除网段 '+n.cidr,`<p>只删除 VLAN ${esc(obj.vlan_number)} 中的 ${esc(n.purpose||'未登记用途')} - ${esc(n.cidr)}，保留此 VLAN ID 及其他网段。删除最后一个网段后仍保留空 VLAN。</p>${field('删除原因',input('reason','',true),true)}`,async form=>{
      await api('/api/ledger/vlan/'+key+'/networks/'+encodeURIComponent(networkId),{method:'DELETE',body:{version:obj.version,confirm:networkId,reason:form.elements.reason.value}});
      $('#modal').close();await ledgerPage('vlan');toast('网段已删除，VLAN 已保留');
    },false,'删除此网段');
  }
  if(action==='ledger-delete'){
    const obj=await api('/api/ledger/item/'+key);
    if(obj.kind==='vlan'&&obj.networks.length)throw Error('此 VLAN 仍有网段，请使用列表中的删除网段按钮');
    return formModal('删除 '+ledgerRefLabel(obj.kind,obj),`<p>${obj.kind==='vlan'?'此操作仅删除没有任何网段的空 VLAN 记录。':''}已有引用的资料不能删除，可以在编辑中停用。</p>${obj.dependents.length?`<div class="callout">关联资料：${obj.dependents.map(v=>esc(v.name)).join('、')}</div>`:''}${field('删除原因',input('reason','',true),true)}`,async form=>{await api('/api/ledger/item/'+key,{method:'DELETE',body:{version:obj.version,confirm:key,reason:form.elements.reason.value}});$('#modal').close();ledgerOptions=null;ledgerOptionsReady=false;await ledgerPage(kind);toast('已删除');});
  }
  if(action==='ledger-add-row'){
    const form=$('#modal-form'),spec=ledgerSpec.modules.find(v=>v.kind===form.elements.ledger_kind.value),f=spec.fields.find(v=>v.name===button.dataset.field),container=form.querySelector(`[data-rows="${f.name}"]`),count=container.children.length;
    if((f.name==='tunnels'||f.name==='lines')&&count>=2){toast('最多维护两条');return;}
    const next=count?Math.max(...[...container.querySelectorAll('[name]')].map(v=>Number(v.name.split('.')[1])))+1:0;
    const remaining=f.name==='lines'?(['primary','gift'].find(type=>![...container.querySelectorAll('[name$=".line_type"]')].some(el=>el.value===type))||'primary'):null;
    container.insertAdjacentHTML('beforeend',ledgerRow(f,f.name==='lines'?{line_type:remaining}:{},next,form.elements.site_id.value));return;
  }
  if(action==='ledger-remove-row'){button.closest('[data-row]').remove();return;}
}

document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-action^="ledger-"]');if(!button)return;
  event.preventDefault();
  try{await ledgerAction(button.dataset.action,button.dataset.id,button);}catch(error){toast(error.message);}
});

function ledgerNotes(value){return `<div class="ledger-notes">${esc(value||'—')}</div>`;}
function ledgerPassword(item,field,owner=item.id,path=field){
  if(!(item['has_'+field]||(field==='wifi_password'&&item.has_password)))return '—';
  return `<div class="ledger-list-password"><span>••••••••</span><button class="small" data-action="ledger-list-password" data-id="${esc(owner)}" data-field="${esc(path)}">显示</button></div>`;
}
function ledgerFilterHTML(kind){
  return `<form id="ledger-filter" class="filters"><input name="q" aria-label="台账关键词" placeholder="输入关键词搜索…" value="${esc(ledgerFilters.q)}"><select name="site_id" aria-label="筛选区域"><option value="">全部区域</option>${ledgerOptions.sites.map(v=>`<option value="${esc(v.id)}" ${v.id===ledgerFilters.site_id?'selected':''}>${esc(v.name)}</option>`).join('')}</select>${kind==='vlan'?`<select name="sort" aria-label="VLAN ID 排序"><option value="vlan_asc" ${ledgerFilters.sort==='vlan_asc'?'selected':''}>VLAN ID 从小到大</option><option value="vlan_desc" ${ledgerFilters.sort==='vlan_desc'?'selected':''}>VLAN ID 从大到小</option></select>`:''}<button type="submit">查询</button><button type="button" data-action="ledger-reset-filter">重置</button></form>`;
}
document.addEventListener('submit',async event=>{
  if(event.target.id!=='ledger-filter')return;
  event.preventDefault();const data=new FormData(event.target);ledgerFilters={q:data.get('q')||'',site_id:data.get('site_id')||'',sort:data.get('sort')||ledgerFilters.sort};state.page=1;
  try{await ledgerPage(ledgerCurrent.kind);}catch(error){toast(error.message);}
});
