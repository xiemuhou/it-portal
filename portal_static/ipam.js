'use strict';
let ipamOptions=null,ipamSelectedNetwork='',ipamFilters={q:'',occupancy_status:'',verification_status:'',asset_link:'',consistency_status:''},ipamItems=[];
let computerFilters={q:'',site_id:''},computerItems=[];
const ipamLabels={available:'空闲',occupied:'已占用',reserved:'预留',disabled:'停用',conflict:'冲突',pending:'待确认',consistent:'一致',confirmed:'已确认',in_use:'在用',standby:'备用',repair:'维修',retired:'报废',wired:'有线',wifi:'无线',virtual:'虚拟',other:'其他'};
const ipamText=value=>ipamLabels[value]||value||'—';
function computerMonth(value){if(!value)return '—';const [year,month]=String(value).slice(0,7).split('-');return year&&month?`${year}年${month}月`:'—';}
function computerAge(item){return item.usage_text?`<span class="computer-age ${item.is_over_five_years?'is-aged':''}">${esc(item.usage_text)}</span>`:'—';}

async function loadIpamOptions(){ipamOptions=await api('/api/ipam/options');}
function optionList(items,value='',empty='请选择'){return `<option value="">${esc(empty)}</option>${items.map(v=>`<option value="${esc(v.id)}" ${v.id===value?'selected':''}>${esc(v.name)}</option>`).join('')}`;}
function ipamStatus(value){return `<span class="ipam-status is-${esc(value)}">${value==='confirmed'?'✓ ':value==='pending'?'? ':''}${esc(ipamText(value))}</span>`;}
function consistencyStatus(value){return `<span class="ipam-status is-${esc(value)}">${value==='consistent'?'✓ ':value==='pending'?'? ':'! '}${esc(value==='pending'?'待核对':ipamText(value))}</span>`;}
function networkLabel(value){return `${value.site_name} · VLAN ${value.vlan_number} · ${value.purpose||'未登记用途'} - ${value.cidr}`;}

