/* Consumable catalog and append-only stock movement views. */
const consumableToday=()=>new Date().toLocaleDateString('sv-SE');
let consumableItems=[],consumableOptions=null,consumableHistoryItem=null,consumableFilters={q:'',month:consumableToday().slice(0,7),archived:false};
const consumableText={inbound:'采购入库',outbound:'领用出库',inbound_reversal:'入库撤销',outbound_return:'出库返库'};

async function loadConsumableOptions(){consumableOptions=await api('/api/consumables/options');}
function consumableNumber(value){const number=Number(value||0);return Number.isInteger(number)?String(number):number.toFixed(2).replace(/0+$/,'').replace(/\.$/,'');}

async function consumablePage(){
  await loadConsumableOptions();
  const params=new URLSearchParams({page:state.page,page_size:state.pageSize,q:consumableFilters.q,month:consumableFilters.month,archived:consumableFilters.archived});
  const data=await api('/api/consumables?'+params);consumableItems=data.items;
  const actions=can('consumable.edit')?'<button class="primary" data-action="consumable-create">＋ 新增耗材</button>':'';
  const filters=`<form id="consumable-filter" class="filters"><input name="q" value="${esc(consumableFilters.q)}" placeholder="耗材名称、编码、分类或规格"><label>统计月份 <input name="month" type="month" value="${esc(data.month)}"></label><label class="checkbox-row"><input name="archived" type="checkbox" ${consumableFilters.archived?'checked':''}>已停用</label><button type="submit">查询</button><button type="button" data-action="consumable-reset">重置</button></form>`;
  const rows=data.items.map(v=>[esc(v.item_code),`<strong>${esc(v.name)}</strong><div class="help">${esc([v.category,v.specification].filter(Boolean).join(' · ')||'未填写分类与规格')}</div>`,
    `<strong class="stock-number ${v.low_stock?'is-low':''}">${esc(consumableNumber(v.current_stock))}</strong> ${esc(v.unit)}${v.low_stock?'<div class="tag pending">库存预警</div>':''}`,
    `<span class="stock-in">＋${esc(consumableNumber(v.month_in))}</span> / <span class="stock-out">－${esc(consumableNumber(v.month_out))}</span>`,
    esc(consumableNumber(v.minimum_stock))+' '+esc(v.unit),ledgerNotes(v.notes),
    `<div class="table-actions">${can('consumable.receive')&&!v.is_archived?`<button data-action="consumable-in" data-id="${v.id}">入库</button>`:''}${can('consumable.issue')&&!v.is_archived?`<button data-action="consumable-out" data-id="${v.id}">出库</button>`:''}<button data-action="consumable-history" data-id="${v.id}">流水</button>${can('consumable.edit')?`<button data-action="consumable-edit" data-id="${v.id}">编辑</button><button class="danger" data-action="consumable-delete" data-id="${v.id}">删除</button>`:''}</div>`]);
  setPage(head('耗材管理','按月登记采购入库和领用出库，库存由全部流水实时汇总。',actions)+`<div class="stock-legend"><span><b class="stock-in">＋ 入库</b> 增加库存</span><span><b class="stock-out">－ 出库</b> 可关联电脑或独立领用</span></div><section class="panel">${filters}${table(['耗材编码','名称 / 规格','当前库存','本月入库 / 出库','最低库存','备注','操作'],rows)}${pager(data)}</section>`,'耗材管理');
}

