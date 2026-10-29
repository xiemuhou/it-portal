/* Encrypted IT memos. Passwords are fetched only after an explicit action. */
const memoCategories={system:'系统账号',network:'网络设备',server:'服务器',database:'数据库',supplier:'供应商',other:'其他'};
let memoItems=[],memoFilters={q:'',category:''},revealedMemoSecret='';

function memoCategoryOptions(value='system'){
  return `<select name="category" data-native-select required>${Object.entries(memoCategories).map(([key,label])=>`<option value="${key}" ${key===value?'selected':''}>${label}</option>`).join('')}</select>`;
}
function memoAddress(value){
  if(!value)return '—';
  return /^https?:\/\//i.test(value)?`<a href="${esc(value)}" target="_blank" rel="noopener">${esc(value)} ↗</a>`:esc(value);
}
function memoTags(value){
  const tags=String(value||'').split(/[,，]/).map(v=>v.trim()).filter(Boolean);
  return tags.length?`<div class="memo-tags">${tags.map(v=>`<span>${esc(v)}</span>`).join('')}</div>`:'—';
}

async function memoPage(){
  const params=new URLSearchParams({page:state.page,page_size:state.pageSize,q:memoFilters.q,category:memoFilters.category});
  const data=await api('/api/memos?'+params);memoItems=data.items;
  const categories=`<select name="category" data-native-select><option value="">全部分类</option>${Object.entries(memoCategories).map(([key,label])=>`<option value="${key}" ${memoFilters.category===key?'selected':''}>${label}</option>`).join('')}</select>`;
  const filters=`<form id="memo-filter" class="filters"><input name="q" value="${esc(memoFilters.q)}" placeholder="标题、地址、用户名、标签或备注">${categories}<button type="submit">查询</button><button type="button" data-action="memo-reset">重置</button></form>`;
  const rows=data.items.map(v=>[
    `<strong>${esc(v.title)}</strong><div class="help">${esc(v.creator_name||'—')} · ${minuteTime(v.updated_at)}</div>`,
    esc(memoCategories[v.category]||v.category),memoAddress(v.system_address),esc(v.username||'—'),memoTags(v.tags),v.notes?`<div class="memo-notes">${esc(v.notes)}</div>`:'—',
    `<div class="table-actions">${v.has_password&&can('memo.secret_view')?`<button data-action="memo-secret" data-id="${v.id}">查看密码</button>`:''}${v.created_by_user_id===state.user.id&&can('memo.edit')?`<button data-action="memo-edit" data-id="${v.id}">编辑</button>`:''}${v.created_by_user_id===state.user.id&&can('memo.delete')?`<button class="danger" data-action="memo-delete" data-id="${v.id}">删除</button>`:''}</div>`
  ]);
  setPage(head('IT 备忘录','供管理员和 IT 人员集中记录零散的系统地址和账号凭据。',can('memo.edit')?'<button class="primary" data-action="memo-create">＋ 新增备忘录</button>':'')+
    `<section class="panel">${filters}<div class="callout memo-security">仅管理员和 IT 人员可以访问。密码不会显示在列表、搜索、导出或审计内容中，请勿把密码写入备注。</div>${table(['标题','分类','系统 / 设备地址','用户名','标签','备注','操作'],rows)}${pager(data)}</section>`,'IT 备忘录');
}

function memoForm(item={}){
  const editing=!!item.id;
  formModal(editing?'编辑备忘录':'新增备忘录',`<div class="form-grid">${field('标题',input('title',item.title||'',true),true)}${field('分类',memoCategoryOptions(item.category||'system'),true)}${field('系统或设备地址',input('system_address',item.system_address||''),false,'可以填写网址、IP 地址或设备名称。')}${field('用户名',input('username',item.username||''))}${field('密码',`<input name="password" type="password" maxlength="4096" autocomplete="new-password" placeholder="${editing&&item.has_password?'已保存；留空保持不变':'按需填写'}">`,false,'密码使用部署凭据密钥加密，页面不会回显已保存密码。')}${field('标签',input('tags',item.tags||''),false,'多个标签使用逗号分隔。')}<div class="field full">${field('备注',`<textarea name="notes" rows="5" maxlength="10000">${esc(item.notes||'')}</textarea>`,false,'管理员和 IT 人员均可查看备注，请勿在备注中填写密码。')}</div>${editing&&item.has_password?'<label class="checkbox-row field full"><input name="clear_password" type="checkbox">清除已保存的密码</label>':''}</div>`,async form=>{
    const fd=new FormData(form),body=Object.fromEntries(fd);body.clear_password=fd.has('clear_password');
    if(!body.password)delete body.password;
    if(editing)body.version=item.version;
    await api('/api/memos'+(editing?'/'+item.id:''),{method:editing?'PUT':'POST',body});resetMemoSecret();$('#modal').close();await memoPage();toast('备忘录已保存');
  });
}

async function copyMemoSecret(){
  if(!revealedMemoSecret)throw Error('密码已经隐藏，请重新查看');
  if(navigator.clipboard?.writeText){try{await navigator.clipboard.writeText(revealedMemoSecret);toast('密码已复制');return;}catch(_){/* Use compatibility fallback below. */}}
  const area=document.createElement('textarea');area.value=revealedMemoSecret;area.style.position='fixed';area.style.opacity='0';document.body.appendChild(area);area.select();
  const copied=document.execCommand('copy');area.remove();if(!copied)throw Error('浏览器不允许复制，请手动选择密码');toast('密码已复制');
}
function resetMemoSecret(){revealedMemoSecret='';const value=$('#memo-secret-value');if(value)value.textContent='••••••••';}

async function memoAction(action,button){
  if(action==='memo-reset'){memoFilters={q:'',category:''};state.page=1;return memoPage();}
  if(action==='memo-create')return memoForm();
  if(action==='memo-copy')return copyMemoSecret();
  const item=memoItems.find(v=>v.id===button.dataset.id);if(!item)throw Error('备忘录列表已变化，请刷新');
  if(action==='memo-edit')return memoForm(item);
  if(action==='memo-secret'){
    const result=await api('/api/memos/'+item.id+'/secret',{method:'POST',body:{}});revealedMemoSecret=result.password;
    modal('查看密码',`<p class="help">${esc(item.title)} · ${esc(item.username||'未登记用户名')}</p><div class="memo-secret"><code id="memo-secret-value">${esc(result.password)}</code><button class="primary" data-action="memo-copy">复制密码</button></div><p class="help">关闭窗口后页面会清除本次解密结果。</p>`);return;
  }
  if(action==='memo-delete')return formModal('删除备忘录',`<div class="callout warning">将删除“${esc(item.title)}”，同时清除其加密密码。操作审计仍会保留。</div>`,async()=>{
    await api('/api/memos/'+item.id,{method:'DELETE',body:{version:item.version}});resetMemoSecret();$('#modal').close();await memoPage();toast('备忘录已删除');
  },true,'确认删除');
}

window.addEventListener('DOMContentLoaded',()=>$('#modal')?.addEventListener('close',resetMemoSecret),{once:true});