async function ipamPage(){
  await loadIpamOptions();
  if(ipamSelectedNetwork&&!ipamOptions.networks.some(v=>v.id===ipamSelectedNetwork))ipamSelectedNetwork='';
  if(!ipamSelectedNetwork&&ipamOptions.networks.length)ipamSelectedNetwork=ipamOptions.networks[0].id;
  const networkSelect=`<select id="ipam-network" name="network_key" aria-label="静态IP受管网段"><option value="">请选择受管网段</option>${ipamOptions.networks.map(v=>`<option value="${esc(v.id)}" ${v.id===ipamSelectedNetwork?'selected':''}>${esc(networkLabel(v))}</option>`).join('')}</select>`;
  if(!ipamSelectedNetwork){
    setPage(head('静态 IP 管理','只管理在 VLAN 规划中明确启用的静态 IPv4 网段。')+`<section class="panel"><div class="ipam-network-picker">${networkSelect}</div>${empty('暂无受管网段','请在 VLAN 规划的具体网段中开启“静态 IP 管理”。')}</section>`,'静态 IP 管理');return;
  }
  const params=new URLSearchParams({network_key:ipamSelectedNetwork,page:state.page,page_size:state.pageSize,...ipamFilters});
  const data=await api('/api/ipam/addresses?'+params);ipamItems=data.items;
  const s=data.stats;
  const rows=data.items.map(v=>{
    const personFlag=v.person_status==='departed'?'<div><span class="ipam-status is-disabled">人员已离职</span></div>':v.person_status==='missing'?'<div><span class="ipam-status is-conflict">人员不存在</span></div>':'';
    const departmentFlag=v.department_status==='missing'?'<div><span class="ipam-status is-conflict">部门不存在</span></div>':'';
    return [`<strong>${esc(v.ip_address)}</strong>`,ipamStatus(v.occupancy_status),ipamStatus(v.verification_status),v.occupancy_status==='available'?'—':tag(v.assignment_type==='shared'?'公共设备':'个人使用'),v.asset_link_status==='linked'?'<span class="ipam-status is-confirmed">✓ 已关联电脑</span>':v.asset_link_status==='candidate'?`<span class="ipam-status is-pending">! 发现匹配资产</span><div class="help">${esc(v.candidate_asset_code)} · ${esc(v.candidate_user)} · ${esc(v.candidate_device_type)}</div>`:v.asset_link_status==='non_computer'?'<span class="ipam-status">非电脑设备</span>':v.asset_link_status==='unlinked'?'<span class="ipam-status is-pending">! 未关联电脑资产</span>':'—',v.consistency_status?`${consistencyStatus(v.consistency_status)}${v.consistency_issues?.length?`<div class="help">${v.consistency_issues.map(esc).join('、')}</div>`:''}`:'—',`<div>${esc(v.department_name||'—')}</div>${departmentFlag}`,`<div>${esc(v.display_user||'—')}</div>${personFlag}`,esc(v.device_type||v.computer_name||'—'),esc(v.mac_address||'—'),esc(v.location||'—'),ledgerNotes(v.notes),v.system_reserved?'系统保留':`<div class="table-actions"><button data-action="ipam-edit" data-ip="${esc(v.ip_address)}">${v.occupancy_status==='available'?'登记':'详情 / 编辑'}</button>${v.id&&v.asset_link_status==='candidate'?`<button class="primary" data-action="ipam-reconcile" data-ip="${esc(v.ip_address)}">确认关联</button>`:v.id&&v.consistency_status==='conflict'?`<button data-action="ipam-reconcile" data-ip="${esc(v.ip_address)}">核对资料</button>`:''}${v.id&&v.occupancy_status!=='available'?`<button class="danger" data-action="ipam-release" data-ip="${esc(v.ip_address)}">释放</button>`:''}</div>`];
  });
  const filters=`<form id="ipam-filter" class="filters"><div class="ipam-network-picker">${networkSelect}</div><input name="q" placeholder="IP、使用人、MAC或设备" value="${esc(ipamFilters.q)}"><select name="occupancy_status">${optionList(['available','occupied','reserved','disabled','conflict'].map(v=>({id:v,name:ipamText(v)})),ipamFilters.occupancy_status,'全部占用状态')}</select><select name="verification_status">${optionList(['pending','confirmed'].map(v=>({id:v,name:v==='pending'?'待确认':'已确认'})),ipamFilters.verification_status,'全部确认状态')}</select><select name="asset_link">${optionList([{id:'candidate',name:'发现匹配资产'},{id:'unlinked',name:'未关联电脑资产'},{id:'linked',name:'已关联电脑'},{id:'non_computer',name:'非电脑设备'}],ipamFilters.asset_link,'全部资产关联')}</select><select name="consistency_status">${optionList([{id:'pending',name:'待核对'},{id:'conflict',name:'存在冲突'},{id:'consistent',name:'一致'}],ipamFilters.consistency_status,'全部一致性状态')}</select><button type="submit">查询</button><button type="button" data-action="ipam-reset">重置</button></form>`;
  const stats=`<div class="stats ipam-stats"><div class="stat"><span class="label">可管理地址</span><strong>${s.total}</strong></div><div class="stat"><span class="label">已占用</span><strong>${s.occupied}</strong></div><div class="stat"><span class="label">空闲</span><strong>${s.available}</strong></div><div class="stat"><span class="label">待确认</span><strong>${s.pending}</strong></div><div class="stat"><span class="label">占用冲突</span><strong>${s.conflict}</strong></div><div class="stat"><span class="label">待核对资料</span><strong>${s.needs_review}</strong></div></div>`;
  const actions=`${can('resource.import')?'<button data-action="ipam-template">下载模板</button><button data-action="ipam-import">导入</button>':''}${can('resource.export')?'<button data-action="ipam-export">导出当前网段</button>':''}`;
  setPage(head('静态 IP 管理',`${data.network.site_name} · VLAN ${data.network.vlan_number} · ${data.network.purpose||'未登记用途'} - ${data.network.cidr}`,actions)+stats+`<section class="panel">${filters}${table(['IP地址','占用状态','确认状态','归属','资产关联','资料一致性','使用部门','使用人','占用设备','MAC地址','位置','备注','操作'],rows)}${pager(data)}</section>`,'静态 IP 管理');
}

