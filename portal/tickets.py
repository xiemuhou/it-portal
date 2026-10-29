"""Transactional tickets. Claim/transfer/close use the parent version as a mutex."""
from datetime import datetime, timedelta, timezone
import json
import re
import sqlalchemy as sa

from .database import TABLES as T, insert_row, row, utcnow, uid
from .security import fail, require, allow, audit, digest


def text(value, label, limit=20000, required=False):
    if value is None:value=''
    if not isinstance(value,str) or len(value.encode('utf-16-le'))//2>limit or '\x00' in value:fail(label+'格式或长度无效')
    value=value.strip()
    if required and not value:fail('请填写'+label)
    return value


def time_value(value):
    try:
        result=datetime.fromisoformat(value.replace('Z','+00:00'))
        if result.tzinfo is None:fail('时间必须带时区')
        result=result.astimezone(timezone.utc).replace(tzinfo=None)
        return result.replace(microsecond=result.microsecond//1000*1000)
    except (ValueError,AttributeError,TypeError):fail('时间格式无效')


def millis(end,start):
    return (end-start)//timedelta(milliseconds=1)


def completion_time(body, earliest):
    completed=time_value(body.get('completed_at'))
    if completed<=earliest:fail('实际结束时间须晚于工单提交时间')
    return completed


def recalculate_segments(conn,cycle_id,completed):
    """Clip credited handling time to the actual completion, without negative durations.

    Claim/transfer event timestamps remain the authoritative operation history.
    Recompute every segment so a later correction can restore previously clipped time.
    """
    table=T['ticket_handling_segments']
    items=conn.execute(sa.select(table).where(table.c.cycle_id==cycle_id).order_by(table.c.segment_no)).mappings().all()
    total=0
    for i,s in enumerate(items):
        end=min(completed,items[i+1]['started_at']) if i+1<len(items) else completed
        end=max(s['started_at'],end)
        duration=millis(end,s['started_at']);total+=duration
        conn.execute(table.update().where(table.c.id==s['id']).values(ended_at=end,duration_ms=duration))
    return total


def ticket(conn,key,user,permission='ticket.view'):
    result=row(conn,'tickets',key)
    if not result:fail('工单不存在',404)
    require(conn,user,permission,result)
    return dict(result)


def update_parent(conn,old,values,version,user):
    if not isinstance(version,int) or isinstance(version,bool) or version!=old['version']:fail('工单已变化，请刷新后重试',409)
    t=T['tickets']
    result=conn.execute(t.update().where(t.c.id==old['id'],t.c.version==version).values(**values,version=version+1,updated_at=utcnow(),updated_by_user_id=user['id']))
    if result.rowcount!=1:fail('其他人刚刚修改了工单，请刷新',409)


def event(conn,old,cycle,user,kind,body=None,when=None,audience='requester',after=None,previous=None,new=None):
    return insert_row(conn,'ticket_events', {'ticket_id':old['id'],'cycle_id':cycle['id'] if cycle else None,
        'event_type':kind,'actor_user_id':user['id'],'actor_name_snapshot':user['display_name'],
        'audience':audience,'body':body,'from_status':old['status'],'to_status':after or old['status'],
        'previous_assignee_id':previous,'next_assignee_id':new,'occurred_at':when or utcnow()},user['id'])


def notify(conn,ticket_data,ev,title,user):
    ids={ticket_data.get('requester_user_id'),ticket_data.get('assignee_user_id')}-{None,user['id']}
    for target in ids:
        insert_row(conn,'notifications',{'recipient_user_id':target,'event_key':ev['id'],'ticket_id':ticket_data['id'],
            'title':title,'message_text':ticket_data['ticket_number']},user['id'])


def create(conn,user,body,key):
    require(conn,user,'ticket.create')
    description=text(body.get('description'),'问题描述',required=True)
    title=text(body.get('title'),'标题',200) or description.splitlines()[0][:120]
    if not isinstance(key,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,128}',key):fail('提交缺少有效幂等键')
    canonical=json.dumps({'description':description,'title':title,'site_id':body.get('site_id'),'location_text':body.get('location_text'),'contact':body.get('contact')},ensure_ascii=False,sort_keys=True)
    keys=T['idempotency_keys']
    previous=conn.execute(sa.select(keys).where(keys.c.actor_user_id==user['id'],keys.c.operation_code=='ticket.create',keys.c.key_hash==digest(key))).mappings().first()
    if previous:
        if previous['request_hash']!=digest(canonical):fail('相同提交标识的内容不同，请重新提交',409)
        return dict(ticket(conn,previous['result_object_id'],user))
    site_id=body.get('site_id') or None
    if site_id:
        site=row(conn,'sites',site_id)
        if not site or not site['is_enabled'] or site['is_archived']:fail('区域不存在或已停用')
    department=row(conn,'departments',user['department_id'])
    now=utcnow()
    result=insert_row(conn,'tickets',{'ticket_number':'IT'+now.strftime('%Y%m%d')+'-'+uid().replace('-','')[-8:].upper(),
        'origin':'portal','requester_user_id':user['id'],'requester_name_snapshot':user['display_name'],
        'department_name_snapshot':department['name'],'contact_snapshot':text(body.get('contact') or user.get('phone'),'联系方式',512) or None,
        'title':title,'description':description,'site_id':site_id,'location_text':text(body.get('location_text'),'位置',256) or None,
        'impact_scope':'unknown','status':'pending','current_cycle_no':1,'submitted_at':now},user['id'])
    cycle=insert_row(conn,'ticket_cycles',{'ticket_id':result['id'],'cycle_no':1,'opened_at':now},user['id'])
    ev=event(conn,result,cycle,user,'created',when=now)
    insert_row(conn,'idempotency_keys',{'actor_user_id':user['id'],'operation_code':'ticket.create','key_hash':digest(key),
        'request_hash':digest(canonical),'result_object_id':result['id'],'result_status':201,'expires_at':now+timedelta(days=7)},user['id'])
    audit(conn,user,'ticket.create','tickets',result['id'])
    return result


def action(conn,user,key,body):
    kind=body.get('action')
    if kind not in ('claim','assign','transfer','close','cancel','reopen','correct'):fail('不支持的工单操作')
    old=ticket(conn,key,user,'ticket.'+kind)
    cycles=T['ticket_cycles']; segments=T['ticket_handling_segments']
    cycle=dict(conn.execute(sa.select(cycles).where(cycles.c.ticket_id==key,cycles.c.cycle_no==old['current_cycle_no'])).mappings().one())
    now=utcnow(); values={}; reason=text(body.get('reason'),'说明',2000)
    current=conn.execute(sa.select(segments).where(segments.c.cycle_id==cycle['id'],segments.c.ended_at.is_(None))).mappings().first()
    if kind=='claim':
        if old['status']!='pending' or old['assignee_user_id'] not in (None,user['id']):fail('工单不在可接单状态或已分配给他人',409)
        values={'status':'in_progress','assignee_user_id':user['id'],'first_started_at':old['first_started_at'] or now}
    elif kind in ('assign','transfer'):
        expected='pending' if kind=='assign' else 'in_progress'
        if old['status']!=expected:fail('工单当前状态不支持此操作',409)
        target=row(conn,'users',body.get('assignee_user_id'))
        if not target or target['account_state']!='active' or target['is_archived'] or not allow(conn,target,'ticket.claim',old):fail('请选择具有处理权限的有效同事')
        if target['id']==old['assignee_user_id']:fail('新处理人不能与原处理人相同')
        values={'assignee_user_id':target['id']}
    elif kind=='close':
        if old['status']!='in_progress' or not current:fail('只有已接单的工单可以关闭',409)
        category=row(conn,'ticket_categories',body.get('category_id'))
        if not category or not category['is_enabled'] or category['is_archived']:fail('请选择有效问题分类')
        completed=completion_time(body,old['submitted_at'])
        values={'status':'closed','category_id':category['id'],'completed_at':completed,'closed_at':now}
    elif kind=='cancel':
        if old['status'] not in ('pending','in_progress'):fail('当前状态不能取消',409)
        if old['status']=='in_progress' and not allow(conn,user,'ticket.close',old):fail('处理中的工单由负责 IT 或管理员取消',403)
        if not reason:fail('请填写取消原因')
        values={'status':'cancelled','cancelled_at':now,'terminal_reason':reason}
    elif kind=='reopen':
        if old['status']!='closed':fail('仅已关闭工单可重开',409)
        values={'status':'pending','current_cycle_no':old['current_cycle_no']+1,'assignee_user_id':None,'completed_at':None,'closed_at':None,'cancelled_at':None}
    elif kind=='correct':
        if old['status']!='closed' or not reason:fail('只可纠正已关闭工单，且必须填写原因')
        category=row(conn,'ticket_categories',body.get('category_id'))
        last=conn.execute(sa.select(segments).where(segments.c.cycle_id==cycle['id']).order_by(segments.c.segment_no.desc()).limit(1)).mappings().first()
        if not category or not category['is_enabled'] or category['is_archived'] or not last:fail('分类或处理时间分段无效')
        completed=completion_time(body,old['submitted_at'])
        values={'category_id':category['id'],'completed_at':completed}
    update_parent(conn,old,values,body.get('version'),user)
    ev=event(conn,old,cycle,user,{'claim':'claimed','assign':'assigned','transfer':'transferred','close':'closed','cancel':'cancelled','reopen':'reopened','correct':'time_corrected'}[kind],reason or None,now,
             after=values.get('status'),previous=old['assignee_user_id'],new=values.get('assignee_user_id',old['assignee_user_id']))
    if kind=='claim':
        conn.execute(cycles.update().where(cycles.c.id==cycle['id']).values(started_at=now))
        insert_row(conn,'ticket_handling_segments',{'ticket_id':key,'cycle_id':cycle['id'],'segment_no':1,'handler_user_id':user['id'],'handler_name_snapshot':user['display_name'],'started_at':now},user['id'])
    elif kind=='transfer':
        if not current:fail('工单处理区间不完整',409)
        conn.execute(segments.update().where(segments.c.id==current['id']).values(ended_at=now,duration_ms=millis(now,current['started_at']),end_reason='transfer',end_event_id=ev['id']))
        insert_row(conn,'ticket_handling_segments',{'ticket_id':key,'cycle_id':cycle['id'],'segment_no':current['segment_no']+1,'handler_user_id':target['id'],'handler_name_snapshot':target['display_name'],'started_at':now},user['id'])
    elif kind in ('close','cancel'):
        end=values.get('completed_at',now)
        if current:
            segment_end=max(current['started_at'],end)
            conn.execute(segments.update().where(segments.c.id==current['id']).values(ended_at=segment_end,duration_ms=millis(segment_end,current['started_at']),end_reason='closed' if kind=='close' else 'cancelled',end_event_id=ev['id']))
        close_values={'ended_at':end,'end_kind':'closed' if kind=='close' else 'cancelled'}
        if kind=='close':
            total=recalculate_segments(conn,cycle['id'],end)
            close_values.update(completed_at=end,closed_at=now,duration_ms=total,category_id=category['id'],final_handler_id=current['handler_user_id'],
                final_handler_name_snapshot=current['handler_name_snapshot'],handling_summary=text(body.get('handling_summary'),'处理说明') or None)
        conn.execute(cycles.update().where(cycles.c.id==cycle['id']).values(**close_values))
    elif kind=='reopen':
        insert_row(conn,'ticket_cycles',{'ticket_id':key,'cycle_no':values['current_cycle_no'],'opened_at':now},user['id'])
    elif kind=='correct':
        total=recalculate_segments(conn,cycle['id'],completed)
        conn.execute(cycles.update().where(cycles.c.id==cycle['id']).values(completed_at=completed,ended_at=completed,duration_ms=total,category_id=category['id']))
    result=dict(row(conn,'tickets',key))
    notify(conn,result,ev,'工单'+{'claim':'已接单','assign':'已分配','transfer':'已转派','close':'已关闭','cancel':'已取消','reopen':'已重开','correct':'已纠正'}[kind],user)
    audit(conn,user,'ticket.'+kind,'tickets',key,{'before':{k:old.get(k) for k in values},'after':values},reason or None)
    return result


def comment(conn,user,key,body):
    internal=body.get('internal',False)
    old=ticket(conn,key,user,'ticket.internal_note' if internal else 'ticket.comment')
    content=text(body.get('body'),'留言',required=True)
    ev=event(conn,old,None,user,'internal_note' if internal else 'comment',content,audience='internal' if internal else 'requester')
    if not internal:notify(conn,old,ev,'工单有新留言',user)
    audit(conn,user,'ticket.comment','tickets',key)
    return ev


def details(conn,user,key):
    result=ticket(conn,key,user)
    events=T['ticket_events']; cycles=T['ticket_cycles']; seg=T['ticket_handling_segments']
    query=sa.select(events).where(events.c.ticket_id==key)
    if not allow(conn,user,'ticket.internal_note',result):query=query.where(events.c.audience=='requester')
    result['events']=[dict(v) for v in conn.execute(query.order_by(events.c.created_at,events.c.id)).mappings()]
    result['cycles']=[dict(v) for v in conn.execute(sa.select(cycles).where(cycles.c.ticket_id==key).order_by(cycles.c.cycle_no)).mappings()]
    result['segments']=[dict(v) for v in conn.execute(sa.select(seg).where(seg.c.ticket_id==key).order_by(seg.c.cycle_id,seg.c.segment_no)).mappings()] if allow(conn,user,'report.view',result) else []
    result['actions']=[a for a in ('claim','assign','transfer','close','cancel','reopen','correct','comment','internal_note','delete') if allow(conn,user,'ticket.'+a,result)]
    return result
