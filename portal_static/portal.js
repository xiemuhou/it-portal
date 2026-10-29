'use strict';
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state={user:null,lookup:{},catalog:[],roles:[],page:1,pageSize:10,q:'',status:'',kind:'',departmentId:'',archived:false,items:[],route:'',database:'',unreadNotifications:0,monitorUrl:'https://monitor.example.com/'};
const names={pending:'待接单',in_progress:'处理中',closed:'已关闭',cancelled:'已取消',draft:'草稿',published:'已发布',withdrawn:'已撤下',
  device:'网络设备',circuit:'宽带线路',vlan:'VLAN',subnet:'子网',wifi:'Wi-Fi',vpn:'VPN 连接',active:'启用',disabled:'停用',
  unknown:'未登记',in_use:'在用',standby:'备用',maintenance:'维修',retired:'退役',verified:'已核对',
  own:'本人',assigned:'当前负责',site:'指定区域',department:'指定部门',all:'全部',none:'功能权限'};
const events={created:'提交工单',claimed:'接单并开始处理',assigned:'分配处理人',transferred:'转派同事',closed:'关闭工单',cancelled:'取消工单',reopened:'重新打开',comment:'留言',internal_note:'内部备注',time_corrected:'纠正分类/时间',edited:'修改问题描述'};
const subtype={device:'devices',circuit:'circuits',vlan:'vlans',subnet:'subnets',wifi:'wifi_networks',vpn:'vpn_connections'};
const time=v=>v?new Date(v).toLocaleString('zh-CN',{hour12:false}):'—';
const minuteTime=v=>v?new Date(v).toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}):'—';
const day=v=>v?new Date(v).toLocaleDateString('zh-CN'):'—';
const duration=v=>{if(v==null)return '—';if(v>0&&v<60000)return '不足 1 分';const minutes=Math.floor(v/60000),hours=Math.floor(minutes/60),rest=minutes%60;return hours?`${hours} 小时 ${rest} 分`:`${minutes} 分`;};
const can=p=>!!state.user?.grants?.[p]?.length;
const tag=v=>`<span class="tag ${esc(v)}">${esc(names[v]||v||'—')}</span>`;
const organizationSource=value=>value==='ehr'?'EHR同步':value==='ldap'?'LDAP同步':'手工维护';
let modalHandler=null,modalContext=null,currentTicket=null,renderToken=0;
let aiMessages=[];

function fuzzyMatch(label,query){
  const text=label.toLocaleLowerCase(),terms=query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  return terms.every(term=>{if(text.includes(term))return true;let index=0;for(const char of text)if(char===term[index])index++;return index===term.length;});
}
function enhanceSearchableSelect(selectElement){
  if(selectElement.dataset.searchableReady||selectElement.matches('[data-native-select]'))return;selectElement.dataset.searchableReady='1';
  const wrapper=document.createElement('div');wrapper.className='searchable-select';selectElement.parentNode.insertBefore(wrapper,selectElement);wrapper.appendChild(selectElement);selectElement.classList.add('searchable-select-native');
  const search=document.createElement('input');search.type='text';search.className='searchable-select-input';search.autocomplete='off';search.setAttribute('role','combobox');search.setAttribute('aria-expanded','false');search.setAttribute('aria-label',selectElement.getAttribute('aria-label')||'搜索并选择');wrapper.insertBefore(search,selectElement);
  const menu=document.createElement('div');menu.className='searchable-select-menu';menu.setAttribute('role','listbox');wrapper.appendChild(menu);
  let required=selectElement.required;selectElement.required=false;search.required=required;let open=false;
  const valueDescriptor=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value');
  Object.defineProperty(selectElement,'value',{configurable:true,get(){return valueDescriptor.get.call(this);},set(value){valueDescriptor.set.call(this,value);queueMicrotask(sync);}});
  function selectedText(){const values=[...selectElement.selectedOptions].filter(v=>v.value).map(v=>v.textContent.trim());return selectElement.multiple?(values.length?`已选择 ${values.length} 项：${values.join('、')}`:''):values[0]||'';}
  function validate(){search.setCustomValidity(required&&!selectElement.value?'请选择一个选项':'');}
  function sync(){if(!open)search.value=selectedText();search.placeholder=selectElement.options[0]?.value===''?selectElement.options[0].textContent.trim():'输入关键词搜索';search.disabled=selectElement.disabled;validate();}
  function close(){open=false;wrapper.classList.remove('open');search.setAttribute('aria-expanded','false');search.value=selectedText();validate();}
  function render(query=''){
    const options=[...selectElement.options].filter(v=>fuzzyMatch(v.textContent,query));menu.innerHTML='';
    for(const option of options.slice(0,100)){
      const item=document.createElement('button');item.type='button';item.className='searchable-select-option'+(option.selected?' selected':'');item.textContent=option.textContent;item.dataset.value=option.value;item.setAttribute('role','option');item.setAttribute('aria-selected',String(option.selected));item.disabled=option.disabled;menu.appendChild(item);
    }
    if(!options.length){const empty=document.createElement('div');empty.className='searchable-select-empty';empty.textContent='未找到匹配项';menu.appendChild(empty);}
    else if(options.length>100){const more=document.createElement('div');more.className='searchable-select-empty';more.textContent=`还有 ${options.length-100} 项，请继续输入关键词`;menu.appendChild(more);}
  }
  function show(){document.querySelectorAll('.searchable-select.open').forEach(v=>{if(v!==wrapper)v._close?.();});open=true;wrapper.classList.add('open');search.setAttribute('aria-expanded','true');search.select();render('');}
  wrapper._close=close;wrapper._setRequired=value=>{required=!!value;selectElement.required=false;search.required=required;validate();};search.addEventListener('focus',show);search.addEventListener('click',show);search.addEventListener('input',()=>{if(!open)show();render(search.value);validate();});
  search.addEventListener('keydown',event=>{if(event.key==='Escape'){close();search.blur();}else if(event.key==='Enter'&&open){const first=menu.querySelector('.searchable-select-option:not(:disabled)');if(first){event.preventDefault();first.click();}}});
  menu.addEventListener('mousedown',event=>event.preventDefault());menu.addEventListener('click',event=>{const item=event.target.closest('.searchable-select-option');if(!item)return;const option=[...selectElement.options].find(v=>v.value===item.dataset.value);if(!option)return;if(selectElement.multiple){option.selected=!option.selected;search.value='';render('');}else{selectElement.value=option.value;close();}selectElement.dispatchEvent(new Event('change',{bubbles:true}));validate();});
  selectElement.addEventListener('change',sync);new MutationObserver(()=>{sync();if(open)render(search.value);}).observe(selectElement,{childList:true,subtree:true,attributes:true});sync();
}
function installSearchableSelects(){
  document.querySelectorAll('select').forEach(enhanceSearchableSelect);new MutationObserver(records=>records.forEach(record=>record.addedNodes.forEach(node=>{if(node.nodeType!==1)return;if(node.matches?.('select'))enhanceSearchableSelect(node);node.querySelectorAll?.('select').forEach(enhanceSearchableSelect);}))).observe(document.body,{childList:true,subtree:true});
  document.addEventListener('mousedown',event=>{if(!event.target.closest('.searchable-select'))document.querySelectorAll('.searchable-select.open').forEach(v=>v._close?.());});
}