function ipamForm(item){
  const network=ipamOptions.networks.find(v=>v.id===ipamSelectedNetwork),computers=ipamOptions.computers.filter(v=>v.site_id===network.site_id);
  const occupancy=item.occupancy_status==='available'?'occupied':item.occupancy_status;
  const adapters=computers.find(v=>v.id===item.computer_id)?.adapters||[];
  const assignment=item.assignment_type||'personal';
  const personWarning=item.person_status==='departed'?'该使用人已离职，请管理员核对并重新选择责任人员。':item.person_status==='missing'?`导入的使用人“${item.display_user||''}”在系统人员中不存在，请管理员核对并选择正确人员。`:'';
  const departmentWarning=item.department_status==='missing'?`导入的部门“${item.department_name||''}”在系统部门中不存在，请管理员核对并选择正确部门。`:'';
  const warnings=[personWarning,departmentWarning].filter(Boolean).map(value=>`<div class="callout warning">${esc(value)}</div>`).join('');
  formModal('维护静态 IP · '+item.ip_address,`${warnings}<div class="form-grid" id="ipam-fields">${field('占用状态',`<select name="occupancy_status">${['occupied','reserved','disabled','conflict','available'].map(v=>`<option value="${v}" ${v===occupancy?'selected':''}>${ipamText(v)}</option>`).join('')}</select>`,true)}${field('确认状态',`<select name="verification_status"><option value="pending" ${item.verification_status!=='confirmed'?'selected':''}>待确认</option><option value="confirmed" ${item.verification_status==='confirmed'?'selected':''}>已确认</option></select>`,true)}${field('归属类型',`<select name="assignment_type"><option value="personal" ${assignment==='personal'?'selected':''}>个人使用</option><option value="shared" ${assignment==='shared'?'selected':''}>公共设备</option></select>`,true)}${field('关联电脑（可选）',`<select name="computer_id">${optionList(computers.map(v=>({id:v.id,name:`${v.asset_code} · ${v.display_user||'公共设备'} · ${v.device_type}`})),item.computer_id,'不关联电脑')}</select>`,false,'依次显示固定资产编码、使用人和设备类型；打印机、门禁等非电脑公共设备无需关联电脑。')}${field('设备网卡',`<select name="adapter_id">${optionList(adapters.filter(v=>v.enabled).map(v=>({id:v.id,name:`${ipamText(v.adapter_type)} · ${v.mac_address}`})),item.adapter_id,'不关联网卡')}</select>`)}<div class="field" data-ip-personal>${field('责任人员',`<select name="user_id">${optionList(ipamOptions.users,item.user_id,'请选择系统人员')}</select>`,true,'部门自动采用该人员的系统部门。')}</div><div class="field" data-ip-shared-department>${field('管理/使用部门',`<select name="department_id">${optionList(ipamOptions.departments,item.department_id,'不指定部门')}</select>`,false,'公共设备可独立选择系统部门，不依赖使用人。')}<input type="hidden" name="department_name_snapshot" value="${esc(item.department_name_snapshot||'')}"></div>${field('占用设备类型',`<div class="device-type-picker"><select data-device-type-choice data-native-select><option value="">请选择设备类型</option><option value="笔记本">笔记本</option><option value="台式机" ${item.device_type==='台式机'?'selected':''}>台式机</option><option value="__custom__">其他（手动填写）</option></select><input data-device-type-custom placeholder="请输入设备类型" autocomplete="off" hidden><input type="hidden" name="device_type" value="${esc(item.device_type||'')}"></div>`,false,'可选择笔记本、台式机，也可直接填写其他设备类型；关联电脑后自动采用电脑设备类型。')}${field('MAC地址',input('mac_address',item.mac_address||''))}${field('位置',input('location',item.location||''),false)}<div class="field full" data-ip-shared><div class="callout">公共设备无需选择使用人；可按需选择管理/使用部门，设备类型必填，位置可选。</div></div><div class="field full">${field('备注',`<textarea name="notes" rows="3">${esc(item.notes||'')}</textarea>`)}</div></div>`,async form=>{
    const body=Object.fromEntries(new FormData(form));body.network_key=ipamSelectedNetwork;body.ip_address=item.ip_address;if(item.id)body.version=item.version;
    await api('/api/ipam/records',{method:'POST',body});$('#modal').close();await loadIpamOptions();await ipamPage();toast(body.occupancy_status==='available'?'IP 已释放':'IP资料已保存');
  },false,'保存');
  const form=$('#modal-form'),computer=form.elements.computer_id,adapter=form.elements.adapter_id,assignmentSelect=form.elements.assignment_type,userSelect=form.elements.user_id,departmentSelect=form.elements.department_id,departmentSnapshot=form.elements.department_name_snapshot,deviceValue=form.elements.device_type,deviceChoice=form.querySelector('[data-device-type-choice]'),deviceCustom=form.querySelector('[data-device-type-custom]'),locationInput=form.elements.location;
  function requireSelect(select,required){const wrapper=select.closest('.searchable-select');if(wrapper?._setRequired)wrapper._setRequired(required);else select.required=required;}
  function setDeviceType(value,locked=false){const common=['笔记本','台式机'].includes(value);deviceChoice.value=common?value:(value?'__custom__':'');deviceCustom.value=common?'':value;deviceCustom.hidden=deviceChoice.value!=='__custom__';deviceValue.value=value||'';deviceChoice.disabled=locked;deviceCustom.readOnly=locked;}
  function syncDeviceType(){const custom=deviceChoice.value==='__custom__';deviceCustom.hidden=!custom;deviceValue.value=custom?deviceCustom.value:deviceChoice.value;syncAssignment();}
  function syncAssignment(){const shared=assignmentSelect.value==='shared',active=['occupied','conflict'].includes(form.elements.occupancy_status.value),needsDevice=active&&shared&&!computer.value;form.querySelector('[data-ip-personal]').hidden=shared;form.querySelector('[data-ip-shared-department]').hidden=!shared;form.querySelector('[data-ip-shared]').hidden=!shared;requireSelect(userSelect,active&&!shared);deviceChoice.required=needsDevice;deviceCustom.required=needsDevice&&deviceChoice.value==='__custom__';locationInput.required=false;if(shared)userSelect.value='';queueMicrotask(()=>requireSelect(userSelect,active&&!shared));}
  function applyComputer(fill=false){
    const value=computers.find(v=>v.id===computer.value),list=value?.adapters.filter(v=>v.enabled)||[];
    if(value){assignmentSelect.value=value.assignment_type||'personal';assignmentSelect.disabled=true;setDeviceType(value.device_type||'',true);}else{assignmentSelect.disabled=false;setDeviceType(deviceValue.value,false);}
    adapter.innerHTML=optionList(list.map(v=>({id:v.id,name:`${ipamText(v.adapter_type)} · ${v.mac_address}`})),fill&&list.length===1?list[0].id:adapter.value,'不关联网卡');
    syncAssignment();
  }
  computer.addEventListener('change',()=>applyComputer(true));assignmentSelect.addEventListener('change',syncAssignment);userSelect.addEventListener('change',()=>{if(assignmentSelect.value==='personal')departmentSelect.value=ipamOptions.users.find(v=>v.id===userSelect.value)?.department_id||'';});departmentSelect.addEventListener('change',()=>{departmentSnapshot.value='';});form.elements.occupancy_status.addEventListener('change',syncAssignment);deviceChoice.addEventListener('change',syncDeviceType);deviceCustom.addEventListener('input',syncDeviceType);applyComputer(false);syncAssignment();
}