function consumableItemForm(item={}){
  formModal(item.id?'编辑耗材':'新增耗材',`<div class="form-grid">${field('耗材编码',input('item_code',item.item_code||''),false,item.id?'编码创建后不可修改。':'留空由系统生成。')}${field('耗材名称',input('name',item.name||'',true),true)}${field('分类',input('category',item.category||''),false,'例如打印耗材、存储介质、电脑配件。')}${field('规格型号',input('specification',item.specification||''))}${field('单位',input('unit',item.unit||'个',true),true)}${field('最低库存','<input name="minimum_stock" type="number" min="0" step="0.01" value="'+esc(item.minimum_stock||'0')+'" required>',true,'当前库存小于或等于该值时显示预警。')}<div class="field full">${field('备注','<textarea name="notes" rows="3">'+esc(item.notes||'')+'</textarea>')}</div>${item.id?'<label class="checkbox-row field full"><input name="is_archived" type="checkbox" '+(item.is_archived?'checked':'')+'>停用此耗材</label>':''}</div>`,async form=>{
    const body=Object.fromEntries(new FormData(form));body.minimum_stock=body.minimum_stock||'0';
    if(item.id){body.version=item.version;body.is_archived=form.elements.is_archived.checked;delete body.item_code;}
    await api('/api/consumables'+(item.id?'/'+item.id:''),{method:item.id?'PUT':'POST',body});$('#modal').close();await consumablePage();toast('耗材资料已保存');
  });
}

function consumableMovementForm(item,type){
  const today=consumableToday(),inbound=type==='inbound';
  const body=inbound?`${field('数量','<input name="quantity" type="number" min="0.01" step="0.01" required>',true)}${field('采购单价（元）','<input name="unit_cost" type="number" min="0" step="0.01">')}${field('供应商',input('supplier'))}`:
    `${field('数量','<input name="quantity" type="number" min="0.01" step="0.01" required>',true)}${field('关联电脑',`<select name="computer_id"><option value="">不关联电脑</option>${consumableOptions.computers.map(v=>`<option value="${v.id}">${esc(v.name)}</option>`).join('')}</select>`,false,'选择后会显示在该电脑的配件信息中。')}${field('领用人员',`<select name="user_id"><option value="">不选择人员</option>${consumableOptions.users.map(v=>`<option value="${v.id}">${esc(v.name)} · ${esc(v.department_name||'未分配部门')}</option>`).join('')}</select>`)}${field('领用部门',`<select name="department_id"><option value="">不选择部门</option>${consumableOptions.departments.map(v=>`<option value="${v.id}">${esc(v.name)}</option>`).join('')}</select>`)}${field('其他领用对象',input('recipient_text'),false,'打印机、会议室或其他公共设备可直接填写。')}${field('用途',input('purpose','',true),true)}${field('单据编号',input('reference_no'))}`;
  formModal((inbound?'采购入库 · ':'领用出库 · ')+item.name,`<div class="callout"><strong>当前库存：${esc(consumableNumber(item.current_stock))} ${esc(item.unit)}</strong></div><div class="form-grid">${field(inbound?'入库日期':'出库日期','<input name="occurred_on" type="date" max="'+today+'" value="'+today+'" required>',true)}${body}<div class="field full">${field('备注','<textarea name="notes" rows="3"></textarea>')}</div></div>`,async form=>{
    const value=Object.fromEntries(new FormData(form));value.movement_type=type;value.version=item.version;
    const result=await api('/api/consumables/'+item.id+'/movements',{method:'POST',body:value});$('#modal').close();await consumablePage();toast(`${consumableText[type]}完成，当前库存 ${consumableNumber(result.current_stock)} ${item.unit}`);
  },false,inbound?'确认入库':'确认出库');
  if(!inbound){
    const form=$('#modal-form'),computer=form.elements.computer_id,user=form.elements.user_id,department=form.elements.department_id;
    computer.addEventListener('change',()=>{const value=consumableOptions.computers.find(v=>v.id===computer.value);if(value){user.value=value.user_id||'';department.value=value.department_id||'';} });
    user.addEventListener('change',()=>{const value=consumableOptions.users.find(v=>v.id===user.value);if(value)department.value=value.department_id||'';});
  }
}