async function api(path,{method='GET',body,activity=true,headers={}}={}){
  const opts={method,credentials:'same-origin',cache:'no-store',headers:{...headers}};
  if(activity)opts.headers['X-Portal-Activity']='1';
  if(method!=='GET'&&state.user)opts.headers['X-CSRF-Token']=state.user.csrf;
  if(body instanceof FormData)opts.body=body;
  else if(body!==undefined){opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(body);}
  const res=await fetch(path,opts);const type=res.headers.get('content-type')||'';
  const result=type.includes('application/json')?await res.json():await res.blob();
  if(!res.ok){if(res.status===401&&state.user){state.user=null;navigation();}throw Error(result.error||'请求未能完成');}
  return result;
}
function toast(message){$('#toast').textContent=message;$('#toast').classList.add('show');setTimeout(()=>$('#toast').classList.remove('show'),4000);}
function modal(title,content,handler=null,narrow=false){
  $('#modal').classList.toggle('narrow',narrow);$('#modal-content').innerHTML=`<h2>${esc(title)}</h2>${content}`;
  modalHandler=handler;if(!$('#modal').open)$('#modal').showModal();
}
function formModal(title,content,handler,narrow=false,submit='保存'){
  modal(title,`<form id="modal-form"><div class="modal-error"></div>${content}<div class="form-footer"><button type="button" data-action="close-modal">取消</button><button class="primary" type="submit">${esc(submit)}</button></div></form>`,handler,narrow);
}
const field=(label,control,required=false,help='')=>{
  const name=control.match(/name="([^"]+)"/)?.[1];const id=name?'field-'+name:'';
  if(id)control=control.replace(/<(input|textarea|select)\b([^>]*\bname="[^"]+"[^>]*)>/,`<$1 id="${esc(id)}"$2>`);
  return `<div class="field"><label ${id?`for="${esc(id)}"`:''}>${esc(label)}${required?'<span class="required">*</span>':''}</label>${control}${help?`<small class="help">${esc(help)}</small>`:''}</div>`;
};
const input=(name,value='',required=false,type='text')=>`<input name="${esc(name)}" type="${esc(type)}" value="${esc(value)}" ${required?'required':''}>`;
function select(name,items,value='',required=false,multiple=false){
  return `<select name="${esc(name)}" ${required?'required':''} ${multiple?'multiple size="5"':''}>${!multiple?`<option value="">${required?'请选择':'不选择'}</option>`:''}${items.map(v=>`<option value="${esc(v.id??v.value)}" ${multiple?(value||[]).includes(v.id??v.value)?'selected':'':String(value??'')===String(v.id??v.value)?'selected':''}>${esc(v.name??v.label)}</option>`).join('')}</select>`;
}
function head(title,description,actions=''){return `<div class="page-head"><div><h1>${esc(title)}</h1><p class="lead">${esc(description)}</p></div><div class="actions">${actions}</div></div>`;}
function empty(title='暂无数据',description='有数据后会展示在这里。'){return `<div class="empty"><strong>${esc(title)}</strong>${esc(description)}</div>`;}
function pager(data){const pages=Math.max(1,Math.ceil(data.total/data.page_size));return `<div class="pager"><span>共 ${data.total} 条 · 第 ${data.page} / ${pages} 页</span><label class="pager-size">每页 <select data-action="page-size" data-native-select aria-label="每页显示条数">${[10,20,50].map(size=>`<option value="${size}" ${data.page_size===size?'selected':''}>${size} 条</option>`).join('')}</select></label><button class="small" data-action="page" data-value="${data.page-1}" ${data.page<=1?'disabled':''}>上一页</button><button class="small" data-action="page" data-value="${data.page+1}" ${data.page>=pages?'disabled':''}>下一页</button><form class="pager-jump" data-pages="${pages}"><label>跳至 <input name="page" type="number" min="1" max="${pages}" value="${data.page}" aria-label="要跳转的页码"> 页</label><button class="small" type="submit">跳转</button></form></div>`;}
function table(headers,rows){return rows.length?`<div class="table-scroll"><table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(c=>`<tr>${c.map(v=>`<td>${v}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:empty();}
function filter(extra=''){return `<form id="filter-form" class="filters"><input name="q" value="${esc(state.q)}" placeholder="输入关键词搜索…">${extra}<button type="submit">查询</button><button type="button" data-action="reset-filter" class="quiet">重置</button></form>`;}
function setPage(content,title){$('#main').innerHTML=content;$('#page-title').textContent=title;document.title=title+' · IT 服务门户';navigation();}
function navigation(){
  const entries=[['员工服务',[['home','⌂','服务概览'],['new-ticket','＋','提交工单'],['knowledge','▤','知识库'],['announcements','◇','公告'],['services','▦','服务目录'],['monitoring','⌁','网络运维态势',state.monitorUrl]]]];
  if(state.user){
    entries[0][1].push(['quick-links','▦','快捷链接']);
    const work=[];
    if(can('ticket.view'))work.push(['tickets','▣',can('ticket.claim')?'工单工作台':'我的工单']);
    if(can('report.view'))work.push(['reports','▥','运维分类汇总']);
    if(can('resource.view')){work.push(['ledger/vlan','▧','基础信息台账']);work.push(['ipam','▦','静态 IP 管理']);work.push(['computers','▤','电脑设备台账']);}
    if(can('consumable.view'))work.push(['consumables','▥','耗材管理']);
    if(can('memo.view'))work.push(['memos','▤','IT 备忘录']);
    if(work.length)entries.push(['协作与运维',work]);
    const admin=[];
    if(can('user.view')||can('directory.view'))admin.push(['organization','♙','部门与人员']);
    if(can('role.view'))admin.push(['roles','⚑','角色与权限']);
    if(can('announcement.view'))admin.push(['data/announcements','◇','公告管理']);
    if(can('knowledge.view'))admin.push(['knowledge-admin','▤','知识管理']);
    if(can('category.view')||can('directory.view'))admin.push(['data/ticket_categories','≡','基础资料']);
    if(can('audit.view'))admin.push(['audit','◷','操作审计']);
    if(can('settings.edit'))admin.push(['ai-settings','✦','AI 助手设置']);
    if(admin.length)entries.push(['管理中心',admin]);
  }
  const current=location.hash.slice(1)||'home';
  $('#nav').innerHTML=entries.map(([label,links])=>`<div class="nav-heading">${esc(label)}</div>${links.map(([path,icon,name,external])=>`<a class="nav-item ${!external&&(current===path||(path==='tickets'&&current.startsWith('ticket/'))||(path==='organization'&&current.startsWith('organization')))?'active':''}" href="${external?esc(external):'#'+path}" ${external?'target="_blank" rel="noopener"':''}><span class="nav-icon">${icon}</span>${esc(name)}${external?'<span class="external-mark">↗</span>':''}</a>`).join('')}`).join('');
  const unread=Math.min(Number(state.unreadNotifications)||0,99);
  $('#account').innerHTML=state.user?`<a class="notification-button ${unread?'has-unread':''}" href="#notifications" aria-label="站内消息，${unread} 条未读" title="站内消息"><span aria-hidden="true">🔔</span><b>${unread===99&&state.unreadNotifications>99?'99+':unread}</b></a><span class="avatar">${esc(state.user.display_name.slice(0,1))}</span><span>${esc(state.user.display_name)}</span><button class="quiet small" data-action="password">修改密码</button><button class="small" data-action="logout">退出</button>`:`<span class="muted">欢迎访问 IT 服务门户</span><button class="primary small" data-action="login">账号登录</button>`;
}
async function refreshUnreadCount(render=false){if(!state.user){state.unreadNotifications=0;return;}const result=await api('/api/notifications/unread-count',{activity:false});state.unreadNotifications=result.unread_count||0;if(render)navigation();}
async function loadPrivate(){
  if(!state.user)return;
  state.lookup=await api('/api/lookups');
  if(can('resource.view')||can('directory.view')||can('knowledge.view')||can('category.view')||can('announcement.view'))state.catalog=(await api('/api/catalog')).modules;
}
async function init(){
  installSearchableSelects();
  try{const s=await api('/api/session',{activity:false});state.user=s.user;state.database=s.database;
    $('#environment').textContent=s.database==='sqlite'?'本地开发验证 · SQLite 独立数据库':s.database==='mssql'?'SQL Server 业务数据库':'MySQL 业务数据库';
    await loadPrivate();await route();
  }catch(error){setPage(`<div class="error">${esc(error.message)}</div>`,'连接异常');}
}
async function loginDialog(){
  formModal('登录服务门户',`<div class="login-logo">it•</div><p class="muted">提交与跟进工单，或进入 IT 工作台。</p>${field('账号',input('login_name','',true),true)}${field('密码',input('password','',true,'password'),true)}`,
    async form=>{const body=Object.fromEntries(new FormData(form));const s=await api('/api/auth/login',{method:'POST',body});state.user=s.user;await loadPrivate();$('#modal').close();toast('登录成功');await route();},true,'登录');
}
async function route(){
  const token=++renderToken;const path=location.hash.slice(1)||'home';
  if(path!==state.route){state.page=1;state.q='';state.status='';state.kind='';state.departmentId='';state.archived=false;state.route=path;}
  try{
    const publicRoutes=['home','knowledge','announcements','services'];
    if(!state.user&&!publicRoutes.includes(path)){setPage(head('登录后继续','使用管理员为你创建的账号登录。')+`<div class="panel">${empty('你的服务，随时跟进','登录后可以提交工单、查看处理进展并与 IT 留言。')}<div class="actions"><button class="primary" data-action="login">账号登录</button></div></div>`,'账号登录');await loginDialog();return;}
    if(state.user)await refreshUnreadCount();
    if(path==='home')await home();
    else if(path==='new-ticket')await newTicket();
    else if(path==='tickets')await ticketList();
    else if(path.startsWith('ticket/'))await ticketDetail(path.split('/')[1]);
    else if(path==='knowledge'||path==='knowledge-admin')await knowledge(path==='knowledge-admin');
    else if(path==='announcements')await announcements();
    else if(path==='services')await services();
    else if(path==='quick-links')await quickLinks();
    else if(path==='reports')await reports();
    else if(path==='users')await users();
    else if(path==='organization'||path.startsWith('organization/'))await organizationPage(path.split('/')[1]||'departments');
    else if(path==='roles')await roles();
    else if(path.startsWith('ledger/'))await ledgerPage(path.split('/')[1]);
    else if(path==='ipam')await ipamPage();
    else if(path==='computers')await computerPage();
    else if(path==='consumables')await consumablePage();
    else if(path.startsWith('consumables/history/'))await consumableHistoryPage(path.split('/')[2]);
    else if(path==='memos')await memoPage();
    else if(path==='data/resources'||path.startsWith('data/')&&state.catalog.find(v=>v.table===path.split('/')[1])?.module==='resource')await ledgerPage(({vlans:'vlan',wifi_networks:'wifi',devices:'device',circuits:'circuit',vpn_connections:'vpn'})[path.split('/')[1]]||'vlan');
    else if(path.startsWith('data/'))await dataPage(path.split('/')[1]);
    else if(path==='notifications')await notifications();
    else if(path==='audit')await auditPage();
    else if(path==='ai-settings')await aiSettingsPage();
    else setPage(empty('页面不存在'),'页面不存在');
  }catch(error){if(token===renderToken)setPage(`<div class="error">${esc(error.message)}</div><button data-action="reload">重新加载</button>`,'加载未完成');}
}
async function home(){
  const p=await api('/api/public');const kb=await api('/api/knowledge');
  state.monitorUrl=p.monitor_url||state.monitorUrl;navigation();
  setPage(`<section class="hero"><div><div class="eyebrow">YOUR EVERYDAY IT PARTNER</div><h1>让问题有人响应<br>让服务有据可查</h1><p>工作中的技术问题，从这里得到支持。<br>查阅操作手册、提交服务工单，与 IT 一起解决。</p><div class="actions"><a class="button primary" href="#new-ticket">提交服务工单 <span>→</span></a><a class="button" href="#knowledge">查阅知识库</a></div></div><div class="hero-art" aria-hidden="true"><div class="hero-orbit"></div><span class="hero-it">it•</span><span class="hero-tag a">服务 · 连接</span><span class="hero-tag b">协作 · 保障</span></div></section>
    <div class="grid"><a class="service-card" href="#new-ticket"><div class="icon-block">＋</div><h3>服务支持</h3><p>描述遇到的问题，IT 接单处理，进度随时可见。</p></a><a class="service-card" href="#knowledge"><div class="icon-block">▤</div><h3>自助知识库</h3><p>先看看操作指南，也许几步就能解决问题。</p></a><a class="service-card" href="${esc(p.monitor_url)}" target="_blank" rel="noopener"><div class="icon-block">⌁</div><h3>网络运维态势</h3><p>打开现有态势系统，查看网络运行情况。</p></a></div>
    <div class="grid two" style="margin-top:25px"><section class="panel"><div class="panel-title"><h2>公司 IT 公告</h2><a href="#announcements">全部公告 →</a></div>${p.announcements.length?p.announcements.map(a=>`<div class="notice">${a.is_pinned?'<span class="tag">置顶</span>':''}<a href="#announcements" data-action="announcement" data-id="${a.id}">${esc(a.title)}</a><span class="date">${esc(a.publisher_name||'IT')} · ${day(a.published_at)}</span></div>`).join(''):empty('暂无公告','IT 发布的服务信息会展示在这里。')}</section><section class="panel"><div class="panel-title"><h2>常用操作手册</h2><a href="#knowledge">进入知识库 →</a></div>${kb.items.length?kb.items.slice(0,5).map(a=>`<div class="notice"><a href="${esc(a.reader_url)}" target="_blank" rel="noopener">${esc(a.title)}</a><span class="date">阅读 →</span></div>`).join(''):empty('暂无已发布手册','手册由 IT 整理、审核后发布。')}</section></div>
    `,'服务概览');
}
async function newTicket(){
  const aiStatus=await api('/api/ai/status');aiMessages=[];
  const assistant=aiStatus.enabled?`<section class="panel ai-panel"><div class="ai-panel-head"><div><h2><span class="ai-mark">✦</span> 问问 IT AI</h2><p class="muted">提交前先让 AI 帮你排查。</p></div><button class="quiet small" data-action="ai-use-description">使用问题描述</button></div><div id="ai-messages" class="ai-messages" aria-live="polite"><div class="ai-message assistant">你好，我可以先帮你分析问题。请描述现象、报错信息和已经尝试过的操作。</div></div><form id="ai-chat-form" class="ai-chat-form"><textarea name="message" required maxlength="4000" rows="3" placeholder="输入问题，请勿填写密码、验证码或访问令牌…"></textarea><button class="primary" type="submit">发送</button></form><p class="ai-disclosure">对话和命中的已发布知识片段会发送到管理员配置的 AI 服务；聊天内容不会保存到门户数据库。AI 建议仅供排查参考。</p><div id="ai-recommendations"></div></section>`:`<section class="panel"><h2>自助解决</h2><div class="callout">AI 助手尚未启用，你可以先查阅知识库或直接提交工单。</div><a class="button" href="#knowledge" target="_blank" rel="noopener">打开知识库 →</a><button class="quiet" data-action="recommend">根据描述查找手册</button><div id="recommendations"></div></section>`;
  setPage(head('提交服务工单','说说遇到的情况，我们一起解决。')+`<div class="ticket-grid"><section class="panel"><form id="new-ticket-form"><div id="ticket-error"></div>${field('问题描述','<textarea name="description" required rows="9" maxlength="20000" placeholder="请描述问题现象、发生位置或错误提示…"></textarea>',true)}<div class="form-grid">${field('发生区域',select('site_id',state.lookup.sites||[]))}${field('具体位置',input('location_text'))}${field('联系方式',input('contact',state.user.phone||''))}${field('截图或附件','<input type="file" name="files" multiple accept=".png,.jpg,.jpeg,.pdf">',false,'PNG、JPG、PDF，单个不超过 20 MB，最多 5 个。')}</div><div class="form-footer"><button class="primary" type="submit">提交工单 →</button></div></form></section><aside>${assistant}<div class="callout">AI 没有解决问题时可直接提交。IT 接单后开始处理，你可以在工单中补充信息和留言。</div></aside></div>`,'提交工单');
}

function renderAiConversation(recommendations=[],meta=null){
  const box=$('#ai-messages');if(!box)return;
  box.innerHTML=`<div class="ai-message assistant">你好，我可以先帮你分析问题。请描述现象、报错信息和已经尝试过的操作。</div>`+aiMessages.map(message=>`<div class="ai-message ${message.role}">${esc(message.content)}</div>`).join('');box.scrollTop=box.scrollHeight;
  const refs=$('#ai-recommendations');if(refs){const basis=meta?`<div class="ai-answer-meta"><span class="tag ${meta.basis==='knowledge_base'?'published':'pending'}">${meta.basis==='knowledge_base'?'依据知识库':meta.basis==='general'?'通用排查建议':'未找到知识依据'}</span>${meta.need_ticket?'<button class="small" data-action="ai-fill-ticket">将问题带入工单</button>':''}</div>`:'';const links=recommendations.length?`<div class="ai-references"><strong>相关操作手册</strong>${recommendations.map(item=>`<a href="${esc(item.reader_url)}" target="_blank" rel="noopener">${esc(item.title)} →</a>`).join('')}</div>`:'';refs.innerHTML=basis+links;}
}

async function aiSettingsPage(){
  const config=await api('/api/ai/settings');
  const mode=`<select name="answer_mode" data-native-select required><option value="strict" ${config.answer_mode==='strict'?'selected':''}>严格知识库</option><option value="hybrid" ${config.answer_mode==='hybrid'?'selected':''}>混合模式（推荐）</option><option value="general" ${config.answer_mode==='general'?'selected':''}>通用 IT 助手</option></select>`;
  const noMatch=`<select name="no_match_action" data-native-select required><option value="general_advice" ${config.no_match_action==='general_advice'?'selected':''}>提供安全的通用排查建议</option><option value="submit_ticket" ${config.no_match_action==='submit_ticket'?'selected':''}>直接引导提交工单</option></select>`;
  setPage(head('AI 助手设置','配置提交工单页面使用的 OpenAI 兼容接口。')+`<section class="panel ai-settings"><form id="ai-settings-form" data-version="${config.version}"><div class="callout">密钥加密保存于服务器本地文件，页面不会回显明文。可填写供应商基础地址，系统会自动补齐 <code>/chat/completions</code>。</div><label class="checkbox-row"><input type="checkbox" name="enabled" ${config.enabled?'checked':''}>启用提交工单页面的 AI 助手</label><div class="form-grid" style="margin-top:20px">${field('API 基础地址或完整地址','<input name="endpoint_url" type="url" required maxlength="2048" value="'+esc(config.endpoint_url)+'" placeholder="https://api.deepseek.com">',true,'DeepSeek 可填写 https://api.deepseek.com；公司内网也可使用 HTTP 接口。')}${field('模型名称',input('model_name',config.model_name,true),true)}${field('API 密钥','<input name="api_key" type="password" maxlength="4096" autocomplete="new-password" placeholder="'+(config.api_key_configured?'已配置；留空则保持不变':'请输入 API 密钥')+'">',false,config.api_key_configured?'当前已配置密钥，保存时留空不会覆盖。':'密钥不会返回到浏览器。')}${field('请求超时（秒）','<input name="timeout_seconds" type="number" min="3" max="120" required value="'+config.timeout_seconds+'">',true)}${field('推荐知识条数','<input name="max_results" type="number" min="1" max="10" required value="'+config.max_results+'">',true)}<div class="field"><label>密钥状态</label><div class="credential-state ${config.api_key_configured?'ready':''}">${config.api_key_configured?'✓ 已安全配置':'未配置'}</div></div>${field('回答模式',mode,true,'严格模式无知识依据时不会调用 AI；混合模式可给安全的通用建议。')}${field('知识库无匹配时',noMatch,true,'选择直接提单时，系统不会把无依据问题发送给 AI。')}<div class="field full">${field('系统提示词','<textarea name="system_prompt" maxlength="4000" rows="8" required>'+esc(config.system_prompt)+'</textarea>',true,'用于补充回答口吻和业务边界；后端回答策略仍会强制执行。')}</div></div><label class="checkbox-row"><input type="checkbox" name="clear_api_key">清除当前 API 密钥</label><div id="ai-settings-error"></div><div id="ai-balance-result" aria-live="polite"></div><div class="form-footer"><button type="button" data-action="ai-balance">查询余额</button><button type="button" data-action="ai-test">测试已保存配置</button><button class="primary" type="submit">保存设置</button></div></form></section>`,'AI 助手设置');
}

function renderAiBalance(result){
  const box=$('#ai-balance-result');if(!box)return;
  const status=result.is_available?'<span class="tag closed">余额可用</span>':'<span class="tag cancelled">余额不足</span>';
  const labels={CNY:'人民币',USD:'美元'};
  const rows=(result.balance_infos||[]).map(item=>`<div class="ai-balance-card"><div><span>${esc(labels[item.currency]||item.currency)}</span><strong>${esc(item.currency==='CNY'?'¥':'$')}${esc(item.total_balance)}</strong></div><small>充值余额 ${esc(item.topped_up_balance)} · 赠送余额 ${esc(item.granted_balance)}</small></div>`).join('');
  box.innerHTML=`<section class="ai-balance"><div class="ai-balance-head"><div><strong>DeepSeek 账号余额</strong><span class="help">实时查询，不保存余额数值</span></div>${status}</div><div class="ai-balance-grid">${rows||'<p class="muted">账号没有返回币种余额明细。</p>'}</div><div class="help">查询时间：${time(result.checked_at)}</div></section>`;
}
async function ticketList(){
  const params=new URLSearchParams({page:state.page,page_size:state.pageSize,q:state.q,status:state.status});const data=await api('/api/tickets?'+params);state.items=data.items;
  const extra=select('status',['pending','in_progress','closed','cancelled'].map(v=>({value:v,name:names[v]})),state.status);
  setPage(head(can('ticket.claim')?'工单工作台':'我的工单','接单、协作、处理与留言，保留完整过程。',`<a class="button primary" href="#new-ticket">＋ 提交工单</a>`)+`<section class="panel">${filter(extra)}${table(['工单号 / 问题','提交人','提交部门','状态','处理人','提交时间','操作'],data.items.map(t=>[
    `<a href="#ticket/${t.id}">${esc(t.ticket_number)}</a><div style="margin-top:7px">${esc(t.title)}</div>`,esc(t.requester_name_snapshot),esc(t.department_name_snapshot||'—'),tag(t.status),esc(handlerName(t.assignee_user_id)),time(t.submitted_at),`<a href="#ticket/${t.id}">查看 →</a>`]))}${pager(data)}</section>`,'工单工作台');
}
function handlerName(id){return (state.lookup.handlers||[]).find(v=>v.id===id)?.name||(id===state.user?.id?state.user.display_name:id?'IT 已分配':'待分配');}
async function ticketDetail(key){
  const t=await api('/api/tickets/'+key);currentTicket=t;const attachments=await api('/api/tickets/'+key+'/attachments');
  let buttons='';const btn=(action,label,cls='')=>`<button class="${cls}" data-action="ticket-${action}">${label}</button>`;
  if(t.status==='pending'&&t.actions.includes('claim'))buttons+=btn('claim','接单并开始','primary');
  if(t.status==='pending'&&t.actions.includes('assign'))buttons+=btn('assign','分配');
  if(t.status==='pending'&&can('ticket.edit'))buttons+=btn('edit','更正描述');
  if(t.status==='in_progress'&&t.actions.includes('transfer'))buttons+=btn('transfer','转派同事');
  if(t.status==='in_progress'&&t.actions.includes('close'))buttons+=btn('close','完成并关闭','primary');
  if(t.status==='closed'&&t.actions.includes('reopen'))buttons+=btn('reopen','重新打开');
  if(t.status==='closed'&&t.actions.includes('correct'))buttons+=btn('correct','纠正分类 / 时间');
  if(['pending','in_progress'].includes(t.status)&&t.actions.includes('cancel'))buttons+=btn('cancel','取消工单');
  if(t.actions.includes('delete'))buttons+=btn('delete','永久删除','danger');
  const category=state.lookup.ticket_categories?.find(v=>v.id===t.category_id)?.name||'结单时确认';const latest=t.cycles.at(-1);
  setPage(head(t.ticket_number,t.title,`<a class="button" href="#tickets">返回列表</a>`)+`<div class="ticket-grid"><div><section class="panel"><div class="panel-title"><h2>问题描述</h2>${tag(t.status)}</div><div class="pretext">${esc(t.description)}</div>${latest?.handling_summary?`<h3 class="section-label">处理说明</h3><div class="pretext">${esc(latest.handling_summary)}</div>`:''}<div class="actions" style="margin-top:24px">${buttons}</div></section><section class="panel"><h2>处理记录与留言</h2>${t.events.map(e=>`<article class="event"><div class="event-head"><strong>${esc(e.actor_name_snapshot||'系统')}</strong><span>${esc(events[e.event_type]||e.event_type)}</span>${e.audience==='internal'?'<span class="tag">内部</span>':''}<span>${time(e.occurred_at)}</span></div>${e.body?`<div class="event-body">${esc(e.body)}</div>`:''}${attachments.filter(a=>a.event_id===e.id).map(a=>`<a class="button small" href="/api/files/ticket/${a.id}" target="_blank" rel="noopener">查看附件：${esc(a.original_name)}</a>`).join('')}</article>`).join('')}
    ${t.actions.includes('comment')?`<form id="comment-form"><div class="field"><label>补充信息或回复 IT</label><textarea name="body" required rows="3" maxlength="20000" placeholder="输入留言…"></textarea></div><div class="actions">${t.actions.includes('internal_note')?'<label><input type="checkbox" name="internal">仅 IT 可见的内部备注</label>':''}<button class="primary" type="submit">发送留言</button><button type="button" data-action="ticket-attachment">添加附件</button></div></form>`:''}</section>
    ${t.segments.length?`<section class="panel"><h2>处理时间分段</h2>${table(['处理人','开始','结束','历时'],t.segments.map(s=>[esc(s.handler_name_snapshot||'历史人员'),time(s.started_at),time(s.ended_at),duration(s.duration_ms)]))}<p class="help" style="margin-top:15px">处理历时包含等待与沟通，不代表实际人工投入。</p></section>`:''}</div><aside><section class="panel"><h2>工单信息</h2><dl class="detail-list"><dt>提交人</dt><dd>${esc(t.requester_name_snapshot)}</dd><dt>部门</dt><dd>${esc(t.department_name_snapshot||'—')}</dd><dt>联系方式</dt><dd>${esc(t.contact_snapshot||'—')}</dd><dt>发生位置</dt><dd>${esc(t.location_text||'—')}</dd><dt>处理人</dt><dd>${esc(handlerName(t.assignee_user_id))}</dd><dt>问题分类</dt><dd>${esc(category)}</dd><dt>本轮接单</dt><dd>${time(latest?.started_at)}</dd><dt>实际结束</dt><dd>${minuteTime(latest?.completed_at)}</dd><dt>处理历时</dt><dd>${duration(latest?.duration_ms)}</dd><dt>处理轮次</dt><dd>第 ${t.current_cycle_no} 轮</dd></dl></section><div class="callout">关闭后仍可留言。再次需要处理时可直接重开，新的处理轮次会单独计时。</div></aside></div>`,'工单详情');
}
function localDate(value=new Date()) {const d=new Date(value);return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,23);}
function localMinute(value=new Date()) {return localDate(value).slice(0,16);}
async function ticketAction(kind){
  let t=currentTicket;
  if(['close','correct'].includes(kind)){t=await api('/api/tickets/'+t.id);currentTicket=t;}
  if(['claim','reopen'].includes(kind)){
    await api('/api/tickets/'+t.id+'/actions',{method:'POST',body:{action:kind,version:t.version}});
    await route();toast(kind==='claim'?'已接单，开始计时':'已重开，等待新一轮接单');return;
  }
  if(kind==='attachment'){
    formModal('添加工单附件',field('附件','<input type="file" name="file" required accept=".png,.jpg,.jpeg,.pdf">',true)+field('说明',input('message','附件'))+(t.actions.includes('internal_note')?'<label><input type="checkbox" name="internal">仅 IT 可见</label>':''),async form=>{
      const fd=new FormData(form);fd.set('internal',form.elements.internal?.checked?'true':'false');await api(`/api/tickets/${t.id}/attachments`,{method:'POST',body:fd});$('#modal').close();await route();toast('附件已添加');
    });return;
  }
  if(kind==='edit'){
    formModal('更正问题描述',field('标题',input('title',t.title,true),true)+field('问题描述',`<textarea name="description" required>${esc(t.description)}</textarea>`,true),async form=>{
      await api('/api/tickets/'+t.id,{method:'PUT',body:{...Object.fromEntries(new FormData(form)),version:t.version}});$('#modal').close();await route();
    });return;
  }
  let content='';
  if(kind==='claim')content='<p>接单后立即开始计时，由你负责处理此工单。</p>';
  if(['assign','transfer'].includes(kind))content=field('接收同事',select('assignee_user_id',state.lookup.handlers||[],'',true),true)+field('转派留言',input('reason'));
  if(['close','correct'].includes(kind))content=field('实际问题分类',select('category_id',state.lookup.ticket_categories||[],t.category_id,true),true)
    +field('实际结束时间',`<input type="datetime-local" name="completed_at" required step="60" min="${localMinute(new Date(new Date(t.submitted_at).getTime()+60000))}" value="${localMinute(kind==='correct'?t.completed_at:new Date())}">`,true,'精确到分钟，须晚于工单提交时间：'+minuteTime(t.submitted_at)+'。可早于接单/转派时间；早于接单时，接单后处理历时记为 0。')
    +field(kind==='correct'?'纠正原因':'处理说明',`<textarea name="${kind==='correct'?'reason':'handling_summary'}" ${kind==='correct'?'required':''}></textarea>`,kind==='correct');
  if(kind==='cancel')content=field('取消原因','<textarea name="reason" required></textarea>',true);
  if(kind==='reopen')content='<p>工单将回到待接单，新一轮接单后重新开始计时。之前的处理记录会保留。</p>'+field('补充说明',input('reason'));
  if(kind==='delete')content=`<div class="callout warning">将永久删除工单、处理分段、留言及附件关系，相关统计会改变。</div>${field('输入工单号确认',input('confirm','',true),true,t.ticket_number)}${field('删除原因',input('reason','',true),true)}`;
  formModal({claim:'接单并开始处理',assign:'分配处理人',transfer:'转派同事',close:'完成并关闭工单',correct:'纠正分类与结束时间',cancel:'取消工单',reopen:'重新打开工单',delete:'永久删除工单'}[kind],content,async form=>{
    const values=Object.fromEntries(new FormData(form));
    if(values.completed_at){
      const end=new Date(values.completed_at);
      if(end<=new Date(t.submitted_at))throw Error('实际结束时间须晚于工单提交时间。');
      values.completed_at=end.toISOString();
    }
    if(kind==='delete'){await api('/api/tickets/'+t.id,{method:'DELETE',body:{...values,version:t.version}});$('#modal').close();location.hash='tickets';toast('工单已删除');return;}
    await api('/api/tickets/'+t.id+'/actions',{method:'POST',body:{...values,action:kind,version:t.version}});$('#modal').close();await route();toast('操作已完成');
  },false,{close:'完成并关闭',transfer:'确认转派',assign:'确认分配',cancel:'取消工单',correct:'保存纠正',delete:'永久删除'}[kind]||'确认');

}
async function knowledge(manage=false){
  const data=await api('/api/knowledge?'+new URLSearchParams({page:state.page,page_size:state.pageSize,q:state.q,manage}));state.items=data.items;
  setPage(head(manage?'知识管理':'知识库',manage?'上传内容，发布可阅读的版本。公开阅读不区分员工角色。':'按原文件排版，在独立窗口查阅操作手册。',manage&&can('knowledge.edit')?'<button class="primary" data-action="knowledge-upload">＋ 上传手册</button>':'')+
    `<section class="panel">${filter()}${data.items.length?`<div class="grid">${data.items.map(a=>`<article class="service-card knowledge-card"><span class="tag">${manage?esc(names[a.publication_state]):'操作手册'}</span><h3 style="margin-top:18px">${esc(a.title)}</h3><p>${esc(a.summary||'查看完整操作内容')}</p><div class="knowledge-meta">${day(a.updated_at)}${manage?` · 查看 ${a.view_count||0} 次`:''}</div><div class="knowledge-actions">${a.publication_state==='published'?`<a class="button small" href="${esc(a.reader_url)}" target="_blank" rel="noopener">新窗口阅读 →</a>`:''}${manage&&can('knowledge.publish')?`<button class="small" data-action="knowledge-publish" data-id="${a.id}">版本 / 发布</button>`:''}${manage&&can('knowledge.edit')?`<button class="small" data-action="knowledge-version" data-id="${a.id}">新版本</button>`:''}${manage&&can('knowledge.delete')?`<button class="small danger" data-action="knowledge-delete" data-id="${a.id}">删除</button>`:''}</div></article>`).join('')}</div>`:empty('暂无'+(manage?'手册':'已发布手册'),manage?'可以上传文件创建手册，并继续上传新版本。':'IT 发布手册后即可公开查阅。')}${pager(data)}</section>`,manage?'知识管理':'知识库');
}

function knowledgeDelete(key){
  const article=state.items.find(v=>v.id===key);if(!article)return;
  if(article.publication_state==='published'){modal('请先撤下知识',`<div class="callout warning">“${esc(article.title)}”当前正在公开展示。请先通过“版本 / 发布”撤下，再执行永久删除。</div>`);return;}
  formModal('永久删除知识',`<div class="callout warning">将删除“${esc(article.title)}”的全部版本、原文件和预览文件，操作无法恢复。</div>${field('删除原因',input('reason','',true),true)}`,async form=>{
    await api('/api/knowledge/'+key,{method:'DELETE',body:{version:article.version,confirm:key,reason:form.elements.reason.value}});$('#modal').close();await route();toast('知识及全部文件版本已删除');
  });
}
async function knowledgeUpload(articleId=null){
  const categories=await api('/api/options/knowledge_categories');
  formModal(articleId?'上传新的知识版本':'上传操作手册',field('标题',input('title',state.items.find(a=>a.id===articleId)?.title||'',true),true)+field('知识分类',select('category_id',categories,'',true),true)+field('原文件','<input name="file" type="file" required accept=".html,.htm,.pdf,.ppt,.pptx">',true,'上传后为草稿，发布前可检查转换情况。'),async form=>{
    const fd=new FormData(form);if(articleId)fd.append('article_id',articleId);await api('/api/knowledge/upload',{method:'POST',body:fd});$('#modal').close();await route();toast('已保存草稿');
  });
}
async function knowledgePublish(key){
  const result=await api('/api/knowledge/'+key+'/versions');const status=await api('/api/knowledge/'+key+'/preview-status');
  formModal('知识版本与发布',`<p>${esc(result.article.title)}</p><div class="callout">最新版本预览：${esc(status.status==='ready'?'已就绪':status.message||status.status)}。PPT 首次转换完成后再发布。</div>${field('选择版本',select('version_no',result.versions.map(v=>({value:v.version_no,name:`第 ${v.version_no} 版 · ${v.file_format.toUpperCase()}`})),result.versions[0].version_no,true),true)}${field('操作',select('state',[{value:'published',name:'发布所选版本'},{value:'withdrawn',name:'撤下文章'}],'published',true),true)}`,async form=>{
    const values=Object.fromEntries(new FormData(form));await api('/api/knowledge/'+key+'/publish',{method:'POST',body:{...values,version_no:Number(values.version_no),version:result.article.version}});$('#modal').close();await route();toast('知识发布状态已更新');
  });
}
async function announcements(){const d=await api('/api/announcements?'+new URLSearchParams({page:state.page,page_size:state.pageSize}));setPage(head('IT 公告','服务信息与维护提醒。')+`<section class="panel">${d.items.length?d.items.map(a=>`<div class="notice">${a.is_pinned?'<span class="tag">置顶</span>':''}<a href="#announcements" data-action="announcement" data-id="${a.id}">${esc(a.title)}</a><span class="date">${esc(a.publisher_name||'IT')} · ${time(a.published_at)}</span></div>`).join(''):empty('暂无公告')}${pager(d)}</section>`,'IT 公告');}
async function services(){const d=await api('/api/public');setPage(head('IT 服务目录','了解服务范围，按需要提交问题。')+(d.services.length?`<div class="grid">${d.services.map(s=>`<article class="panel"><h2>${esc(s.name)}</h2><p>${esc(s.summary)}</p><div class="pretext">${esc(s.scope_text||'')}</div>${s.submission_guide?`<h3>申请方式</h3><div class="pretext">${esc(s.submission_guide)}</div>`:''}<p class="help">${esc(s.service_hours||'')}${s.contact_text?' · '+esc(s.contact_text):''}</p><a class="button primary" href="#new-ticket">提交服务工单 →</a></article>`).join('')}</div>`:empty('暂无已发布服务','仍可通过“提交工单”联系 IT。')),'服务目录');}

async function quickLinks(){
  const result=await api('/api/quick-links');state.items=result.items;
  const query=state.q.trim().toLocaleLowerCase(),visible=result.items.filter(v=>!query||(v.title+' '+(v.description||'')).toLocaleLowerCase().includes(query));
  const cards=category=>visible.filter(v=>v.link_category===category).map(v=>`<article class="quick-link-card ${v.is_enabled?'':'disabled'}"><a class="quick-link-open" href="${esc(v.url)}" target="_blank" rel="noopener"><span class="quick-link-icon">${esc(v.icon_text||v.title.slice(0,1))}</span><span class="quick-link-copy"><strong>${esc(v.title)}</strong><small>${esc(v.description||new URL(v.url).hostname)}</small></span><span class="quick-link-arrow">↗</span></a>${result.can_manage?`<div class="quick-link-admin">${v.is_enabled?'':tag('disabled')}<button class="small" data-action="quick-link-edit" data-id="${v.id}">编辑</button><button class="small danger" data-action="quick-link-delete" data-id="${v.id}">删除</button></div>`:''}</article>`).join('');
  const actions=result.can_manage?'<button class="primary" data-action="quick-link-create">＋ 添加链接</button>':'';
  setPage(`<section class="quick-link-hero"><div><span class="eyebrow">INTERNAL WORKSPACE</span><h1>快捷链接</h1><p>集中访问公司内部系统，点击卡片将在新窗口打开。</p></div><form id="filter-form" class="quick-link-search"><span>⌕</span><input name="q" value="${esc(state.q)}" placeholder="搜索系统名称或说明…"><button type="submit">搜索</button></form></section>${head('常用系统',result.it_access?'通用系统与 IT 管理入口。':'你可以访问公司通用系统。',actions)}<section class="quick-link-section"><h2>通用</h2><div class="quick-link-grid">${cards('general')||empty('暂无通用链接','管理员添加后会显示在这里。')}</div></section>${result.it_access?`<section class="quick-link-section"><h2>IT 管理</h2><div class="quick-link-grid">${cards('it')||empty('暂无 IT 管理链接','管理员可以添加运维管理系统。')}</div></section>`:''}`,'快捷链接');
}

function quickLinkForm(key=null){
  const item=state.items.find(v=>v.id===key)||{};
  formModal(key?'编辑快捷链接':'添加快捷链接',`<div class="form-grid">${field('链接名称',input('title',item.title||'',true),true)}${field('分类',select('link_category',[{value:'general',name:'通用'},{value:'it',name:'IT 管理'}],item.link_category||'general',true),true)}${field('链接地址',input('url',item.url||'',true),true,'可填写完整 HTTP/HTTPS 地址；未填写协议时自动使用 HTTP。')}${field('图标文字或 Emoji',input('icon_text',item.icon_text||''),false,'例如：OA、ERP、☁；留空取名称首字。')}${field('说明',input('description',item.description||''))}${field('排序',`<input name="sort_order" type="number" min="-9999" max="9999" value="${esc(item.sort_order??0)}">`)}${field('状态',select('is_enabled',[{value:'1',name:'启用'},{value:'0',name:'停用'}],item.is_enabled===false?'0':'1',true),true)}</div>`,async form=>{
    const body={title:form.elements.title.value,url:form.elements.url.value,link_category:form.elements.link_category.value,icon_text:form.elements.icon_text.value,description:form.elements.description.value,sort_order:Number(form.elements.sort_order.value||0),is_enabled:form.elements.is_enabled.value==='1'};if(key)body.version=item.version;
    await api('/api/quick-links'+(key?'/'+key:''),{method:key?'PUT':'POST',body});$('#modal').close();await route();toast('快捷链接已保存');
  });
}
async function reports(){
  const params=new URLSearchParams({start:state.reportStart||'',end:state.reportEnd||''});const d=await api('/api/reports/tickets?'+params);
  state.reportStart=d.start||'';state.reportEnd=d.end||'';
  const metrics=[['结单轮次',d.closed_cycles,'重开后再次结单，计新一轮'],['去重工单数',d.unique_tickets,'同一工单不重复计算'],['总处理历时',duration(d.duration_ms),'包含等待与沟通时间'],['平均处理历时',duration(d.average_ms),'仅含有效关闭轮次']];
  const max=Math.max(1,...d.categories.map(v=>v.count));
  setPage(head('运维记录分类汇总','按实际结束时间统计，展示处理规模与协作过程。')+`<form id="report-filter" class="filters"><label>开始日期</label><input name="start" type="date" value="${esc(state.reportStart||'')}" style="width:180px"><label>结束日期</label><input name="end" type="date" value="${esc(state.reportEnd||'')}" style="width:180px"><button type="submit">查询汇总</button></form><div class="stat-grid">${metrics.map(([label,value,help])=>`<div class="stat"><span class="label">${label}</span><strong>${esc(value)}</strong><small>${help}</small></div>`).join('')}</div><div class="grid two"><section class="panel"><h2>问题分类分布</h2>${d.categories.length?d.categories.map(c=>`<div class="bar-row"><span>${esc(c.name)}</span><div class="bar-track"><div class="bar-fill" style="width:${c.count/max*100}%"></div></div><span>${c.count} 次</span></div>`).join(''):empty('暂无结单记录')}</section><section class="panel"><h2>当前工单状态</h2>${['pending','in_progress','closed','cancelled'].map(v=>`<div class="notice">${tag(v)}<strong style="margin-left:auto">${d.states[v]||0}</strong></div>`).join('')}</section></div><section class="panel"><h2>分类处理历时</h2>${table(['问题分类','结单次数','总处理历时','平均处理历时'],d.categories.map(c=>[esc(c.name),c.count,duration(c.duration_ms),duration(c.duration_ms/c.count)]))}</section><section class="panel"><h2>处理人工作记录</h2>${table(['处理人','最终结单次数','参与轮次','本人区间历时'],d.handlers.map(h=>[esc(h.name),h.closed_count,h.participated_cycles,duration(h.duration_ms)]))}<p class="help" style="margin-top:18px">转派前后的区间分别归属各处理人；最终结单只归最后责任处理人一次。此指标不是实际劳动投入工时。</p></section>`,'运维分类汇总');
}

async function dataPage(name){
  const spec=state.catalog.find(v=>v.table===name);if(!spec)throw Error('没有此模块的访问权限');
  const params=new URLSearchParams({page:state.page,page_size:state.pageSize,q:state.q,archived:state.archived,kind:state.kind,status:state.status});
  const data=await api('/api/data/'+name+'?'+params);state.items=data.items;state.dataSpec=spec;
  const actions=spec.actions;let buttons='';
  if(actions.includes('create')||actions.includes('edit'))buttons+='<button class="primary" data-action="data-create">＋ 新增记录</button>';
  if(actions.includes('import'))buttons+=`<button data-action="import-open">导入数据</button><button data-action="template-download">下载标准模板</button>`;
  if(actions.includes('export'))buttons+='<button data-action="data-export">导出数据</button>';
  const basicTables=['ticket_categories','sites','service_catalog'];
  const group=basicTables.includes(name)?basicTables.map(tableName=>state.catalog.find(v=>v.table===tableName)).filter(Boolean):spec.table==='departments'?[spec]:spec.module==='resource'?state.catalog.filter(v=>v.module==='resource'):state.catalog.filter(v=>v.module===spec.module&&v.table!=='departments');
  const tabs=group.map(v=>`<a class="${v.table===name?'active':''}" href="#data/${v.table}">${esc(v.title)}</a>`).join('');
  const available=spec.fields.filter(f=>!f.ui_hidden&&!['description','body','scope_text','submission_guide','implementation_text','outcome_text','problem_summary'].includes(f.name));
  const visible=name==='announcements'?['title','publication_state','published_at','published_by_user_id','is_pinned','expires_at'].map(fieldName=>available.find(f=>f.name===fieldName)).filter(Boolean):available.slice(0,7);
  const options=name==='resources'?select('kind',Object.entries(subtype).map(([k])=>({value:k,name:names[k]})),state.kind):name==='announcements'?`<select name="status" data-native-select><option value="">全部状态</option><option value="published" ${state.status==='published'?'selected':''}>已发布</option><option value="draft" ${state.status==='draft'?'selected':''}>草稿</option></select>`:'';
  setPage(head(spec.title,({dictionary_items:'统一保存设备类型等标准名称。目前尚未绑定业务表单，下方维护不会自动改变设备类型选项。',service_catalog:'向员工介绍 IT 可提供哪些服务、适用范围、服务时间和申请方式；打开公开发布后展示在员工服务目录。'})[name]||'在线维护为正式数据源。批量操作使用本模块标准模板。',buttons)+`<div class="tabs">${tabs}</div><section class="panel">${filter(options+(spec.has_version?`<label class="checkbox-row"><input name="archived" type="checkbox" ${state.archived?'checked':''}>已归档</label>`:''))}${table([...visible.map(f=>f.label),'操作'],data.items.map(item=>[
    ...visible.map(f=>f.name==='publication_state'&&name==='announcements'?tag(item.publication_state)+(item.publication_state==='published'&&item.expires_at&&new Date(item.expires_at)<=new Date()?'<div class="help">已过期 · 公开页面不展示</div>':''):name==='announcements'&&f.name==='expires_at'?minuteTime(item[f.name]):displayField(f,item[f.name])),`<div class="table-actions"><button data-action="data-edit" data-id="${item[spec.pk]}">详情 / 编辑</button>${name==='announcements'?`<button data-action="announcement-attachments" data-id="${item[spec.pk]}">附件</button>`:''}${name==='announcements'&&actions.includes('publish')?`<button data-action="data-publish" data-id="${item[spec.pk]}">${item.publication_state==='published'?'撤下':'发布'}</button>`:''}${actions.includes('archive')&&spec.has_version?`<button data-action="data-archive" data-id="${item[spec.pk]}">${item.is_archived?'恢复':'归档'}</button>`:''}${actions.includes('delete')?`<button class="danger" data-action="data-delete" data-id="${item[spec.pk]}">删除</button>`:''}</div>`]))}${pager(data)}</section>`,spec.title);
}

async function announcementAttachments(key){
  const item=state.items.find(v=>v.id===key),items=await api(`/api/announcements/${key}/attachments`);
  const listing=items.length?`<div class="attachment-list">${items.map(v=>`<div class="notice"><span>${esc(v.original_name)} <small class="help">${Math.ceil(v.size_bytes/1024)} KB</small></span>${item.publication_state!=='published'?`<button type="button" class="small danger" data-action="announcement-attachment-delete" data-id="${v.id}" data-announcement="${key}">移除</button>`:''}</div>`).join('')}</div>`:'<div class="empty">暂无附件</div>';
  if(item.publication_state==='published'){modal('公告附件',`${listing}<div class="callout">已发布公告的附件处于公开状态。如需修改，请先撤下公告。</div>`);return;}
  formModal('公告附件',`${listing}${field('上传附件','<input name="files" type="file" multiple required accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.png,.jpg,.jpeg,.txt,.zip">',true,'最多 10 个附件，单个不超过 20 MB。')}`,async form=>{
    const files=form.elements.files.files;if(!files.length||[...files].some(v=>v.size>20*1024*1024))throw Error('请选择 20 MB 以内的附件');
    await api(`/api/announcements/${key}/attachments`,{method:'POST',body:new FormData(form)});$('#modal').close();toast('附件已上传');
  },false,'上传');
}
function displayField(f,value){
  if(f.name==='site_id')return esc(state.lookup.sites?.find(v=>v.id===value)?.name||value||'—');
  if(f.name==='department_id')return esc(state.lookup.departments?.find(v=>v.id===value)?.name||'—');
  if(f.name==='parent_id'){
    const target=f.ref?.split('.')[0],list=state.lookup[target]||state.items||[];
    return esc(list.find(v=>v.id===value)?.name||'—');
  }
  if(f.name==='owner_user_id'||f.name==='published_by_user_id')return esc(handlerName(value));
  if(f.type==='bool')return value?'是':'否';
  if(f.type==='utc')return time(value);
  if(names[value])return tag(value);
  return esc(value??'—');
}
async function generatedFields(spec,values={},prefix='',exclude=[]){
  const defaults={is_enabled:true,is_pinned:false,sort_order:0,lifecycle_status:'unknown',verification_status:'draft',publication_state:'draft',is_published:false,site_type:'other',role_code:'unknown',registered_state:'unknown'};
  const result=[];
  for(const f of spec.fields){
    if(f.ui_hidden||f.ui_form_hidden||exclude.includes(f.name))continue;
    let value=values[f.name]??defaults[f.name]??'';let control;const name=prefix+f.name;const required=!f.nullable;
    if(f.ref){
      const target=f.ref.split('.')[0];let list;
      if(target==='sites'||target==='departments'||target==='ticket_categories')list=state.lookup[target]||[];
      else list=await api('/api/options/'+target);
      control=select(name,list,value,required);
    }else if(f.type==='bool')control=select(name,[{value:'1',name:'是'},{value:'0',name:'否'}],value?'1':'0',required);
    else if(f.enum.length)control=select(name,f.enum.map(v=>({value:v,name:names[v]||v})),value,required);
    else if(f.type==='text'||f.type==='json'||f.name==='summary')control=`<textarea name="${name}" ${required?'required':''}>${esc(value)}</textarea>`;
    else if(f.type==='utc')control=`<input name="${name}" type="datetime-local" step="${spec.table==='announcements'&&f.name==='expires_at'?'60':'0.001'}" ${required?'required':''} value="${value?(spec.table==='announcements'&&f.name==='expires_at'?localMinute(value):localDate(value)):''}">`;
    else if(f.type==='date')control=input(name,value,required,'date');
    else if(['int','bigint','decimal12_3','decimal18_2'].includes(f.type))control=`<input name="${name}" type="number" ${required?'required':''} step="${f.type.startsWith('decimal')?'0.001':'1'}" value="${esc(value)}">`;
    else control=input(name,value,required);
    control=control.replace(/<(input|textarea|select)\b/,`<$1 id="field-${esc(name)}"`);
    result.push(`<div class="field ${f.type==='text'||f.type==='json'?'full':''}"><label for="field-${esc(name)}">${esc(f.label)}${required?'<span class="required">*</span>':''}</label>${control}<small class="help">${esc(f.description)}</small></div>`);
  }
  return result.join('');
}
function formValues(form,spec,prefix='',exclude=[]){
  const result={};
  for(const f of spec.fields){
    if(f.ui_hidden||f.ui_form_hidden||exclude.includes(f.name))continue;
    const element=form.elements.namedItem(prefix+f.name);if(!element)continue;
    let value=element.value;
    if(value===''){if(f.nullable)result[f.name]=null;continue;}
    if(f.type==='bool')value=value==='1';
    else if(['int','bigint'].includes(f.type))value=Number(value);
    else if(f.type==='utc')value=new Date(value).toISOString();
    result[f.name]=value;
  }
  return result;
}
async function dataForm(key=null){
  const spec=state.dataSpec;const item=state.items.find(v=>v[spec.pk]===key)||{};
  if(spec.table==='resources'){
    if(!key){formModal('选择资源类型',field('资源类型',select('kind',Object.keys(subtype).map(v=>({value:v,name:names[v]})),'device',true),true),async form=>resourceForm(null,form.elements.kind.value));return;}
    await resourceForm(key,item.resource_kind);return;
  }
  let body=await generatedFields(spec,item);
  if(spec.table==='announcements'){
    const attachments=key?await api(`/api/announcements/${key}/attachments`):[];
    const existing=attachments.length?attachments.map(v=>`<div class="notice"><span>${esc(v.original_name)} <small class="help">${Math.ceil(v.size_bytes/1024)} KB</small></span>${item.publication_state!=='published'?`<button type="button" class="small danger" data-action="announcement-attachment-delete" data-id="${v.id}" data-announcement="${key}" data-return-edit="1">移除</button>`:''}</div>`).join(''):'<div class="empty">暂无附件</div>';
    body+=`<div class="field full"><label>已有附件</label>${existing}</div><div class="field full"><label for="field-announcement_files">${key?'继续添加附件':'公告附件'}</label><input id="field-announcement_files" name="announcement_files" type="file" multiple accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.png,.jpg,.jpeg,.txt,.zip" ${item.publication_state==='published'?'disabled':''}><small class="help">最多 10 个附件，单个不超过 20 MB。已发布公告请先撤下后修改附件。</small></div>`;
  }
  formModal(key?'编辑'+spec.title:'新增'+spec.title,`<div class="form-grid">${body}</div>`,async form=>{
    const values=formValues(form,spec);if(key)values.version=item.version;
    const saved=await api('/api/data/'+spec.table+(key?'/'+key:''),{method:key?'PUT':'POST',body:values});
    const files=form.elements.announcement_files?.files;
    if(spec.table==='announcements'&&files?.length){
      if(files.length>10||[...files].some(v=>v.size>20*1024*1024))throw Error('每个公告最多 10 个附件，单个不得超过 20 MB');
      const data=new FormData();[...files].forEach(file=>data.append('files',file));
      await api(`/api/announcements/${saved.id}/attachments`,{method:'POST',body:data});
    }
    $('#modal').close();await loadPrivate();await route();toast('已保存');
  });
}
async function resourceForm(key,kind){
  const spec=state.catalog.find(v=>v.table==='resources'),detailSpec=state.catalog.find(v=>v.table===subtype[kind]);
  const current=key?await api(`/api/resources/${key}/full`):{resource:{resource_kind:kind},details:{}};
  const common=await generatedFields(spec,current.resource,'r_',['resource_kind']);
  const details=await generatedFields(detailSpec,current.details,'d_',kind==='wifi'?['resource_id','site_id']:['resource_id']);
  formModal((key?'编辑':'新增')+names[kind],`<h3 class="section-label">基本信息</h3><div class="form-grid">${common}</div><h3 class="section-label">${names[kind]}参数</h3><div class="form-grid">${details}</div>`,async form=>{
    const resource=formValues(form,spec,'r_',['resource_kind']);if(key)resource.version=current.resource.version;
    const detail=formValues(form,detailSpec,'d_',['resource_id',...(kind==='wifi'?['site_id']:[])]);
    await api(key?`/api/resources/${key}/full`:`/api/resources/${kind}`,{method:key?'PUT':'POST',body:{resource,details:detail}});$('#modal').close();await route();toast('资源及参数已保存');
  });
}
async function dataOperation(kind,key){
  const spec=state.dataSpec,item=state.items.find(v=>v[spec.pk]===key);
  if(kind==='publish'){
    formModal(item.publication_state==='published'?'撤下内容':'发布内容',`<p>${esc(item.title)}</p><p class="muted">${item.publication_state==='published'?'撤下后首页和公开链接将无法读取。':item.expires_at&&new Date(item.expires_at)<=new Date()?'截止时间已过，请先取消本操作，在编辑中清空截止时间或改为未来时间。':'发布后所有人可在首页查看；截止时间留空则长期展示。'}</p>`,async()=>{
      await api(`/api/data/${spec.table}/${key}/publish`,{method:'POST',body:{state:item.publication_state==='published'?'withdrawn':'published',version:item.version}});$('#modal').close();await route();
    });
  }else if(kind==='archive'){
    await api(`/api/data/${spec.table}/${key}/archive`,{method:'POST',body:{archive:!item.is_archived,version:item.version}});await route();toast(item.is_archived?'已恢复':'已归档');
  }else if(kind==='delete'){
    formModal('永久删除记录',`<div class="callout warning">删除会影响当前统计。仍有引用的资料需要先归档或解除引用。</div>${field('删除原因',input('reason','',true),true)}`,async form=>{
      await api(`/api/data/${spec.table}/${key}`,{method:'DELETE',body:{reason:form.elements.reason.value,version:item.version,confirm:key}});$('#modal').close();await route();await loadPrivate();toast('已删除');
    });
  }
}
async function download(path,filename,options={}){const blob=await api(path,options);const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function importOpen(){
  const spec=state.dataSpec;
  formModal('按标准模板导入'+spec.title,`<div class="callout">第一步下载本模块模板，填写后上传。不会读取原有 Excel 或 OneDrive 数据源。</div><button type="button" data-action="template-download">下载 ${esc(spec.title)}标准模板</button><div style="height:20px"></div>${field('导入文件','<input type="file" name="file" required accept=".xlsx">',true)}${field('导入模式',select('mode',[{value:'create_only',name:'仅新增，已有编号报错'},{value:'upsert',name:'按业务编号新增或更新'}],'create_only',true),true)}`,async form=>{
    const b=await api('/api/imports/'+spec.table,{method:'POST',body:new FormData(form)});await importReview(b.id);
  },false,'校验并预览');
}
async function importReview(key){
  const result=await api('/api/imports/batches/'+key);const summary=JSON.parse(result.batch.summary_json);
  formModal('确认导入预览',`<div class="callout">总计 ${summary.rows} 行，错误 ${summary.errors} 行。确认前不会写入正式业务数据。</div>${table(['数据行','结果','错误信息'],result.rows.map(r=>[esc(r.source_row_key),r.resolution_state==='ready'?tag('verified'):'<span class="tag pending">需修正</span>',esc(JSON.parse(r.validation_json).error||'通过，待确认提交')]))}${summary.errors?'<label class="checkbox-row" style="margin-top:20px"><input name="valid_only" type="checkbox">明确选择：仅提交正确行，跳过错误行</label>':''}`,async form=>{
    await api('/api/imports/batches/'+key+'/commit',{method:'POST',body:{valid_only:!!form.elements.valid_only?.checked}});$('#modal').close();if(summary.ledger_kind){ledgerOptions=null;ledgerOptionsReady=false;}await route();toast('导入已提交');
  },false,'确认提交');
}
async function users(){
  const [data,roles]=await Promise.all([api('/api/users?'+new URLSearchParams({page:state.page,page_size:state.pageSize,q:state.q})),api('/api/roles')]);state.items=data.items;state.roles=roles.items;
  setPage(head('用户管理','管理员创建账号即可登录；用户和管理员都可以修改密码。',can('user.create')?'<button class="primary" data-action="user-create">＋ 新增用户</button>':'')+`<section class="panel">${filter()}${table(['账号','姓名','部门','角色','状态','操作'],data.items.map(u=>[esc(u.login_name),esc(u.display_name),esc(state.lookup.departments?.find(v=>v.id===u.department_id)?.name||'—'),esc(u.role_ids.map(k=>roles.items.find(r=>r.id===k)?.name||'').join('、')),tag(u.account_state),`<div class="table-actions">${can('user.edit')?`<button data-action="user-edit" data-id="${u.id}">编辑</button>`:''}${can('user.password')?`<button data-action="user-reset" data-id="${u.id}">设置密码</button>`:''}${can('user.delete')?`<button data-action="user-delete" data-id="${u.id}">删除</button>`:''}</div>`]))}${pager(data)}</section>`,'用户管理');
}
async function organizationPage(section='departments'){
  if(!['departments','people','positions'].includes(section))section='departments';
  const status=await api('/api/organization/sync-status');
  const tabs=`<div class="tabs"><a class="${section==='departments'?'active':''}" href="#organization/departments">部门</a><a class="${section==='people'?'active':''}" href="#organization/people">人员</a><a class="${section==='positions'?'active':''}" href="#organization/positions">岗位</a></div>`;
  const syncAllowed=can('user.import')&&can('directory.import');
  const syncActions=syncAllowed?`<button class="primary" data-action="org-sync-ehr">↻ 从 EHR 同步</button><button data-action="org-sync-ldap">同步域用户</button>`:'';
  const syncState=status.state;const syncPanel=`<section class="panel org-sync"><div class="panel-title"><div><h2>组织数据同步</h2><p class="help">EHR 仅读取 ${status.allowed_views.map(esc).join('、')}；每天 00:00 自动同步。</p></div><div class="actions">${syncActions}</div></div><div class="sync-summary"><span>${status.configured?tag(syncState?.last_status||'尚未同步'):tag('未配置')}</span><span>数据库：${esc(status.database)}</span><span>组织：${esc(status.org_code)}</span><span>最后成功：${time(syncState?.last_success_at)}</span></div>${syncState?.last_message?`<div class="callout ${syncState.last_status==='error'?'warning':''}">${esc(syncState.last_message)}</div>`:''}</section>`;
  let content='';
  if(section==='departments'){
    const spec=state.catalog.find(v=>v.table==='departments');if(!spec)throw Error('没有部门查看权限');
    const data=await api('/api/data/departments?'+new URLSearchParams({page:state.page,page_size:state.pageSize,q:state.q,archived:false}));state.items=data.items;state.dataSpec=spec;
    content=`${filter()}${table(['部门编号','部门名称','上级部门','来源','状态','操作'],data.items.map(v=>[esc(v.code),esc(v.name),displayField(spec.fields.find(f=>f.name==='parent_id'),v.parent_id),tag(organizationSource(v.source_type)),tag(v.is_enabled?'active':'disabled'),`<div class="table-actions">${can('directory.edit')?`<button data-action="data-edit" data-id="${v.id}">编辑</button>`:''}${can('directory.delete')?`<button class="danger" data-action="data-delete" data-id="${v.id}">删除</button>`:''}</div>`]))}${pager(data)}`;
  }else if(section==='people'){
    const params=new URLSearchParams({page:state.page,page_size:state.pageSize,q:state.q,department_id:state.departmentId,account_state:state.status,source_type:state.kind});
    const [data,roles]=await Promise.all([api('/api/users?'+params),api('/api/roles')]);state.items=data.items;state.roles=roles.items;
    const departmentFilter=`<select name="department_id"><option value="">全部部门</option>${(state.lookup.departments||[]).map(v=>`<option value="${esc(v.id)}" ${v.id===state.departmentId?'selected':''}>${esc(v.name)}</option>`).join('')}</select>`;
    const stateFilter=`<select name="status" data-native-select><option value="">全部状态</option><option value="active" ${state.status==='active'?'selected':''}>启用</option><option value="disabled" ${state.status==='disabled'?'selected':''}>停用</option></select>`;
    const sourceFilter=`<select name="kind" data-native-select><option value="">全部来源</option><option value="ehr" ${state.kind==='ehr'?'selected':''}>EHR同步</option><option value="ldap" ${state.kind==='ldap'?'selected':''}>LDAP同步</option><option value="manual" ${state.kind==='manual'?'selected':''}>手工维护</option></select>`;
    content=`${filter(departmentFilter+stateFilter+sourceFilter)}${table(['账号','姓名','所属部门','最上级部门','岗位','角色','来源','状态','操作'],data.items.map(u=>[esc(u.login_name),esc(u.display_name),esc(u.department_name||'—'),esc(u.top_department_name||'—'),esc((u.position_ids||[]).map(k=>state.lookup.positions?.find(v=>v.id===k)?.name).filter(Boolean).join('、')||'—'),esc((u.role_ids||[]).map(k=>roles.items.find(v=>v.id===k)?.name).filter(Boolean).join('、')||'—'),tag(organizationSource(u.source_type)),tag(u.account_state),`<div class="table-actions">${can('user.edit')?`<button data-action="user-edit" data-id="${u.id}">编辑</button>`:''}${can('user.password')?`<button data-action="user-reset" data-id="${u.id}">设置密码</button>`:''}${can('user.delete')?`<button class="danger" data-action="user-delete" data-id="${u.id}">删除</button>`:''}</div>`]))}${pager(data)}`;
  }else{
    const data=await api('/api/organization/positions?'+new URLSearchParams({page:state.page,page_size:state.pageSize,q:state.q}));state.items=data.items;
    content=`${filter()}${table(['岗位','来源','状态','操作'],data.items.map(v=>[esc(v.title),tag(organizationSource(v.source_type)),tag(v.is_enabled?'active':'disabled'),can('directory.edit')?`<button data-action="org-position-edit" data-id="${v.id}">编辑</button>`:'—']))}${pager(data)}`;
  }
  const add=section==='departments'&&can('directory.edit')?'<button class="primary" data-action="data-create">＋ 新增部门</button>':section==='people'&&can('user.create')?'<button class="primary" data-action="user-create">＋ 新增人员</button>':section==='positions'&&can('directory.edit')?'<button class="primary" data-action="org-position-create">＋ 新增岗位</button>':'';
  setPage(head('部门与人员','统一维护部门、人员和岗位；手工数据与外部同步数据可以并存。',add)+syncPanel+tabs+`<section class="panel">${content}</section>`,'部门与人员');
}
function positionForm(key=null){
  const item=state.items.find(v=>v.id===key)||{};
  formModal(key?'编辑岗位':'新增岗位',`<div class="form-grid">${field('岗位名称',input('title',item.title||'',true),true)}${field('状态',select('is_enabled',[{value:'1',name:'启用'},{value:'0',name:'停用'}],item.is_enabled===false?'0':'1',true),true)}</div>`,async form=>{
    const body={title:form.elements.title.value,is_enabled:form.elements.is_enabled.value==='1'};if(key)body.version=item.version;
    await api('/api/organization/positions'+(key?'/'+key:''),{method:key?'PUT':'POST',body});$('#modal').close();await loadPrivate();await route();toast('岗位已保存');
  });
}
async function userForm(key=null){
  if(!state.roles.length)state.roles=(await api('/api/roles')).items;
  const u=state.items.find(v=>v.id===key)||{};const roles=state.roles.filter(v=>!v.is_archived);
  formModal(key?'编辑用户':'新增用户',`<div class="form-grid">${!key?field('账号',input('login_name','',true),true):field('账号',`<input value="${esc(u.login_name)}" disabled>`)}${field('姓名',input('display_name',u.display_name||'',true),true)}${field('部门',select('department_id',state.lookup.departments,u.department_id,true),true)}${field('岗位',select('position_ids',state.lookup.positions||[],u.position_ids||[],false,true),false,'可选择多个岗位；支持输入部门或岗位名称搜索。')}${field('邮箱',input('email',u.email||'',false,'email'))}${field('电话',input('phone',u.phone||''))}${key?field('账号状态',select('account_state',[{value:'active',name:'启用'},{value:'disabled',name:'停用'}],u.account_state,true),true):field('初始密码',input('password','',false,'password'),false,'留空由系统生成；手动设置至少 8 位。')}</div>${can('user.roles')?`<h3 class="section-label">分配角色</h3>${roles.map(r=>`<label class="checkbox-row"><input name="role_ids" type="checkbox" value="${r.id}" ${u.role_ids?.includes(r.id)||!key&&r.code==='employee'?'checked':''}>${esc(r.name)}</label>`).join('')}`:''}`,async form=>{
    const fd=new FormData(form);const values=Object.fromEntries(fd);values.position_ids=fd.getAll('position_ids');if(can('user.roles'))values.role_ids=fd.getAll('role_ids');if(key)values.version=u.version;
    const result=await api('/api/users'+(key?'/'+key:''),{method:key?'PUT':'POST',body:values});$('#modal').close();await route();
    if(result.initial_password)passwordHandover(result);else toast('用户已更新，原会话已失效');
  });
}
function passwordHandover(result){modal('账号交付',`<div class="callout success">账号可直接登录，无需激活。请通过公司现有渠道交付，此处关闭后无法再次查看密码。</div><p>账号：<strong>${esc(result.login_name)}</strong></p><div class="password-result">${esc(result.initial_password)}</div><div class="form-footer"><button class="primary" data-action="close-modal">已记录，关闭</button></div>`);}
function resetPassword(key){const u=state.items.find(v=>v.id===key);formModal('管理员设置新密码',`<p>${esc(u.display_name)} · ${esc(u.login_name)}</p>${field('新密码',input('password','',false,'password'),false,'至少 8 位；留空由系统随机生成。旧密码和旧会话立即失效。')}`,async form=>{
  const result=await api('/api/users/'+key+'/password',{method:'POST',body:{password:form.elements.password.value,version:u.version}});$('#modal').close();await route();passwordHandover(result);
});}
const moduleNames={ticket:'工单',resource:'基础台账',user:'用户',role:'角色权限',category:'问题分类',knowledge:'知识库',announcement:'公告',directory:'基础资料',report:'分类汇总',audit:'审计',settings:'系统设置',quicklink:'快捷链接',consumable:'耗材管理',memo:'IT 备忘录'};
const operationNames={view:'查看',create:'新增/提交',edit:'编辑',comment:'留言',internal_note:'内部备注',claim:'接单',assign:'分配',transfer:'转派',close:'关闭',cancel:'取消',reopen:'重开',correct:'纠正时间分类',export:'导出',delete:'永久删除',archive:'归档/恢复',import:'导入',password:'设置密码',roles:'分配角色',publish:'发布/撤下',receive:'采购入库',issue:'领用出库',secret_view:'查看密码'};
async function roles(){const result=await api('/api/roles');state.roles=result.items;state.permissionList=result.permissions;setPage(head('角色与模块权限','每项操作绑定数据范围，再将角色分配给用户。',can('role.edit')?'<button class="primary" data-action="role-create">＋ 新建角色</button>':'')+`<section class="panel">${table(['角色','编码','说明','状态','操作'],result.items.map(r=>[esc(r.name),esc(r.code),esc(r.description||'—'),r.is_archived?'已停用':'有效',r.code==='admin'?'<span class="muted">系统管理角色</span>':`<div class="actions"><button class="small" data-action="role-edit" data-id="${r.id}">配置权限</button><button class="small" data-action="role-state" data-id="${r.id}">${r.is_archived?'启用':'停用'}</button></div>`]))}</section>`,'角色与模块权限');}
function roleForm(key=null){
  const r=state.roles.find(v=>v.id===key)||{};const selected=Object.fromEntries((r.permissions||[]).map(g=>[g.code,g]));let last='';
  const permissions=state.permissionList.map(p=>{
    const g=selected[p.code];let heading='';if(p.module!==last){heading=`<h3 class="section-label">${esc(moduleNames[p.module]||p.module)}</h3>`;last=p.module;}
    return heading+`<div class="permission-row"><label><input type="checkbox" name="permissions" value="${p.code}" ${g?'checked':''}>${esc(operationNames[p.code.split('.')[1]]||p.code)} <small class="help">${esc(p.code)}</small></label>${select('scope_'+p.code,(p.supports_data_scope?['own','assigned','site','department','all']:['none']).map(v=>({value:v,name:names[v]})),g?.data_scope||(p.supports_data_scope?'own':'none'),true)}${p.supports_data_scope?`<div class="permission-scope help" data-scope-type="site" ${g?.data_scope==='site'?'':'hidden'}>选择区域：${select('sites_'+p.code,state.lookup.sites,g?.site_ids||[],false,true)}</div><div class="permission-scope help" data-scope-type="department" ${g?.data_scope==='department'?'':'hidden'}>选择部门：${select('departments_'+p.code,state.lookup.departments,g?.department_ids||[],false,true)}</div>`:''}</div>`;
  }).join('');
  formModal(key?'配置角色权限':'新建角色',`${!key?field('角色编码',input('code','',true),true):''}${field('角色名称',input('name',r.name||'',true),true)}${field('说明',input('description',r.description||''))}<div class="callout">同一操作的多角色范围取并集；查看全部不会让“仅修改本人”变成修改全部。</div>${permissions}`,async form=>{
    const fd=new FormData(form);const body={name:fd.get('name'),description:fd.get('description'),permissions:fd.getAll('permissions').map(code=>({code,scope:fd.get('scope_'+code),site_ids:fd.getAll('sites_'+code),department_ids:fd.getAll('departments_'+code)}))};if(key)body.version=r.version;else body.code=fd.get('code');
    await api('/api/roles'+(key?'/'+key:''),{method:key?'PUT':'POST',body});$('#modal').close();await init();toast('角色权限已保存');
  });
}
async function notifications(){const items=await api('/api/notifications');state.items=items;const actions=state.unreadNotifications?'<button class="primary" data-action="notification-read-all">✓ 一键全部已读</button>':'';setPage(head('站内消息','工单进展、公开留言和公司公告集中查看。',actions)+`<section class="panel">${items.length?items.map(n=>`<div class="notice"><span class="tag">${n.read_at?'已读':'未读'}</span><div><a href="${n.ticket_id?'#ticket/'+n.ticket_id:n.announcement_id?'#announcements':'#notifications'}" data-action="notification-read" data-id="${n.id}">${esc(n.title)}</a><div class="help">${esc(n.message_text||'')}</div></div><span class="date">${time(n.created_at)}</span></div>`).join(''):empty('暂无消息')}</section>`,'站内消息');}
async function auditPage(){const d=await api('/api/audit?'+new URLSearchParams({page:state.page,page_size:state.pageSize}));setPage(head('操作审计','记录授权、业务变更、发布、导入与管理员操作。')+`<section class="panel">${table(['时间','操作者','动作','对象类型','结果'],d.items.map(a=>[time(a.occurred_at),esc(a.actor_name_snapshot),esc(a.action_code),esc(a.target_type),esc(a.result_code)]))}${pager(d)}</section>`,'操作审计');}

document.addEventListener('submit',async event=>{
  const form=event.target;event.preventDefault();const button=form.querySelector('button[type="submit"]');if(button)button.disabled=true;
  try{
    if(form.id==='modal-form'){const handler=modalHandler;await handler?.(form);}
    else if(form.id==='filter-form'){const fd=new FormData(form);state.q=fd.get('q')||'';state.status=fd.get('status')||'';state.kind=fd.get('kind')||'';state.departmentId=fd.get('department_id')||'';state.archived=fd.has('archived');state.page=1;await route();}
    else if(form.matches('.pager-jump')){const pages=Number(form.dataset.pages)||1,page=Number(form.elements.page.value);if(!Number.isInteger(page)||page<1||page>pages)throw Error(`请输入 1 到 ${pages} 之间的页码`);state.page=page;await route();}
    else if(form.id==='report-filter'){const fd=new FormData(form);state.reportStart=fd.get('start');state.reportEnd=fd.get('end');await route();}
    else if(form.id==='consumable-filter'){const fd=new FormData(form);consumableFilters={q:fd.get('q')||'',month:fd.get('month')||'',archived:fd.has('archived')};state.page=1;await consumablePage();}
    else if(form.id==='memo-filter'){const fd=new FormData(form);memoFilters={q:fd.get('q')||'',category:fd.get('category')||''};state.page=1;await memoPage();}
    else if(form.id==='ai-chat-form'){
      const message=form.elements.message.value.trim();if(!message)throw Error('请输入要咨询的问题');
      aiMessages=[...aiMessages.slice(-10),{role:'user',content:message}];renderAiConversation();form.reset();
      const result=await api('/api/ai/chat',{method:'POST',body:{messages:aiMessages}});aiMessages.push({role:'assistant',content:result.answer});renderAiConversation(result.recommendations||[],result);
    }
    else if(form.id==='ai-settings-form'){
      const fd=new FormData(form),body={enabled:fd.has('enabled'),endpoint_url:fd.get('endpoint_url'),model_name:fd.get('model_name'),clear_api_key:fd.has('clear_api_key'),timeout_seconds:Number(fd.get('timeout_seconds')),max_results:Number(fd.get('max_results')),answer_mode:fd.get('answer_mode'),no_match_action:fd.get('no_match_action'),system_prompt:fd.get('system_prompt'),version:Number(form.dataset.version)};
      if(fd.get('api_key'))body.api_key=fd.get('api_key');
      await api('/api/ai/settings',{method:'PUT',body});toast('AI 助手设置已保存');await aiSettingsPage();
    }
    else if(form.id==='new-ticket-form'){
      const fd=new FormData(form);const files=fd.getAll('files').filter(v=>v.size);if(files.length>5||files.some(v=>v.size>20*1024*1024))throw Error('最多 5 个附件，单个不得超过 20 MB');
      const body=Object.fromEntries([...fd.entries()].filter(([k])=>k!=='files'));const key=form.dataset.submitKey||(form.dataset.submitKey=crypto.randomUUID());
      const ticket=await api('/api/tickets',{method:'POST',body,headers:{'Idempotency-Key':key}});
      let failed=false;for(const file of files){const upload=new FormData();upload.append('file',file);upload.append('message','提交时附件');try{await api('/api/tickets/'+ticket.id+'/attachments',{method:'POST',body:upload});}catch(error){failed=true;toast('工单已提交，附件未上传：'+error.message);}}
      location.hash='ticket/'+ticket.id;if(!failed)toast('工单已提交');
    }else if(form.id==='comment-form'){
      await api('/api/tickets/'+currentTicket.id+'/events',{method:'POST',body:{body:form.elements.body.value,internal:!!form.elements.internal?.checked}});await route();toast('留言已发送');
    }
  }catch(error){
    if(form.id==='modal-form'){$('.modal-error').innerHTML=`<div class="error">${esc(error.message)}</div>`;}
    else if(form.id==='new-ticket-form')$('#ticket-error').innerHTML=`<div class="error">${esc(error.message)}</div>`;
    else if(form.id==='ai-chat-form'){aiMessages.push({role:'assistant',content:error.message});renderAiConversation();}
    else if(form.id==='ai-settings-form')$('#ai-settings-error').innerHTML=`<div class="error">${esc(error.message)}</div>`;
    else toast(error.message);
  }finally{if(button)button.disabled=false;}
});
document.addEventListener('click',async event=>{
  const el=event.target.closest('[data-action]');if(!el||el.disabled)return;const action=el.dataset.action,key=el.dataset.id;
  if(el.tagName==='A'&&!['notification-read'].includes(action))event.preventDefault();
  try{
    if(action==='close-modal'){if(typeof ledgerCancelInline==='function'&&await ledgerCancelInline())return;if(typeof resetMemoSecret==='function')resetMemoSecret();$('#modal').close();return;}
    if(action==='login')await loginDialog();
    else if(action==='logout'){await api('/api/auth/logout',{method:'POST',body:{}});state.user=null;state.catalog=[];if(typeof resetLedger==='function')resetLedger();await route();}
    else if(action==='password')formModal('修改我的密码',field('当前密码',input('old_password','',true,'password'),true)+field('新密码','<input name="password" type="password" required minlength="8" maxlength="256" autocomplete="new-password">',true,'至少 8 位，无需强制组合。修改后重新登录。'),async form=>{
      await api('/api/auth/password',{method:'POST',body:Object.fromEntries(new FormData(form))});state.user=null;$('#modal').close();await route();toast('密码已修改，请重新登录');
    },true);
    else if(action==='page'){state.page=Number(el.dataset.value);await route();}
    else if(action==='reset-filter'){state.q='';state.status='';state.kind='';state.departmentId='';state.archived=false;state.page=1;await route();}
    else if(action==='reload')await route();
    else if(action==='ai-use-description'){
      const description=$('#new-ticket-form')?.elements.description.value.trim()||'';if(!description)throw Error('请先填写左侧的问题描述');
      const input=$('#ai-chat-form')?.elements.message;if(input){input.value=description;input.focus();}
    }
    else if(action==='ai-fill-ticket'){
      const latest=[...aiMessages].reverse().find(message=>message.role==='user')?.content||'';const description=$('#new-ticket-form')?.elements.description;
      if(description&&latest){description.value=latest;description.focus();description.scrollIntoView({behavior:'smooth',block:'center'});toast('问题已带入工单描述');}
    }
    else if(action==='ai-test'){
      el.disabled=true;const original=el.textContent;el.textContent='正在连接…';
      try{const result=await api('/api/ai/settings/test',{method:'POST',body:{}});toast('连接成功：'+result.answer);}finally{el.disabled=false;el.textContent=original;}
    }
    else if(action==='ai-balance'){
      el.disabled=true;const original=el.textContent;el.textContent='正在查询…';
      try{renderAiBalance(await api('/api/ai/balance'));}finally{el.disabled=false;el.textContent=original;}
    }
    else if(action.startsWith('ipam-')||action.startsWith('computer-'))await ipamAction(action,el);
    else if(action.startsWith('consumable-'))await consumableAction(action,el);
    else if(action.startsWith('memo-'))await memoAction(action,el);
    else if(action.startsWith('ticket-'))await ticketAction(action.slice(7));
    else if(action==='recommend'){
      const description=$('#new-ticket-form')?.elements.description.value||'';
      const r=await api('/api/knowledge/recommendations',{method:'POST',body:{description,max_results:5}});
      $('#recommendations').innerHTML=r.items.length?r.items.map(a=>`<div class="notice"><a href="${esc(a.reader_url)}" target="_blank" rel="noopener">${esc(a.title)} →</a></div>`).join(''):'<p class="help">暂未找到匹配手册，可以直接提交工单。</p>';
    }else if(action==='announcement'){const a=await api('/api/announcements/'+key);modal(a.title,`<p class="help">发布人：${esc(a.publisher_name||'IT')} · ${time(a.published_at)}</p><div class="pretext">${esc(a.body)}</div>${a.attachments.length?`<h3 class="section-label">附件</h3>${a.attachments.map(v=>`<div class="notice"><span>${esc(v.original_name)} <small class="help">${Math.ceil(v.size_bytes/1024)} KB</small></span><span class="table-actions"><a class="button small" href="${esc(v.url)}" target="_blank" rel="noopener">查看</a><a class="button small" href="${esc(v.url)}?download=true">下载</a></span></div>`).join('')}`:''}`);}
    else if(action==='knowledge-upload')await knowledgeUpload();
    else if(action==='knowledge-version')await knowledgeUpload(key);
    else if(action==='knowledge-publish')await knowledgePublish(key);
    else if(action==='knowledge-delete')knowledgeDelete(key);
    else if(action==='data-create')await dataForm();
    else if(action==='data-edit')await dataForm(key);
    else if(action==='announcement-attachments')await announcementAttachments(key);
    else if(action==='announcement-attachment-delete'){await api(`/api/announcements/${el.dataset.announcement}/attachments/${key}`,{method:'DELETE',body:{}});if(el.dataset.returnEdit)await dataForm(el.dataset.announcement);else await announcementAttachments(el.dataset.announcement);toast('附件已移除');}
    else if(action==='data-publish')await dataOperation('publish',key);
    else if(action==='data-archive')await dataOperation('archive',key);
    else if(action==='data-delete')await dataOperation('delete',key);
    else if(action==='template-download')await download('/api/import-templates/'+state.dataSpec.table,state.dataSpec.table+'-template.xlsx');
    else if(action==='data-export')await download('/api/exports/'+state.dataSpec.table+'?q='+encodeURIComponent(state.q),state.dataSpec.table+'-data.xlsx');
    else if(action==='import-open')importOpen();
    else if(action==='user-create')await userForm();
    else if(action==='user-edit')await userForm(key);
    else if(action==='user-reset')resetPassword(key);
    else if(action==='quick-link-create')quickLinkForm();
    else if(action==='quick-link-edit')quickLinkForm(key);
    else if(action==='quick-link-delete'){
      const item=state.items.find(v=>v.id===key);formModal('删除快捷链接',`<div class="callout warning">将永久删除“${esc(item.title)}”。</div>${field('删除原因',input('reason','',true),true)}`,async form=>{
        await api('/api/quick-links/'+key,{method:'DELETE',body:{version:item.version,reason:form.elements.reason.value}});$('#modal').close();await route();toast('快捷链接已删除');
      },true,'确认删除');
    }
    else if(action==='org-position-create')positionForm();
    else if(action==='org-position-edit')positionForm(key);
    else if(action==='org-sync-ehr'){
      el.disabled=true;const original=el.textContent;el.textContent='正在同步…';
      try{const result=await api('/api/organization/sync-ehr',{method:'POST',body:{}});toast(result.message);await new Promise(resolve=>setTimeout(resolve,600));await loadPrivate();await route();}finally{el.disabled=false;el.textContent=original;}
    }
    else if(action==='org-sync-ldap'){
      const status=await api('/api/organization/ldap-status');const sync=status.state;
      modal('LDAP / Active Directory 同步',`<div class="callout ${status.configured?'success':'warning'}">${esc(status.message)}</div><dl class="detail-list"><dt>服务器</dt><dd>${esc(status.host||'未配置')}</dd><dt>Base DN</dt><dd>${esc(status.base_dn||'未配置')}</dd><dt>连接安全</dt><dd>${status.use_ssl?'LDAPS':'LDAP / StartTLS'}${status.validate_certificate?' · 验证证书':' · 不验证证书'}</dd><dt>自动同步</dt><dd>${esc(status.schedule)}</dd><dt>最后状态</dt><dd>${esc(sync?.last_status||'尚未同步')}</dd><dt>最后成功</dt><dd>${time(sync?.last_success_at)}</dd></dl>${sync?.last_message?`<div class="callout ${sync.last_status==='error'?'warning':''}">${esc(sync.last_message)}</div>`:''}<p class="muted">只读取域用户属性，不修改域对象；新增门户用户默认停用，管理员核对后再启用。域同步不会替换门户密码或角色。</p>${status.configured?'<div class="form-footer"><button data-action="org-test-ldap">测试连接</button><button class="primary" data-action="org-run-ldap">开始同步</button></div>':''}`,null,true);
    }
    else if(action==='org-test-ldap'){
      el.disabled=true;const original=el.textContent;el.textContent='正在测试…';try{const result=await api('/api/organization/test-ldap',{method:'POST',body:{}});toast(`${result.message}，已读取 ${result.sample_count} 条样本`);}finally{el.disabled=false;el.textContent=original;}
    }
    else if(action==='org-run-ldap'){
      el.disabled=true;const original=el.textContent;el.textContent='正在启动…';try{const result=await api('/api/organization/sync-ldap',{method:'POST',body:{}});$('#modal').close();toast(result.message);await new Promise(resolve=>setTimeout(resolve,600));await loadPrivate();await route();}finally{el.disabled=false;el.textContent=original;}
    }
    else if(action==='user-delete'){
      const u=state.items.find(v=>v.id===key);formModal('删除用户并匿名化',`<div class="callout warning">将清除 ${esc(u.display_name)} 的身份资料和凭据，保留匿名 ID 及历史业务关系。请先转派未结束工单、电脑和静态 IP。${u.source_type==='ehr'?'该人员仍存在于 EHR 时，下次同步会重新导入。':u.source_type==='ldap'?'该人员仍存在于域目录时，下次同步会重新导入。':''}</div>${field('删除原因',input('reason','',true),true)}`,async form=>{
        await api('/api/users/'+key,{method:'DELETE',body:{version:u.version,confirm:key,reason:form.elements.reason.value}});$('#modal').close();await route();toast('身份资料已清除，历史关系保留');
      });
    }
    else if(action==='role-create')roleForm();
    else if(action==='role-edit')roleForm(key);
    else if(action==='role-state'){
      const r=state.roles.find(v=>v.id===key);formModal(r.is_archived?'启用角色':'停用角色',`<p>${esc(r.name)}</p><p class="muted">更新后相关用户下一次请求将采用新的权限状态。</p>`,async()=>{
        await api('/api/roles/'+key+'/state',{method:'POST',body:{version:r.version,disabled:!r.is_archived}});$('#modal').close();await init();
      });
    }
    else if(action==='notification-read'){const result=await api('/api/notifications/'+key+'/read',{method:'POST',body:{}});state.unreadNotifications=result.unread_count||0;navigation();}
    else if(action==='notification-read-all'){const result=await api('/api/notifications/read-all',{method:'POST',body:{}});state.unreadNotifications=result.unread_count||0;await route();toast(result.updated_count?`已将 ${result.updated_count} 条消息标记为已读`:'没有未读消息');}
  }catch(error){toast(error.message);}
});
window.addEventListener('hashchange',route);
document.addEventListener('change',async event=>{
  if(event.target.matches('[data-action="page-size"]')){state.pageSize=Number(event.target.value);state.page=1;await route();return;}
  if(event.target.name?.startsWith('scope_'))event.target.closest('.permission-row').querySelectorAll('[data-scope-type]').forEach(el=>el.hidden=el.dataset.scopeType!==event.target.value);
});
// Check expiry without treating this background request as user activity.
setInterval(async()=>{if(state.user){try{const s=await api('/api/session',{activity:false});if(!s.user){state.user=null;await route();toast('登录已过期，请重新登录');}else state.user=s.user;}catch(_){/* Next explicit operation reports connectivity. */}}},60000);
window.addEventListener('DOMContentLoaded',init,{once:true});