async function computerPage(){
  await loadIpamOptions();const params=new URLSearchParams({page:state.page,page_size:state.pageSize,...computerFilters});const data=await api('/api/computers?'+params);computerItems=data.items;
  const filters=`<form id="computer-filter" class="filters"><input name="q" placeholder="资产编号、序列号或使用人" value="${esc(computerFilters.q)}"><select name="site_id">${optionList(ipamOptions.sites,computerFilters.site_id,'全部区域')}</select><button type="submit">查询</button><button type="button" data-action="computer-reset">重置</button></form>`;
  const rows=data.items.map(v=>[esc(v.asset_code),esc(v.device_type),v.assignment_type==='shared'?tag('公共设备'):tag('个人使用'),esc(v.site_name),esc(v.department_name||'—'),esc(v.display_user||'—'),esc(v.location||'—'),(v.adapters||[]).map(a=>`<div>${esc(ipamText(a.adapter_type))}<span class="help"> · ${esc(a.mac_address)}</span></div>`).join('')||'—',(v.ip_addresses||[]).map(ip=>`<div><strong>${esc(ip.ip_address)}</strong><span class="help"> · ${esc(ipamText(ip.verification_status))}</span></div>`).join('')||'—',esc(ipamText(v.asset_status)),computerMonth(v.acceptance_month),computerAge(v),ledgerNotes(v.notes),`<div class="table-actions"><button data-action="computer-edit" data-id="${v.id}">详情 / 编辑</button><button data-action="computer-history" data-id="${v.id}">变更记录</button>${can('resource.delete')?`<button class="danger" data-action="computer-delete" data-id="${v.id}">删除</button>`:''}</div>`]);
  const actions=`${can('resource.import')?'<button data-action="computer-template">下载模板</button><button data-action="computer-import">导入</button>':''}${can('resource.export')?'<button data-action="computer-export">导出</button>':''}${can('resource.create')?'<button class="primary" data-action="computer-create">＋ 新增电脑</button>':''}`;
  setPage(head('电脑设备台账','维护电脑基本资料和网卡，供静态 IP 记录直接关联。',actions)+`<section class="panel">${filters}${table(['资产编号','设备类型','归属','区域','部门','使用人','位置','网卡类型 / MAC','关联 IP','状态','验收日期','使用年限','备注','操作'],rows)}${pager(data)}</section>`,'电脑设备台账');
}