async function consumableHistoryPage(key){
  const params=new URLSearchParams({page:state.page,page_size:state.pageSize});const data=await api('/api/consumables/'+key+'/movements?'+params);
  consumableHistoryItem={...data.item,current_stock:data.current_stock};
  const increases=new Set(['inbound','outbound_return']);
  const rows=data.items.map(v=>{
    const reverseAllowed=!v.is_reversed&&!v.reversal_of_id&&((v.movement_type==='inbound'&&can('consumable.receive'))||(v.movement_type==='outbound'&&can('consumable.issue')));
    const action=reverseAllowed?`<button data-action="consumable-reverse" data-item="${data.item.id}" data-id="${v.id}" data-type="${v.movement_type}">${v.movement_type==='inbound'?'撤销入库':'返库'}</button>`:v.is_reversed?'<span class="tag muted">已处理</span>':'—';
    return [day(v.occurred_on),`<span class="tag ${increases.has(v.movement_type)?'closed':'pending'}">${consumableText[v.movement_type]||v.movement_type}</span>${v.is_reversed?'<div class="help">原流水已撤销/返库</div>':''}`,
      `${increases.has(v.movement_type)?'+':'-'}${esc(consumableNumber(v.quantity))} ${esc(v.unit_snapshot)}`,v.unit_cost!==null&&v.unit_cost!==undefined?'¥'+esc(consumableNumber(v.unit_cost)):'—',
      esc(v.supplier||v.computer_asset_code||v.user_name||v.department_name||v.recipient_text||'—'),esc(v.purpose||'—'),esc(v.reference_no||'—'),ledgerNotes(v.notes),esc(v.actor_name||'—'),action];
  });
  setPage(head(data.item.name+' · 出入库流水',`当前库存 ${consumableNumber(data.current_stock)} ${data.item.unit}`,`<a class="button" href="#consumables">← 返回耗材管理</a>`)+`<section class="panel">${table(['出入库日期','类型','数量','单价','供应商 / 领用对象','用途','单据编号','备注','操作人','操作'],rows)}${pager(data)}</section>`,'耗材流水');
}

function consumableReverseForm(button){
  const inbound=button.dataset.type==='inbound',itemId=button.dataset.item,movementId=button.dataset.id;
  formModal(inbound?'撤销入库':'出库返库',`<div class="callout">${inbound?'撤销后将从当前库存扣除该笔入库数量；库存不足时不能撤销。':'返库后将恢复该笔出库数量，并取消它与电脑的配件关联。'}</div>${field('操作原因','<textarea name="reason" rows="3" required maxlength="500" placeholder="请填写返库或撤销原因"></textarea>',true)}`,async form=>{
    const result=await api(`/api/consumables/${itemId}/movements/${movementId}/reverse`,{method:'POST',body:{reason:form.elements.reason.value,version:consumableHistoryItem.version}});
    $('#modal').close();await consumableHistoryPage(itemId);toast(`${inbound?'入库已撤销':'耗材已返库'}，当前库存 ${consumableNumber(result.current_stock)} ${consumableHistoryItem.unit}`);
  },false,inbound?'确认撤销':'确认返库');
}

function consumableDeleteForm(item){
  formModal('删除耗材品类',`<div class="callout"><strong>${esc(item.name)}</strong><p>仅没有出入库流水的耗材可以删除；已有流水请在编辑页面将其停用。</p></div>`,async()=>{
    await api('/api/consumables/'+item.id,{method:'DELETE',body:{version:item.version}});$('#modal').close();await consumablePage();toast('耗材品类已删除');
  },false,'确认删除');
}

async function consumableAction(action,button){
  if(action==='consumable-reset'){consumableFilters={q:'',month:consumableToday().slice(0,7),archived:false};state.page=1;return consumablePage();}
  if(action==='consumable-create')return consumableItemForm();
  if(action==='consumable-reverse')return consumableReverseForm(button);
  const item=consumableItems.find(v=>v.id===button.dataset.id);if(!item)throw Error('耗材列表已变化，请刷新');
  if(action==='consumable-edit')return consumableItemForm(item);
  if(action==='consumable-in')return consumableMovementForm(item,'inbound');
  if(action==='consumable-out')return consumableMovementForm(item,'outbound');
  if(action==='consumable-delete')return consumableDeleteForm(item);
  if(action==='consumable-history'){location.hash='consumables/history/'+item.id;}
}
