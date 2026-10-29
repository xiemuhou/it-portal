"""Consumable catalog, stock balances and immutable inbound/outbound history."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re

import sqlalchemy as sa
from fastapi import Request

from .database import TABLES as T, insert_row, row, utcnow, uid
from .security import audit, fail, require


MOVEMENT_TYPES={'inbound','outbound'}
ALL_MOVEMENT_TYPES=MOVEMENT_TYPES|{'inbound_reversal','outbound_return'}
STOCK_INCREASE_TYPES={'inbound','outbound_return'}


def _text(value,label,limit,required=False):
    if value is None:value=''
    if not isinstance(value,str):fail(label+'格式无效')
    value=value.strip()
    if required and not value:fail('请填写'+label)
    if '\x00' in value or len(value)>limit:fail(label+'内容过长或无效')
    return value or None


def _decimal(value,label,allow_zero=False):
    if value in (None,''):return Decimal('0') if allow_zero else None
    try:number=Decimal(str(value))
    except (InvalidOperation,ValueError,TypeError):fail(label+'须为有效数字')
    if not number.is_finite() or number<0 or (not allow_zero and number==0) or number>=Decimal('1000000000') or number.as_tuple().exponent < -2:
        fail(label+('须为不小于 0、最多两位小数的有效数字' if allow_zero else '须为大于 0、最多两位小数的有效数字'))
    return number


def _date(value):
    try:result=date.fromisoformat(str(value))
    except ValueError:fail('出入库日期无效')
    if result>date.today():fail('出入库日期不能晚于今天')
    return result


def _month(value):
    value=value or date.today().strftime('%Y-%m')
    if not re.fullmatch(r'\d{4}-\d{2}',value):fail('月份格式无效')
    try:start=date.fromisoformat(value+'-01')
    except ValueError:fail('月份格式无效')
    end=date(start.year+1,1,1) if start.month==12 else date(start.year,start.month+1,1)
    return value,start,end


def _stock_expression():
    movement=T['consumable_movements']
    return sa.case((movement.c.movement_type.in_(STOCK_INCREASE_TYPES),movement.c.quantity),else_=-movement.c.quantity)


def _current_stock(conn,item_id):
    movement=T['consumable_movements']
    return Decimal(conn.execute(sa.select(sa.func.coalesce(sa.func.sum(_stock_expression()),0)).where(movement.c.item_id==item_id)).scalar_one())


def _item_result(value):
    result=dict(value)
    for key in ('current_stock','month_in','month_out','minimum_stock'):
        result[key]=str(result.get(key) or Decimal('0'))
    result['low_stock']=Decimal(result['current_stock'])<=Decimal(result['minimum_stock'])
    return result


def register(app,engine,out,current_user):
    @app.get('/api/consumables/options')
    def options(request:Request):
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'consumable.view')
            departments=[dict(v) for v in conn.execute(sa.select(T['departments'].c.id,T['departments'].c.name).where(T['departments'].c.is_archived==False).order_by(T['departments'].c.name)).mappings()]
            department_names={v['id']:v['name'] for v in departments}
            users=[{'id':v['id'],'name':v['display_name'],'department_id':v['department_id'],'department_name':department_names.get(v['department_id'])} for v in conn.execute(
                sa.select(T['users'].c.id,T['users'].c.display_name,T['users'].c.department_id).where(T['users'].c.is_archived==False,T['users'].c.account_state=='active').order_by(T['users'].c.display_name)).mappings()]
            computer_users=T['users'].alias('computer_users')
            computers=[{'id':v['id'],'asset_code':v['asset_code'],'device_type':v['device_type'],'display_user':v['display_user'] or '公共设备',
                'name':f"{v['asset_code']} · {v['display_user'] or '公共设备'} · {v['device_type']}",'department_id':v['department_id'],'user_id':v['user_id']} for v in conn.execute(
                sa.select(T['computer_assets'].c.id,T['computer_assets'].c.asset_code,T['computer_assets'].c.device_type,T['computer_assets'].c.department_id,
                    T['computer_assets'].c.user_id,computer_users.c.display_name.label('display_user')).select_from(
                    T['computer_assets'].outerjoin(computer_users,computer_users.c.id==T['computer_assets'].c.user_id))
                .where(T['computer_assets'].c.is_archived==False).order_by(T['computer_assets'].c.asset_code)).mappings()]
            return out({'departments':departments,'users':users,'computers':computers})

    @app.get('/api/consumables')
    def items(request:Request,page:int=1,page_size:int=10,q:str='',month:str='',archived:bool=False):
        if page_size not in (10,20,50):fail('每页条数仅支持 10、20、50')
        month_value,start,end=_month(month)
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'consumable.view');items=T['consumable_items'];movements=T['consumable_movements']
            stock=sa.select(movements.c.item_id,sa.func.sum(_stock_expression()).label('current_stock')).group_by(movements.c.item_id).subquery()
            monthly=sa.select(movements.c.item_id,
                sa.func.sum(sa.case((movements.c.movement_type.in_(STOCK_INCREASE_TYPES),movements.c.quantity),else_=0)).label('month_in'),
                sa.func.sum(sa.case((movements.c.movement_type.in_({'outbound','inbound_reversal'}),movements.c.quantity),else_=0)).label('month_out')).where(
                movements.c.occurred_on>=start,movements.c.occurred_on<end).group_by(movements.c.item_id).subquery()
            query=sa.select(items,sa.func.coalesce(stock.c.current_stock,0).label('current_stock'),sa.func.coalesce(monthly.c.month_in,0).label('month_in'),
                sa.func.coalesce(monthly.c.month_out,0).label('month_out')).outerjoin(stock,stock.c.item_id==items.c.id).outerjoin(monthly,monthly.c.item_id==items.c.id).where(items.c.is_archived==archived)
            q=q.strip()
            if q:query=query.where(sa.or_(items.c.item_code.contains(q,autoescape=True),items.c.name.contains(q,autoescape=True),items.c.category.contains(q,autoescape=True),items.c.specification.contains(q,autoescape=True)))
            total=conn.execute(sa.select(sa.func.count()).select_from(query.subquery())).scalar_one();page=max(1,page)
            values=conn.execute(query.order_by(items.c.name,items.c.id).offset((page-1)*page_size).limit(page_size)).mappings().all()
            return out({'items':[_item_result(v) for v in values],'total':total,'page':page,'page_size':page_size,'month':month_value})

    @app.post('/api/consumables')
    def create_item(request:Request,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'consumable.edit')
            code=_text(body.get('item_code'),'耗材编码',64) or ('HC-'+date.today().strftime('%Y%m')+'-'+uid()[-6:].upper())
            if conn.execute(sa.select(T['consumable_items'].c.id).where(T['consumable_items'].c.item_code==code)).first():fail('耗材编码已存在',409)
            value=insert_row(conn,'consumable_items',{'item_code':code,'name':_text(body.get('name'),'耗材名称',160,True),
                'category':_text(body.get('category'),'分类',80),'specification':_text(body.get('specification'),'规格型号',200),
                'unit':_text(body.get('unit'),'单位',32,True),'minimum_stock':_decimal(body.get('minimum_stock'),'最低库存',True),
                'notes':_text(body.get('notes'),'备注',1000)},user['id'])
            audit(conn,user,'consumable.item.create','consumable_items',value['id'],{'item_code':code,'name':value['name']})
            return out(dict(value),201)

    @app.put('/api/consumables/{key}')
    def edit_item(request:Request,key:str,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'consumable.edit');old=row(conn,'consumable_items',key)
            if not old:fail('耗材不存在',404)
            if body.get('version')!=old['version']:fail('耗材资料已变化，请刷新',409)
            archived=body.get('is_archived') is True
            values={'name':_text(body.get('name'),'耗材名称',160,True),'category':_text(body.get('category'),'分类',80),
                'specification':_text(body.get('specification'),'规格型号',200),'unit':_text(body.get('unit'),'单位',32,True),
                'minimum_stock':_decimal(body.get('minimum_stock'),'最低库存',True),'notes':_text(body.get('notes'),'备注',1000),
                'is_archived':archived,'version':old['version']+1,'updated_at':utcnow(),'updated_by_user_id':user['id']}
            if conn.execute(T['consumable_items'].update().where(T['consumable_items'].c.id==key,T['consumable_items'].c.version==old['version']).values(**values)).rowcount!=1:fail('耗材资料已变化，请刷新',409)
            audit(conn,user,'consumable.item.edit','consumable_items',key,{'archived':archived})
            return out(dict(row(conn,'consumable_items',key)))

    @app.delete('/api/consumables/{key}')
    def delete_item(request:Request,key:str,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'consumable.edit');old=row(conn,'consumable_items',key)
            if not old:fail('耗材品类不存在',404)
            if body.get('version')!=old['version']:fail('耗材资料已变化，请刷新后重试',409)
            movement_count=conn.execute(sa.select(sa.func.count()).select_from(T['consumable_movements']).where(T['consumable_movements'].c.item_id==key)).scalar_one()
            if movement_count:fail('该耗材已有出入库流水，不能删除，请改为停用',409)
            audit(conn,user,'consumable.item.delete','consumable_items',key,{'item_code':old['item_code'],'name':old['name']})
            conn.execute(T['consumable_items'].delete().where(T['consumable_items'].c.id==key))
            return out({'deleted':True})

    @app.post('/api/consumables/{key}/movements')
    def add_movement(request:Request,key:str,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);item=row(conn,'consumable_items',key)
            if not item or item['is_archived']:fail('耗材不存在或已停用',404)
            movement_type=body.get('movement_type')
            if movement_type not in MOVEMENT_TYPES:fail('出入库类型无效')
            require(conn,user,'consumable.receive' if movement_type=='inbound' else 'consumable.issue')
            if body.get('version')!=item['version']:fail('库存已发生变化，请刷新后重试',409)
            quantity=_decimal(body.get('quantity'),'数量');business_date=_date(body.get('occurred_on'))
            computer=department=linked_user=None
            if movement_type=='outbound':
                if _current_stock(conn,key)<quantity:fail('库存不足，无法出库',409)
                computer=row(conn,'computer_assets',body.get('computer_id')) if body.get('computer_id') else None
                if computer and computer['is_archived']:fail('关联电脑不存在或已删除')
                linked_user=row(conn,'users',body.get('user_id')) if body.get('user_id') else None
                if computer:
                    linked_user=row(conn,'users',computer['user_id']) if computer.get('user_id') else None
                    department=row(conn,'departments',computer['department_id']) if computer.get('department_id') else None
                elif linked_user:
                    if linked_user['is_archived']:fail('领用人员已停用')
                    department=row(conn,'departments',linked_user['department_id']) if linked_user.get('department_id') else None
                elif body.get('department_id'):
                    department=row(conn,'departments',body.get('department_id'))
                recipient=_text(body.get('recipient_text'),'领用对象',160)
                if not computer and not linked_user and (not department or department['is_archived']) and not recipient:fail('独立出库须选择部门、人员或填写领用对象')
                purpose=_text(body.get('purpose'),'用途',300,True)
            else:
                recipient=None;purpose=None
            now=utcnow()
            if conn.execute(T['consumable_items'].update().where(T['consumable_items'].c.id==key,T['consumable_items'].c.version==item['version']).values(
                version=item['version']+1,updated_at=now,updated_by_user_id=user['id'])).rowcount!=1:fail('库存已发生变化，请刷新后重试',409)
            movement=insert_row(conn,'consumable_movements',{'actor_user_id':user['id'],'item_id':key,'movement_type':movement_type,
                'quantity':quantity,'occurred_on':business_date,'unit_cost':_decimal(body.get('unit_cost'),'采购单价',True) if movement_type=='inbound' and body.get('unit_cost') not in (None,'') else None,
                'supplier':_text(body.get('supplier'),'供应商',160) if movement_type=='inbound' else None,
                'reference_no':_text(body.get('reference_no'),'单据编号',128),'computer_id':computer and computer['id'],
                'department_id':department and department['id'],'user_id':linked_user and linked_user['id'],'recipient_text':recipient,
                'purpose':purpose,'notes':_text(body.get('notes'),'备注',1000),'item_name_snapshot':item['name'],'unit_snapshot':item['unit'],
                'is_reversed':False,'reversal_of_id':None})
            audit(conn,user,'consumable.'+movement_type,'consumable_movements',movement['id'],{'item_id':key,'quantity':str(quantity),'computer_id':computer and computer['id']})
            return out({'movement':dict(movement),'current_stock':str(_current_stock(conn,key))},201)

    @app.post('/api/consumables/{key}/movements/{movement_id}/reverse')
    def reverse_movement(request:Request,key:str,movement_id:str,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);item=row(conn,'consumable_items',key)
            if not item:fail('耗材品类不存在',404)
            original=row(conn,'consumable_movements',movement_id)
            if not original or original['item_id']!=key:fail('出入库流水不存在',404)
            if original['movement_type'] not in MOVEMENT_TYPES:fail('返库或撤销流水不能再次操作',409)
            require(conn,user,'consumable.receive' if original['movement_type']=='inbound' else 'consumable.issue')
            if body.get('version')!=item['version']:fail('库存已发生变化，请刷新后重试',409)
            reason=_text(body.get('reason'),'操作原因',500,True)
            if original['movement_type']=='inbound' and _current_stock(conn,key)<original['quantity']:
                fail('当前库存不足以撤销该笔入库，请先处理已出库数量',409)
            now=utcnow();movements=T['consumable_movements']
            changed=conn.execute(movements.update().where(movements.c.id==movement_id,movements.c.is_reversed==False).values(is_reversed=True)).rowcount
            if changed!=1:fail('该流水已完成返库或撤销，请勿重复操作',409)
            if conn.execute(T['consumable_items'].update().where(T['consumable_items'].c.id==key,T['consumable_items'].c.version==item['version']).values(
                version=item['version']+1,updated_at=now,updated_by_user_id=user['id'])).rowcount!=1:fail('库存已发生变化，请刷新后重试',409)
            reverse_type='inbound_reversal' if original['movement_type']=='inbound' else 'outbound_return'
            reversal=insert_row(conn,'consumable_movements',{'actor_user_id':user['id'],'item_id':key,'movement_type':reverse_type,
                'quantity':original['quantity'],'occurred_on':date.today(),'unit_cost':original['unit_cost'],'supplier':original['supplier'],
                'reference_no':None,'computer_id':original['computer_id'],'department_id':original['department_id'],'user_id':original['user_id'],
                'recipient_text':original['recipient_text'],'purpose':original['purpose'],'notes':reason,
                'item_name_snapshot':original['item_name_snapshot'],'unit_snapshot':original['unit_snapshot'],
                'is_reversed':False,'reversal_of_id':movement_id})
            audit(conn,user,'consumable.'+reverse_type,'consumable_movements',reversal['id'],
                {'item_id':key,'original_movement_id':movement_id,'quantity':str(original['quantity'])},reason=reason)
            return out({'movement':dict(reversal),'current_stock':str(_current_stock(conn,key))},201)

    @app.get('/api/consumables/{key}/movements')
    def movements(request:Request,key:str,page:int=1,page_size:int=10,movement_type:str=''):
        if page_size not in (10,20,50):fail('每页条数仅支持 10、20、50')
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'consumable.view');item=row(conn,'consumable_items',key)
            if not item:fail('耗材不存在',404)
            movement=T['consumable_movements'];users=T['users'];departments=T['departments'];computers=T['computer_assets'];actors=T['users'].alias('actors')
            query=sa.select(movement,users.c.display_name.label('user_name'),departments.c.name.label('department_name'),computers.c.asset_code.label('computer_asset_code'),actors.c.display_name.label('actor_name')).select_from(
                movement.outerjoin(users,users.c.id==movement.c.user_id).outerjoin(departments,departments.c.id==movement.c.department_id).outerjoin(computers,computers.c.id==movement.c.computer_id).join(actors,actors.c.id==movement.c.actor_user_id)).where(movement.c.item_id==key)
            if movement_type:
                if movement_type not in ALL_MOVEMENT_TYPES:fail('流水类型无效')
                query=query.where(movement.c.movement_type==movement_type)
            total=conn.execute(sa.select(sa.func.count()).select_from(query.subquery())).scalar_one();page=max(1,page)
            values=conn.execute(query.order_by(movement.c.occurred_on.desc(),movement.c.created_at.desc()).offset((page-1)*page_size).limit(page_size)).mappings().all()
            return out({'item':dict(item),'items':[dict(v) for v in values],'total':total,'page':page,'page_size':page_size,'current_stock':str(_current_stock(conn,key))})