function importWorkbook(title,path,refresh){
  formModal(title,`${field('Excel 文件','<input type="file" name="file" accept=".xlsx" required>',true,'请使用系统下载的标准模板，单个文件不超过 20 MB。')}`,async form=>{
    const file=form.elements.file.files[0];if(!file)throw Error('请选择 XLSX 文件');const body=new FormData();body.append('file',file);
    const result=await api(path,{method:'POST',body});$('#modal').close();await refresh();
    const review=result.people_review||{},departmentReview=result.department_review||{},parts=[];if(review.departed)parts.push(`${review.departed} 条人员已离职`);if(review.missing)parts.push(`${review.missing} 条人员不存在`);if(departmentReview.missing)parts.push(`${departmentReview.missing} 条部门不存在`);
    toast(`导入完成，共处理 ${result.count} 条记录${parts.length?'；待管理员核对：'+parts.join('、'):''}`);
  },true,'开始导入');
}

function computerAdapterRow(value={},index=Date.now()){
  return `<div class="computer-network-row" data-computer-adapter><input type="hidden" name="adapters.${index}.id" value="${esc(value.id||'')}"><select name="adapters.${index}.adapter_type" aria-label="网卡类型">${['wired','wifi','virtual','other'].map(v=>`<option value="${v}" ${v===(value.adapter_type||'wired')?'selected':''}>${ipamText(v)}网卡</option>`).join('')}</select><input name="adapters.${index}.mac_address" value="${esc(value.mac_address||'')}" required placeholder="MAC 地址，如 00:11:22:33:44:55" aria-label="MAC地址"><button type="button" class="small" data-action="computer-remove-adapter">移除</button></div>`;
}
function computerAccessoryRow(value={},index=Date.now()){
  return `<div class="computer-accessory-row" data-computer-accessory><select name="accessories.${index}.accessory_type" required><option value="">配件类型</option>${['显示器','鼠标','键盘','移动硬盘','U盘','扩展坞','其他'].map(v=>`<option value="${v}" ${v===value.accessory_type?'selected':''}>${v}</option>`).join('')}</select><input name="accessories.${index}.notes" value="${esc(value.notes||'')}" placeholder="备注（可选）"><button type="button" class="small" data-action="computer-remove-accessory">移除</button></div>`;
}
function computerIpRow(value={},index=Date.now()){
  return `<div class="computer-ip-row" data-computer-ip><input name="ips.${index}.ip_address" value="${esc(value.ip_address||'')}" placeholder="IP 地址" required><select name="ips.${index}.adapter_mac" required data-ip-adapter data-value="${esc(value.mac_address||'')}"></select><button type="button" class="small" data-action="computer-remove-ip">移除</button></div>`;
}
function refreshComputerIpAdapters(){
  const adapters=$$('[data-computer-adapter]').map(row=>({mac:row.querySelector('input[name$=".mac_address"]').value.trim(),type:row.querySelector('select[name$=".adapter_type"]').value})).filter(v=>v.mac);
  $$('[data-ip-adapter]').forEach(select=>{const current=select.value||select.dataset.value;select.innerHTML='<option value="">选择网卡</option>'+adapters.map(v=>`<option value="${esc(v.mac)}" ${v.mac===current?'selected':''}>${esc(ipamText(v.type))}网卡 · ${esc(v.mac)}</option>`).join('');select.dataset.value='';});
}
function computerForm(item={}){
  const editable=item.id?can('resource.edit'):can('resource.create');
  const assignment=item.assignment_type||'personal',selectedUser=ipamOptions.users.find(v=>v.id===item.user_id);
  formModal(item.id?'详情 / 编辑电脑':'新增电脑',`<div class="form-grid" id="computer-fields">${field('资产编号',input('asset_code',item.asset_code||''),false,'留空由系统自动生成。')}${field('设备类型',`<select name="device_type" required><option value="笔记本" ${(item.device_type||'笔记本')==='笔记本'?'selected':''}>笔记本</option><option value="台式机" ${item.device_type==='台式机'?'selected':''}>台式机</option></select>`,true)}${field('验收日期（年月）',`<input name="acceptance_month" type="month" max="${new Date().toLocaleDateString('sv-SE').slice(0,7)}" value="${esc(String(item.acceptance_month||'').slice(0,7))}">`,false,item.usage_text?`当前使用年限：${item.usage_text}`:'填写后自动计算使用年限。')}${field('归属类型',`<select name="assignment_type"><option value="personal" ${assignment==='personal'?'selected':''}>个人使用</option><option value="shared" ${assignment==='shared'?'selected':''}>公共设备</option></select>`,true)}${field('区域',`<select name="site_id" required>${optionList(ipamOptions.sites,item.site_id,'请选择区域')}</select>`,true)}${field('品牌',input('brand',item.brand||''))}${field('型号',input('model',item.model||''))}${field('序列号',input('serial_number',item.serial_number||''))}<div class="field" data-personal-owner>${field('使用人',`<select name="user_id">${optionList(ipamOptions.users,item.user_id,'请选择系统人员')}</select>`,true,'选择后自动带出部门。')}</div><div class="field" data-personal-owner>${field('部门',`<input data-computer-department value="${esc(selectedUser?.department_name||'')}" disabled placeholder="由使用人自动带出">`)}</div><div class="field full" data-shared-note><div class="callout">公共设备无需填写使用人和部门；使用位置和备注均可按实际情况填写。</div></div>${field('位置',input('location',item.location||''))}${field('操作系统',input('operating_system',item.operating_system||''))}${field('设备状态',`<select name="asset_status">${['in_use','standby','repair','retired'].map(v=>`<option value="${v}" ${v===(item.asset_status||'in_use')?'selected':''}>${ipamText(v)}</option>`).join('')}</select>`)}<section class="computer-adapters field full"><h3>静态 IP 与网卡</h3><div id="computer-ip-list">${(item.ip_addresses||[]).map((v,i)=>computerIpRow(v,i)).join('')}</div><button type="button" data-action="computer-add-ip">＋ 添加 IP</button><p class="help">每个 IP 必须选择实际占用它的网卡；保存后自动占用，移除后自动释放。</p></section><div class="field full">${field('备注',`<textarea name="notes" rows="3">${esc(item.notes||'')}</textarea>`)}</div></div><section class="computer-adapters"><h3>设备网卡</h3><div id="computer-adapter-list">${(item.adapters||[]).map((v,i)=>computerAdapterRow(v,i)).join('')}</div><button type="button" data-action="computer-add-adapter">＋ 添加网卡</button></section><section class="computer-adapters"><h3>电脑配件</h3><div id="computer-accessory-list">${(item.accessories||[]).map((v,i)=>computerAccessoryRow(v,i)).join('')}</div><button type="button" data-action="computer-add-accessory">＋ 添加配件</button>${item.id?`<div class="issued-consumables"><h4>耗材领用记录</h4>${(item.consumable_issues||[]).length?(item.consumable_issues||[]).map(v=>`<div class="notice"><span><strong>${esc(v.name)}</strong>${v.specification?` · ${esc(v.specification)}`:''}<small class="help">${esc(v.quantity)} ${esc(v.unit_snapshot)} · ${day(v.occurred_on)}${v.purpose?' · '+esc(v.purpose):''}</small></span></div>`).join(''):'<p class="help">暂无关联到此电脑的耗材出库记录。</p>'}<p class="help">此处来自耗材出库流水，请在“耗材管理”中登记和查询。</p></div>`:''}</section>`,async form=>{
    const body=Object.fromEntries([...new FormData(form)].filter(([key])=>!key.startsWith('adapters.')&&!key.startsWith('accessories.')));body.adapters=[...form.querySelectorAll('[data-computer-adapter]')].map(row=>{const value={};row.querySelectorAll('[name]').forEach(el=>{const key=el.name.split('.').pop();value[key]=['enabled','is_primary'].includes(key)?el.value==='1':el.value;});return value;});body.ip_assignments=[...form.querySelectorAll('[data-computer-ip]')].map(row=>({ip_address:row.querySelector('[name$=".ip_address"]').value,adapter_mac:row.querySelector('[name$=".adapter_mac"]').value}));body.accessories=[...form.querySelectorAll('[data-computer-accessory]')].map(row=>{const value={};row.querySelectorAll('[name]').forEach(el=>value[el.name.split('.').pop()]=el.value);return value;});if(item.id)body.version=item.version;
    await api('/api/computers'+(item.id?'/'+item.id:''),{method:item.id?'PUT':'POST',body});$('#modal').close();await computerPage();toast('电脑设备已保存');
  },false,editable?'保存':'关闭');
  const form=$('#modal-form'),assignmentSelect=form.elements.assignment_type,userSelect=form.elements.user_id,departmentInput=form.querySelector('[data-computer-department]');
  function syncOwner(){const shared=assignmentSelect.value==='shared';form.querySelectorAll('[data-personal-owner]').forEach(v=>v.hidden=shared);form.querySelector('[data-shared-note]').hidden=!shared;const wrapper=userSelect.closest('.searchable-select');if(wrapper?._setRequired)wrapper._setRequired(!shared);else userSelect.required=!shared;if(shared){userSelect.value='';departmentInput.value='';}else departmentInput.value=ipamOptions.users.find(v=>v.id===userSelect.value)?.department_name||'';queueMicrotask(()=>{const current=userSelect.closest('.searchable-select');if(current?._setRequired)current._setRequired(!shared);});}
  assignmentSelect.addEventListener('change',syncOwner);userSelect.addEventListener('change',syncOwner);syncOwner();refreshComputerIpAdapters();if(!editable)[...form.elements].forEach(v=>v.disabled=true);
}

async function ipamAction(action,button){
  if(action==='ipam-open'){ipamSelectedNetwork=button.dataset.network;location.hash='ipam';}
  else if(action==='ipam-edit'){const item=ipamItems.find(v=>v.ip_address===button.dataset.ip);if(!item)throw Error('IP列表已变化，请刷新');ipamForm(item);}
  else if(action==='ipam-release'){
    const item=ipamItems.find(v=>v.ip_address===button.dataset.ip);if(!item?.id)throw Error('IP记录已变化，请刷新');
    formModal('释放 IP · '+item.ip_address,'<div class="callout warning">释放后将清除该 IP 的使用人、设备、MAC、位置及关联电脑信息，操作会保留在历史记录中。</div>',async()=>{
      await api('/api/ipam/records',{method:'POST',body:{network_key:ipamSelectedNetwork,ip_address:item.ip_address,version:item.version,occupancy_status:'available',verification_status:'pending'}});$('#modal').close();await ipamPage();toast('IP 已释放');
    },true,'确认释放');
  }
  else if(action==='ipam-reconcile'){
    const item=ipamItems.find(v=>v.ip_address===button.dataset.ip);if(!item?.id)throw Error('IP记录已变化，请刷新');
    modal(item.asset_link_status==='candidate'?'确认关联电脑资产':'核对 IP 与电脑资料',`<div class="callout warning"><strong>${esc(item.ip_address)}</strong><p>${(item.consistency_issues||[]).map(esc).join('、')}</p>${item.asset_link_status==='candidate'?`<p>匹配电脑：${esc(item.candidate_asset_code)} · ${esc(item.candidate_user)} · ${esc(item.candidate_device_type)}</p>`:''}</div><p>请选择采用哪一侧的归属类型、部门、使用人、设备类型和位置。MAC 地址始终采用匹配到的电脑网卡信息。</p><div class="form-footer"><button data-action="ipam-reconcile-to" data-ip="${esc(item.ip_address)}">${item.asset_link_status==='candidate'?'关联并':''}以 IP 记录为准</button><button class="primary" data-action="ipam-reconcile-from" data-ip="${esc(item.ip_address)}">${item.asset_link_status==='candidate'?'关联并':''}以电脑台账为准</button></div>`,null,true);
  }
  else if(action==='ipam-reconcile-from'||action==='ipam-reconcile-to'){
    const item=ipamItems.find(v=>v.ip_address===button.dataset.ip);if(!item?.id)throw Error('IP记录已变化，请刷新');
    await api('/api/ipam/records/'+item.id+'/reconcile',{method:'POST',body:{version:item.version,action:action.endsWith('-from')?'from_computer':'to_computer'}});$('#modal').close();await loadIpamOptions();await ipamPage();toast('资料核对已完成');
  }
  else if(action==='ipam-template')await download('/api/ipam-transfers/template','静态IP导入模板.xlsx');
  else if(action==='ipam-export')await download('/api/ipam-transfers/export?network_key='+encodeURIComponent(ipamSelectedNetwork),'静态IP记录.xlsx');
  else if(action==='ipam-import')importWorkbook('导入静态 IP','/api/ipam-transfers/import',ipamPage);
  else if(action==='ipam-reset'){ipamFilters={q:'',occupancy_status:'',verification_status:'',asset_link:'',consistency_status:''};state.page=1;await ipamPage();}
  else if(action==='computer-template')await download('/api/computer-transfers/template','电脑设备导入模板.xlsx');
  else if(action==='computer-export')await download('/api/computer-transfers/export','电脑设备台账.xlsx');
  else if(action==='computer-import')importWorkbook('导入电脑设备','/api/computer-transfers/import',computerPage);
  else if(action==='computer-create')computerForm();
  else if(action==='computer-edit')computerForm(await api('/api/computers/'+button.dataset.id));
  else if(action==='computer-history'){
    const result=await api('/api/computers/'+button.dataset.id+'/history');modal('电脑变更记录',result.items.length?result.items.map(v=>`<div class="notice"><div><strong>${esc(v.change_summary)}</strong><div class="help">${esc(v.actor_name)} · ${time(v.created_at)}</div></div></div>`).join(''):empty('暂无变更记录'),false,false);
  }
  else if(action==='computer-delete'){
    const item=computerItems.find(v=>v.id===button.dataset.id);if(!item)throw Error('电脑列表已变化，请刷新');
    formModal('删除电脑',`<div class="callout warning">将删除电脑 ${esc(item.asset_code)} 及其网卡。若仍关联静态 IP，系统会阻止删除。</div>${field('删除原因',input('reason','',true),true)}`,async form=>{
      await api('/api/computers/'+item.id,{method:'DELETE',body:{version:item.version,reason:form.elements.reason.value}});$('#modal').close();await computerPage();toast('电脑已删除');
    },true,'确认删除');
  }
  else if(action==='computer-reset'){computerFilters={q:'',site_id:''};state.page=1;await computerPage();}
  else if(action==='computer-add-adapter'){$('#computer-adapter-list').insertAdjacentHTML('beforeend',computerAdapterRow());refreshComputerIpAdapters();}
  else if(action==='computer-remove-adapter'){button.closest('[data-computer-adapter]').remove();refreshComputerIpAdapters();}
  else if(action==='computer-add-ip'){$('#computer-ip-list').insertAdjacentHTML('beforeend',computerIpRow());refreshComputerIpAdapters();}
  else if(action==='computer-remove-ip')button.closest('[data-computer-ip]').remove();
  else if(action==='computer-add-accessory')$('#computer-accessory-list').insertAdjacentHTML('beforeend',computerAccessoryRow());
  else if(action==='computer-remove-accessory')button.closest('[data-computer-accessory]').remove();
}

document.addEventListener('change',async event=>{
  if(event.target.id==='ipam-network'){ipamSelectedNetwork=event.target.value;state.page=1;try{await ipamPage();}catch(error){toast(error.message);}}
  if(event.target.matches('[data-computer-adapter] input[name$=".mac_address"]'))refreshComputerIpAdapters();
  if(event.target.matches('[data-computer-adapter] select[name$=".adapter_type"]'))refreshComputerIpAdapters();
});
document.addEventListener('submit',async event=>{
  if(event.target.id==='ipam-filter'){event.preventDefault();const data=new FormData(event.target);ipamFilters={q:data.get('q')||'',occupancy_status:data.get('occupancy_status')||'',verification_status:data.get('verification_status')||'',asset_link:data.get('asset_link')||'',consistency_status:data.get('consistency_status')||''};state.page=1;try{await ipamPage();}catch(error){toast(error.message);}}
  if(event.target.id==='computer-filter'){event.preventDefault();const data=new FormData(event.target);computerFilters={q:data.get('q')||'',site_id:data.get('site_id')||''};state.page=1;try{await computerPage();}catch(error){toast(error.message);}}
});
