"""Behavioral tests for the new application; isolated databases, no legacy sources."""
from contextlib import ExitStack
from datetime import datetime,timedelta
from io import BytesIO
from pathlib import Path
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

import sqlalchemy as sa
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy.schema import CreateTable,CreateIndex
from sqlalchemy.dialects import mssql,mysql

from portal.app import make_app
from portal.database import TABLES as T,metadata,utcnow,uid,insert_row,database_url
from portal import organization,ldap_sync
from portal.security import audit


class BusinessTests(unittest.TestCase):
    def test_mysql_root_unix_socket_url(self):
        url=database_url({'database':{'engine':'mysql','host':'','port':3306,'name':'itportal',
            'username':'root','password':'','unix_socket':'/var/run/mysqld/mysqld.sock'}},False)
        self.assertEqual(url.drivername,'mysql+pymysql')
        self.assertIsNone(url.host)
        self.assertIsNone(url.port)
        self.assertEqual(url.query['unix_socket'],'/var/run/mysqld/mysqld.sock')

    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.temp=self.stack.enter_context(tempfile.TemporaryDirectory())
        self.stack.enter_context(patch.dict(os.environ,{'IT_PORTAL_BOOTSTRAP_PASSWORD':'test-admin-2026'}))
        self.app=make_app('sqlite:///'+Path(self.temp,'test.db').as_posix(),self.temp,True)
        self.client=self.stack.enter_context(TestClient(self.app))
        self.admin=self.login('admin','test-admin-2026')
        look=self.client.get('/api/lookups').json();self.department=look['departments'][0]['id'];self.categories=look['ticket_categories']
        roles=self.client.get('/api/roles').json()['items'];self.roles={r['code']:r['id'] for r in roles}
        self.employee=self.add_user('employee-a','employee')
        self.other=self.add_user('employee-b','employee')
        self.it_a=self.add_user('it-a','it')
        self.it_b=self.add_user('it-b','it')

    def login(self,account,password='test-user-2026'):
        r=self.client.post('/api/auth/login',json={'login_name':account,'password':password})
        self.assertEqual(r.status_code,200,r.text)
        self.client.headers['X-CSRF-Token']=r.json()['user']['csrf']
        self.client.headers['X-Portal-Activity']='1'
        return r.json()['user']

    def add_user(self,login,role):
        r=self.client.post('/api/users',json={'login_name':login,'display_name':login,'department_id':self.department,
            'password':'test-user-2026','role_ids':[self.roles[role]]})
        self.assertEqual(r.status_code,201,r.text)
        return r.json()['id']

    def create_ticket(self,description='测试网络连接问题',key=None):
        r=self.client.post('/api/tickets',json={'description':description},headers={'Idempotency-Key':key or str(uuid.uuid4())})
        self.assertEqual(r.status_code,201,r.text);return r.json()

    def action(self,t,action,**kwargs):
        return self.client.post('/api/tickets/'+t['id']+'/actions',json={'action':action,'version':t['version'],**kwargs})

    def test_login_password_and_revoked_session(self):
        self.login('employee-a')
        bad=self.client.post('/api/auth/password',json={'old_password':'test-user-2026','password':'1234567'})
        self.assertEqual(bad.status_code,422)
        good=self.client.post('/api/auth/password',json={'old_password':'test-user-2026','password':'12345678'})
        self.assertEqual(good.status_code,200)
        self.assertIsNone(self.client.get('/api/session').json()['user'])
        self.login('employee-a','12345678')

    def test_ehr_organization_sync_first_and_incremental_rules(self):
        first={'departments':[{'parent_code':'','department_code':'D001','department_name':'研发部'}],
            'employees':[{'employee_code':'00000001','full_name':'张三','department_code':'D001','dimission_date':None}],
            'jobs':[{'employee_code':'00000001','department_code':'D001','job_title':'工程师'}]}
        before=self.client.get('/api/organization/sync-status').json().get('state') or {}
        with patch.object(organization,'read_ehr',return_value=first):
            r=self.client.post('/api/organization/sync-ehr',json={})
            self.assertEqual(r.status_code,202,r.text)
            for _ in range(50):
                state=self.client.get('/api/organization/sync-status').json().get('state') or {}
                if state.get('last_attempt_at')!=before.get('last_attempt_at') and state.get('last_status') not in (None,'running'):break
                time.sleep(.1)
        self.assertTrue(self.client.get('/api/organization/sync-status').json()['state']['first_success_at'])
        self.login('00000001','00000001')
        self.login('admin','test-admin-2026')
        second={'departments':first['departments'],
            'employees':[first['employees'][0],{'employee_code':'00000002','full_name':'李四','department_code':'D001','dimission_date':None}],
            'jobs':first['jobs']+[{'employee_code':'00000002','department_code':'D001','job_title':'主管'}]}
        before=self.client.get('/api/organization/sync-status').json().get('state') or {}
        with patch.object(organization,'read_ehr',return_value=second):
            r=self.client.post('/api/organization/sync-ehr',json={})
            self.assertEqual(r.status_code,202,r.text)
            for _ in range(50):
                state=self.client.get('/api/organization/sync-status').json().get('state',{})
                if state.get('last_attempt_at')!=before.get('last_attempt_at') and state.get('last_status') not in (None,'running'):break
                time.sleep(.1)
        with self.app.state.engine.begin() as conn:
            user=conn.execute(sa.select(T['users']).where(T['users'].c.login_name=='00000002')).mappings().one()
            self.assertEqual(user['account_state'],'disabled')
            assignment=conn.execute(sa.select(sa.func.count()).select_from(T['user_job_assignments']).where(T['user_job_assignments'].c.user_id==user['id'])).scalar_one()
            self.assertEqual(assignment,1)

    def test_user_list_exposes_top_department_roles_and_department_filter(self):
        root=self.client.post('/api/data/departments',json={'code':'ORG-ROOT','name':'制造中心','is_enabled':True})
        self.assertEqual(root.status_code,201,root.text);root=root.json()
        child=self.client.post('/api/data/departments',json={'code':'ORG-CHILD','name':'生产一部','parent_id':root['id'],'is_enabled':True})
        self.assertEqual(child.status_code,201,child.text);child=child.json()
        created=self.client.post('/api/users',json={'login_name':'department-filter-user','display_name':'部门筛选人员','department_id':child['id'],
            'password':'test-user-2026','role_ids':[self.roles['employee']]})
        self.assertEqual(created.status_code,201,created.text);created=created.json()
        result=self.client.get('/api/users',params={'department_id':root['id'],'q':'部门筛选人员'}).json()
        self.assertEqual(result['total'],1);item=result['items'][0]
        self.assertEqual(item['department_name'],'生产一部');self.assertEqual(item['top_department_name'],'制造中心')
        self.assertIn(self.roles['employee'],item['role_ids'])
        empty_result=self.client.get('/api/users',params={'department_id':self.department,'q':'部门筛选人员'}).json()
        self.assertEqual(empty_result['total'],0)
        with self.app.state.engine.begin() as conn:
            organization._link(conn,'user','FILTER-EMPLOYEE',created['id'],utcnow())
        ehr_active=self.client.get('/api/users',params={'q':'部门筛选人员','account_state':'active','source_type':'ehr'}).json()
        self.assertEqual(ehr_active['total'],1);self.assertEqual(ehr_active['items'][0]['source_type'],'ehr')
        self.assertEqual(self.client.get('/api/users',params={'q':'部门筛选人员','source_type':'manual'}).json()['total'],0)
        disabled=self.client.put('/api/users/'+created['id'],json={'version':ehr_active['items'][0]['version'],'account_state':'disabled'})
        self.assertEqual(disabled.status_code,200,disabled.text)
        ehr_disabled=self.client.get('/api/users',params={'q':'部门筛选人员','account_state':'disabled','source_type':'ehr'}).json()
        self.assertEqual(ehr_disabled['total'],1);self.assertEqual(ehr_disabled['items'][0]['account_state'],'disabled')
        self.assertEqual(self.client.get('/api/users',params={'account_state':'invalid'}).status_code,422)
        self.assertEqual(self.client.get('/api/users',params={'source_type':'unknown'}).status_code,422)

    def test_ldap_read_only_sync_updates_directory_without_enabling_new_users(self):
        self.app.state.config['ldap']={'enabled':True,'host':'ad.example.local','base_dn':'DC=example,DC=local',
            'bind_dn':'EXAMPLE\\svc-ldap','password':'test-secret','use_ssl':True,'validate_certificate':True}
        source={'users':[
            {'external_key':'guid-a','login_name':'employee-a','display_name':'域用户甲','employee_no':'00000001',
                'department_name':'域技术部','job_title':'域工程师','email':'a@example.local','phone':'1001','disabled':False},
            {'external_key':'guid-b','login_name':'employee-b','display_name':'域用户乙','employee_no':'00000002',
                'department_name':'域技术部','job_title':'域工程师','email':None,'phone':None,'disabled':True},
            {'external_key':'guid-new','login_name':'domain-new','display_name':'域新增用户','employee_no':'00000003',
                'department_name':'域技术部','job_title':'域主管','email':'new@example.local','phone':'1003','disabled':False},
        ]}
        with patch.object(ldap_sync,'read_ldap',return_value=source):
            tested=self.client.post('/api/organization/test-ldap',json={})
            self.assertEqual(tested.status_code,200,tested.text);self.assertEqual(tested.json()['sample_count'],3)
            started=self.client.post('/api/organization/sync-ldap',json={})
            self.assertEqual(started.status_code,202,started.text)
            for _ in range(60):
                status=self.client.get('/api/organization/ldap-status').json().get('state') or {}
                if status.get('last_status') not in (None,'running'):break
                time.sleep(.1)
        self.assertEqual(status['last_status'],'success',status)
        users=self.client.get('/api/users',params={'source_type':'ldap','page_size':50}).json()
        self.assertEqual(users['total'],3);by_login={v['login_name']:v for v in users['items']}
        self.assertEqual(by_login['employee-a']['display_name'],'域用户甲');self.assertEqual(by_login['employee-a']['account_state'],'active')
        self.assertEqual(by_login['employee-b']['account_state'],'disabled')
        self.assertEqual(by_login['domain-new']['account_state'],'disabled')
        self.assertEqual(by_login['domain-new']['department_name'],'域技术部')
        positions=self.client.get('/api/organization/positions',params={'page_size':50}).json()['items']
        self.assertEqual(next(v for v in positions if v['title']=='域主管')['source_type'],'ldap')
        departments=self.client.get('/api/data/departments',params={'page_size':50}).json()['items']
        self.assertEqual(next(v for v in departments if v['name']=='域技术部')['source_type'],'ldap')
        self.login('employee-a')

    def test_session_idle_and_heartbeat(self):
        self.login('employee-a')
        with self.app.state.engine.begin() as conn:
            s=T['user_sessions'];conn.execute(s.update().where(s.c.user_id==self.employee).values(idle_expires_at=utcnow()-timedelta(seconds=1)))
        self.assertIsNone(self.client.get('/api/session').json()['user'])
        self.assertEqual(self.client.get('/api/tickets').status_code,401)

    def test_csrf_and_login_origin(self):
        self.assertEqual(self.client.post('/api/users',json={},headers={'X-CSRF-Token':'invalid'}).status_code,403)
        self.assertEqual(self.client.post('/api/auth/login',json={},headers={'Origin':'https://evil.example'}).status_code,403)

    def test_employee_ownership_and_it_visibility(self):
        self.login('employee-a');ticket=self.create_ticket()
        self.login('employee-b')
        self.assertEqual(self.client.get('/api/tickets/'+ticket['id']).status_code,403)
        self.assertEqual(self.client.get('/api/tickets').json()['total'],0)
        self.assertEqual(self.client.get('/api/data/resources').status_code,403)
        self.login('it-a');self.assertEqual(self.client.get('/api/tickets').json()['total'],1)

    def test_submission_idempotency(self):
        self.login('employee-a');key=str(uuid.uuid4());one=self.create_ticket(key=key);two=self.create_ticket(key=key)
        self.assertEqual(one['id'],two['id'])
        r=self.client.post('/api/tickets',json={'description':'different'},headers={'Idempotency-Key':key})
        self.assertEqual(r.status_code,409)

    def test_claim_transfer_close_reopen_accounting(self):
        self.login('employee-a');t=self.create_ticket();self.login('it-a');start=utcnow()-timedelta(hours=2)
        with self.app.state.engine.begin() as conn:conn.execute(T['tickets'].update().where(T['tickets'].c.id==t['id']).values(submitted_at=start-timedelta(minutes=5)))
        with patch('portal.tickets.utcnow',return_value=start):r=self.action(t,'claim')
        self.assertEqual(r.status_code,200,r.text);claimed=r.json()
        self.assertEqual(self.action(t,'claim').status_code,409)
        transfer=start+timedelta(minutes=20)
        with patch('portal.tickets.utcnow',return_value=transfer):r=self.action(claimed,'transfer',assignee_user_id=self.it_b)
        self.assertEqual(r.status_code,200,r.text);transferred=r.json()
        self.assertEqual(self.action(transferred,'close',category_id=self.categories[0]['id'],completed_at=(transfer+timedelta(minutes=30)).isoformat()+'Z').status_code,403)
        self.login('it-b');end=start+timedelta(minutes=50)
        bad=self.action(transferred,'close',category_id=self.categories[0]['id'],completed_at=(start-timedelta(minutes=6)).isoformat()+'Z')
        self.assertEqual(bad.status_code,422)
        r=self.action(transferred,'close',category_id=self.categories[0]['id'],completed_at=end.isoformat()+'Z')
        self.assertEqual(r.status_code,200,r.text);closed=r.json()
        detail=self.client.get('/api/tickets/'+t['id']).json()
        self.assertEqual(detail['cycles'][0]['duration_ms'],3000000)
        self.assertEqual([v['duration_ms'] for v in detail['segments']],[1200000,1800000])
        report=self.client.get('/api/reports/tickets').json();self.assertEqual(report['closed_cycles'],1)
        people={v['name']:v for v in report['handlers']};self.assertEqual(people['it-a']['closed_count'],0);self.assertEqual(people['it-b']['closed_count'],1)
        self.login('employee-a')
        self.assertEqual(self.client.post('/api/tickets/'+t['id']+'/events',json={'body':'还需要补充帮助'}).status_code,201)
        self.assertEqual(self.client.get('/api/tickets/'+t['id']).json()['status'],'closed')
        r=self.action(closed,'reopen');self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['current_cycle_no'],2)
        self.assertEqual(self.client.get('/api/tickets/'+t['id']).json()['cycles'][1]['started_at'],None)

    def test_ticket_report_defaults_to_recent_30_calendar_days(self):
        self.login('employee-a');ticket=self.create_ticket();self.login('it-a')
        claimed=self.action(ticket,'claim').json()
        closed=self.action(claimed,'close',category_id=self.categories[0]['id'],completed_at=(utcnow()+timedelta(seconds=1)).isoformat()+'Z')
        self.assertEqual(closed.status_code,200,closed.text)
        old_completed=utcnow()-timedelta(days=40)
        with self.app.state.engine.begin() as conn:
            conn.execute(T['ticket_cycles'].update().where(T['ticket_cycles'].c.ticket_id==ticket['id']).values(completed_at=old_completed,ended_at=old_completed))
        default=self.client.get('/api/reports/tickets').json()
        self.assertEqual(default['closed_cycles'],0)
        self.assertEqual((datetime.fromisoformat(default['end']).date()-datetime.fromisoformat(default['start']).date()).days,29)
        expanded=self.client.get('/api/reports/tickets',params={'start':(old_completed.date()-timedelta(days=1)).isoformat(),'end':utcnow().date().isoformat()}).json()
        self.assertEqual(expanded['closed_cycles'],1)

    def test_notification_unread_count_and_mark_read(self):
        self.login('employee-a');ticket=self.create_ticket()
        self.login('it-a');claimed=self.action(ticket,'claim');self.assertEqual(claimed.status_code,200,claimed.text)
        comment=self.client.post('/api/tickets/'+ticket['id']+'/events',json={'body':'处理进度更新'});self.assertEqual(comment.status_code,201,comment.text)
        self.login('employee-a')
        count=self.client.get('/api/notifications/unread-count');self.assertEqual(count.status_code,200,count.text);self.assertEqual(count.json()['unread_count'],2)
        items=self.client.get('/api/notifications').json();self.assertEqual(len(items),2);self.assertIsNone(items[0]['read_at'])
        marked=self.client.post('/api/notifications/'+items[0]['id']+'/read',json={});self.assertEqual(marked.status_code,200,marked.text);self.assertEqual(marked.json()['unread_count'],1)
        marked_all=self.client.post('/api/notifications/read-all',json={});self.assertEqual(marked_all.status_code,200,marked_all.text);self.assertEqual(marked_all.json()['updated_count'],1);self.assertEqual(marked_all.json()['unread_count'],0)
        self.assertEqual(self.client.get('/api/notifications/unread-count').json()['unread_count'],0)

    def test_completion_after_submission_clips_and_restores_all_segments(self):
        from datetime import timezone
        submitted=utcnow()-timedelta(hours=2)
        with patch('portal.tickets.utcnow',return_value=submitted):t=self.create_ticket()
        start=submitted+timedelta(minutes=20)
        with patch('portal.tickets.utcnow',return_value=start):claimed=self.action(t,'claim').json()
        transfer=start+timedelta(minutes=20)
        with patch('portal.tickets.utcnow',return_value=transfer):
            transferred=self.action(claimed,'transfer',assignee_user_id=self.it_b).json()
        category=self.categories[0]['id']
        for invalid in (submitted,submitted-timedelta(milliseconds=1)):
            r=self.action(transferred,'close',category_id=category,completed_at=invalid.isoformat()+'Z')
            self.assertEqual(r.status_code,422,r.text);self.assertIn('提交时间',r.text)
        end=start+timedelta(minutes=10)
        local=end.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8)))
        r=self.action(transferred,'close',category_id=category,completed_at=local.isoformat())
        self.assertEqual(r.status_code,200,r.text);closed=r.json()
        detail=self.client.get('/api/tickets/'+t['id']).json()
        self.assertEqual([s['duration_ms'] for s in detail['segments']],[600000,0])
        before_claim=submitted+timedelta(minutes=1)
        r=self.action(closed,'correct',category_id=category,reason='补录实际结束时间',completed_at=before_claim.isoformat()+'Z')
        self.assertEqual(r.status_code,200,r.text);closed=r.json()
        detail=self.client.get('/api/tickets/'+t['id']).json()
        self.assertEqual(detail['cycles'][0]['duration_ms'],0)
        self.assertTrue(all(s['ended_at']>=s['started_at'] for s in detail['segments']))
        future=utcnow()+timedelta(hours=1)
        r=self.action(closed,'correct',category_id=category,reason='验证仅提交时间限制',completed_at=future.isoformat()+'Z')
        self.assertEqual(r.status_code,200,r.text)
        detail=self.client.get('/api/tickets/'+t['id']).json()
        self.assertEqual(detail['segments'][0]['duration_ms'],1200000)
        self.assertEqual(detail['cycles'][0]['duration_ms'],sum(s['duration_ms'] for s in detail['segments']))
        self.assertEqual(len([e for e in detail['events'] if e['event_type']=='transferred']),1)

    def test_category_delete_permissions_references_and_simplified_metadata(self):
        specs=self.client.get('/api/catalog').json()['modules']
        self.assertNotIn('site_aliases',[s['table'] for s in specs])
        self.assertTrue({'locations','vendors','dictionary_items','improvement_projects'}.isdisjoint(s['table'] for s in specs))
        self.assertTrue(all(f['ui_hidden'] for s in specs for f in s['fields'] if f['name']=='sort_order'))
        self.assertEqual(self.client.get('/api/data/locations').status_code,404)
        cat=self.client.post('/api/data/ticket_categories',json={'name':'待删除分类'}).json()
        payload={'version':cat['version'],'confirm':cat['id'],'reason':'清理测试分类'}
        self.login('it-a')
        self.assertEqual(self.client.request('DELETE','/api/data/ticket_categories/'+cat['id'],json=payload).status_code,403)
        self.login('admin','test-admin-2026')
        r=self.client.request('DELETE','/api/data/ticket_categories/'+cat['id'],json=payload)
        self.assertEqual(r.status_code,200,r.text)
        used=self.categories[0];t=self.create_ticket();claimed=self.action(t,'claim').json()
        r=self.action(claimed,'close',category_id=used['id'],completed_at=(utcnow()+timedelta(seconds=1)).isoformat()+'Z')
        self.assertEqual(r.status_code,200,r.text)
        r=self.client.request('DELETE','/api/data/ticket_categories/'+used['id'],json={'version':1,'confirm':used['id'],'reason':'不能破坏历史'})
        self.assertEqual(r.status_code,409,r.text);self.assertIn('停用' if '停用' in r.text else '启用',r.text)

    def test_hidden_generated_codes_and_area_edit_preserves_identity(self):
        specs=self.client.get('/api/catalog').json()['modules'];site=next(v for v in specs if v['table']=='sites')
        self.assertEqual(site['title'],'区域')
        fields={f['name']:f for f in site['fields']}
        self.assertTrue(fields['code']['ui_hidden']);self.assertTrue(fields['site_type']['ui_hidden'])
        one=self.client.post('/api/data/sites',json={'name':'一区'});two=self.client.post('/api/data/sites',json={'name':'二区'})
        self.assertEqual(one.status_code,201,one.text);self.assertEqual(two.status_code,201,two.text)
        one=one.json();self.assertNotEqual(one['code'],two.json()['code']);self.assertEqual(one['site_type'],'other')
        edit=self.client.put('/api/data/sites/'+one['id'],json={'name':'区域一','version':one['version']})
        self.assertEqual(edit.status_code,200,edit.text);self.assertEqual(edit.json()['code'],one['code'])
        self.assertNotIn('import',site['actions']);self.assertNotIn('export',site['actions'])

    def test_pending_cannot_close_and_missing_category(self):
        t=self.create_ticket();self.assertEqual(self.action(t,'close',completed_at=utcnow().isoformat()+'Z',category_id=self.categories[0]['id']).status_code,409)
        claimed=self.action(t,'claim').json()
        self.assertEqual(self.action(claimed,'close',completed_at=utcnow().isoformat()+'Z').status_code,422)

    def test_internal_notes_and_attachment_permissions(self):
        self.login('employee-a');t=self.create_ticket();self.login('it-a')
        r=self.client.post('/api/tickets/'+t['id']+'/events',json={'body':'内部排查信息','internal':True});self.assertEqual(r.status_code,201)
        png=b'\x89PNG\r\n\x1a\n'+b'test-image'
        r=self.client.post('/api/tickets/'+t['id']+'/attachments',files={'file':('screen.png',png,'image/png')},data={'internal':'true'})
        self.assertEqual(r.status_code,201,r.text);attachment=r.json()['id']
        self.login('employee-a')
        detail=self.client.get('/api/tickets/'+t['id']).json()
        self.assertFalse(any(v['audience']=='internal' for v in detail['events']))
        self.assertEqual(self.client.get('/api/files/ticket/'+attachment).status_code,403)

    def test_no_last_admin_disable(self):
        users=self.client.get('/api/users?q=admin').json()['items'];admin=next(v for v in users if v['login_name']=='admin')
        r=self.client.put('/api/users/'+admin['id'],json={'version':admin['version'],'account_state':'disabled'})
        self.assertEqual(r.status_code,422)

    def test_per_operation_scope_does_not_cross_roles(self):
        t=self.create_ticket();self.login('employee-a');own=self.create_ticket();self.login('admin','test-admin-2026')
        role=self.client.post('/api/roles',json={'code':'view_all','name':'只读全量','permissions':[{'code':'ticket.view','scope':'all'}]})
        self.assertEqual(role.status_code,201,role.text)
        u=next(v for v in self.client.get('/api/users').json()['items'] if v['id']==self.employee)
        r=self.client.put('/api/users/'+self.employee,json={'version':u['version'],'role_ids':[self.roles['employee'],role.json()['id']]})
        self.assertEqual(r.status_code,200,r.text);self.login('employee-a')
        self.assertEqual(self.client.get('/api/tickets').json()['total'],2)
        self.assertEqual(self.client.put('/api/tickets/'+t['id'],json={'version':t['version'],'title':'bad','description':'bad'}).status_code,403)

    def test_announcements_only_published_and_unexpired(self):
        r=self.client.post('/api/data/announcements',json={'announcement_code':'notice-1','title':'维护提醒','body':'测试公告内容','publication_state':'draft'})
        self.assertEqual(r.status_code,201,r.text);a=r.json()
        self.assertEqual(self.client.get('/api/announcements').json()['total'],0)
        r=self.client.post('/api/data/announcements/'+a['id']+'/publish',json={'version':a['version'],'state':'published'})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.client.get('/api/announcements').json()['total'],1)
        t=T['announcements']
        with self.app.state.engine.begin() as conn:conn.execute(t.update().where(t.c.id==a['id']).values(expires_at=utcnow()-timedelta(seconds=1)))
        self.assertEqual(self.client.get('/api/announcements/'+a['id']).status_code,404)
        draft=self.client.post('/api/data/announcements',json={'title':'过期草稿','body':'测试','expires_at':(utcnow()-timedelta(minutes=1)).isoformat()+'Z'}).json()
        r=self.client.post('/api/data/announcements/'+draft['id']+'/publish',json={'version':draft['version'],'state':'published'})
        self.assertEqual(r.status_code,422,r.text);self.assertIn('截止时间',r.text)
        fixed=self.client.put('/api/data/announcements/'+draft['id'],json={'version':draft['version'],'expires_at':None}).json()
        r=self.client.post('/api/data/announcements/'+draft['id']+'/publish',json={'version':fixed['version'],'state':'published'})
        self.assertEqual(r.status_code,200,r.text)
        self.assertIn(draft['id'],[a['id'] for a in self.client.get('/api/public').json()['announcements']])
        self.assertEqual(self.client.get('/api/announcements/'+draft['id']).status_code,200)
        published_rows=self.client.get('/api/data/announcements',params={'status':'published'}).json()['items']
        self.assertTrue(published_rows);self.assertTrue(all(v['publication_state']=='published' and v['published_at'] for v in published_rows))
        self.assertEqual([v['published_at'] for v in published_rows],sorted([v['published_at'] for v in published_rows],reverse=True))
        announcement_spec=next(v for v in self.client.get('/api/catalog').json()['modules'] if v['table']=='announcements')
        self.assertTrue({'published_at','published_by_user_id'}.issubset({v['name'] for v in announcement_spec['fields']}))
        disposable=self.client.post('/api/data/announcements',json={'title':'待删除公告','body':'测试'}).json()
        draft_rows=self.client.get('/api/data/announcements',params={'status':'draft'}).json()['items']
        self.assertIn(disposable['id'],[v['id'] for v in draft_rows]);self.assertTrue(all(v['publication_state']=='draft' for v in draft_rows))
        deleted=self.client.request('DELETE','/api/data/announcements/'+disposable['id'],json={'version':disposable['version'],'confirm':disposable['id'],'reason':'测试删除公告'})
        self.assertEqual(deleted.status_code,200,deleted.text)

    def test_announcement_attachments_publisher_and_notifications(self):
        self.assertEqual(self.client.get('/api/import-templates/announcements').status_code,404)
        self.assertEqual(self.client.get('/api/exports/announcements').status_code,404)
        created=self.client.post('/api/data/announcements',json={'title':'带附件公告','body':'请阅读附件'});self.assertEqual(created.status_code,201,created.text);a=created.json()
        uploaded=self.client.post(f'/api/announcements/{a["id"]}/attachments',files=[('files',('说明.txt',b'notice attachment','text/plain'))])
        self.assertEqual(uploaded.status_code,201,uploaded.text);attachment=uploaded.json()['items'][0]
        published=self.client.post(f'/api/data/announcements/{a["id"]}/publish',json={'version':a['version'],'state':'published'})
        self.assertEqual(published.status_code,200,published.text);published=published.json()
        detail=self.client.get(f'/api/announcements/{a["id"]}');self.assertEqual(detail.status_code,200,detail.text)
        self.assertEqual(detail.json()['publisher_name'],'系统管理员');self.assertEqual(detail.json()['attachments'][0]['original_name'],'说明.txt')
        viewed=self.client.get(f'/api/files/announcement/{attachment["id"]}');self.assertEqual(viewed.content,b'notice attachment')
        self.assertTrue(viewed.headers['content-disposition'].startswith('inline;'))
        downloaded=self.client.get(f'/api/files/announcement/{attachment["id"]}?download=true');self.assertEqual(downloaded.content,b'notice attachment')
        self.assertTrue(downloaded.headers['content-disposition'].startswith('attachment;'))
        with self.app.state.engine.begin() as conn:
            notifications=list(conn.execute(sa.select(T['notifications']).where(T['notifications'].c.announcement_id==a['id'])).mappings())
            self.assertEqual(len(notifications),5);self.assertTrue(all(v['read_at'] is None for v in notifications))
        self.login('employee-a')
        message=next(v for v in self.client.get('/api/notifications').json() if v['announcement_id']==a['id'])
        self.assertEqual(message['title'],'新公告：带附件公告')
        self.login('admin','test-admin-2026')
        withdrawn=self.client.post(f'/api/data/announcements/{a["id"]}/publish',json={'version':published['version'],'state':'withdrawn'})
        self.assertEqual(withdrawn.status_code,200,withdrawn.text)
        self.assertEqual(self.client.get(f'/api/files/announcement/{attachment["id"]}').status_code,404)

    def test_quick_links_role_visibility_and_admin_management(self):
        general=self.client.post('/api/quick-links',json={'title':'办公系统','url':'10.10.1.20:8080','icon_text':'OA','description':'公司通用入口','link_category':'general','is_enabled':True,'sort_order':1})
        self.assertEqual(general.status_code,201,general.text);general=general.json();self.assertEqual(general['url'],'http://10.10.1.20:8080')
        internal=self.client.post('/api/quick-links',json={'title':'交换机管理','url':'https://10.10.1.1','icon_text':'NET','link_category':'it','is_enabled':True,'sort_order':1})
        self.assertEqual(internal.status_code,201,internal.text);internal=internal.json()
        self.login('employee-a');employee=self.client.get('/api/quick-links').json()
        self.assertFalse(employee['it_access']);self.assertFalse(employee['can_manage']);self.assertEqual([v['id'] for v in employee['items']],[general['id']])
        self.assertEqual(self.client.post('/api/quick-links',json={}).status_code,403)
        self.login('it-a');it_result=self.client.get('/api/quick-links').json()
        self.assertTrue(it_result['it_access']);self.assertFalse(it_result['can_manage']);self.assertEqual({v['id'] for v in it_result['items']},{general['id'],internal['id']})
        self.login('admin','test-admin-2026');updated=self.client.put('/api/quick-links/'+general['id'],json={**general,'title':'统一办公入口','version':general['version']})
        self.assertEqual(updated.status_code,200,updated.text);updated=updated.json();self.assertEqual(updated['title'],'统一办公入口')
        deleted=self.client.request('DELETE','/api/quick-links/'+internal['id'],json={'version':internal['version'],'reason':'测试删除'})
        self.assertEqual(deleted.status_code,200,deleted.text)


    def test_basic_data_import_export_removed(self):
        for name in ('sites','ticket_categories','knowledge_categories','service_catalog'):
            self.assertEqual(self.client.get('/api/import-templates/'+name).status_code,404)
            self.assertEqual(self.client.get('/api/exports/'+name).status_code,404)
            self.assertEqual(self.client.post('/api/imports/'+name,files={'file':('data.xlsx',b'not-used')}).status_code,404)

    def test_resource_transaction_and_version(self):
        site=self.client.get('/api/lookups').json()['sites'][0]['id']
        body={'resource':{'resource_code':'SW-001','name':'接入交换机','site_id':site},'details':{'device_type_code':'switch','model':'test'}}
        r=self.client.post('/api/resources/device',json=body);self.assertEqual(r.status_code,201,r.text);resource=r.json()['resource']
        full=self.client.get('/api/resources/'+resource['id']+'/full').json();self.assertEqual(full['details']['model'],'test')
        body={'resource':{'name':'更新交换机','version':resource['version']},'details':{'device_type_code':'switch','model':'new'}}
        r=self.client.put('/api/resources/'+resource['id']+'/full',json=body);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.client.put('/api/resources/'+resource['id']+'/full',json=body).status_code,409)
        bad={'resource':{'resource_code':'bad','name':'bad','site_id':site},'details':{'vlan_number':5000,'scope_id':'bad'}}
        self.assertEqual(self.client.post('/api/resources/vlan',json=bad).status_code,422)
        self.assertEqual(self.client.get('/api/data/resources').json()['total'],1)

    def test_knowledge_publication_withdrawal_and_recommendation(self):
        categories=self.client.get('/api/options/knowledge_categories').json();raw=b'<html><h1>WiFi</h1><script>console.log(1)</script></html>'
        r=self.client.post('/api/knowledge/upload',files={'file':('wifi.html',raw,'text/html')},data={'title':'WiFi 连接指南','category_id':categories[0]['id']})
        self.assertEqual(r.status_code,201,r.text);a=r.json()['article']
        self.assertEqual(self.client.get('/read/'+a['id']).status_code,404)
        self.assertEqual(self.client.get('/api/knowledge',params={'manage':True}).json()['items'][0]['view_count'],0)
        r=self.client.post('/api/knowledge/'+a['id']+'/publish',json={'state':'published','version':a['version'],'version_no':1});self.assertEqual(r.status_code,200,r.text)
        response=self.client.get('/read/'+a['id']);self.assertEqual(response.status_code,200);self.assertIn('sandbox',response.headers['content-security-policy']);self.assertNotIn('allow-same-origin',response.headers['content-security-policy'])
        self.assertEqual(self.client.get('/api/knowledge',params={'manage':True}).json()['items'][0]['view_count'],1)
        r=self.client.post('/api/knowledge/recommendations',json={'description':'WiFi 无法连接'});self.assertEqual(len(r.json()['items']),1)
        r=self.client.post('/api/knowledge/'+a['id']+'/publish',json={'state':'withdrawn','version':2});self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.client.get('/read/'+a['id']).status_code,404)
        self.assertEqual(self.client.post('/api/knowledge/recommendations',json={'description':'WiFi 无法连接'}).json()['items'],[])
        with self.app.state.engine.connect() as conn:
            version=conn.execute(sa.select(T['knowledge_versions']).where(T['knowledge_versions'].c.article_id==a['id'])).mappings().one()
            file=conn.execute(sa.select(T['file_objects']).where(T['file_objects'].c.id==version['file_id'])).mappings().one()
        source=Path(self.temp,'knowledge',file['storage_key']);self.assertTrue(source.exists())
        deleted=self.client.request('DELETE','/api/knowledge/'+a['id'],json={'version':3,'confirm':a['id'],'reason':'测试删除知识'})
        self.assertEqual(deleted.status_code,200,deleted.text);self.assertFalse(source.exists())
        self.assertEqual(self.client.get('/api/knowledge',params={'manage':True}).json()['total'],0)

    def test_ai_settings_are_admin_only_and_secret_is_not_returned(self):
        initial=self.client.get('/api/ai/settings');self.assertEqual(initial.status_code,200,initial.text)
        saved=self.client.put('/api/ai/settings',json={'enabled':True,'endpoint_url':'https://ai.example.test/v1/chat/completions',
            'model_name':'support-model','api_key':'secret-test-key','timeout_seconds':15,'max_results':4,
            'system_prompt':'只回答 IT 支持问题，不索取密码。','version':0})
        self.assertEqual(saved.status_code,200,saved.text);body=saved.json()
        self.assertTrue(body['enabled']);self.assertTrue(body['api_key_configured']);self.assertNotIn('secret-test-key',saved.text)
        secret_file=Path(self.temp,'credentials','ai-default.secret')
        self.assertTrue(secret_file.is_file());self.assertNotIn(b'secret-test-key',secret_file.read_bytes())
        self.login('employee-a')
        self.assertEqual(self.client.get('/api/ai/settings').status_code,403)

    def test_deepseek_balance_is_live_admin_only_and_does_not_expose_secret(self):
        saved=self.client.put('/api/ai/settings',json={'enabled':True,'endpoint_url':'https://api.deepseek.com/v1/chat/completions?ignored=true',
            'model_name':'deepseek-chat','api_key':'secret-balance-key','timeout_seconds':15,'max_results':4,
            'system_prompt':'只回答 IT 支持问题。','version':0})
        self.assertEqual(saved.status_code,200,saved.text)
        class Response:
            def raise_for_status(self):pass
            def json(self):return {'is_available':True,'balance_infos':[
                {'currency':'CNY','total_balance':'110.00','granted_balance':'10.00','topped_up_balance':'100.00'},
                {'currency':'USD','total_balance':'2.50','granted_balance':'0.50','topped_up_balance':'2.00'}]}
        with patch('portal.ai.httpx.get',return_value=Response()) as request:
            result=self.client.get('/api/ai/balance')
        self.assertEqual(result.status_code,200,result.text);body=result.json()
        self.assertEqual(request.call_args.args[0],'https://api.deepseek.com/user/balance')
        self.assertEqual(request.call_args.kwargs['headers']['Authorization'],'Bearer secret-balance-key')
        self.assertEqual(body['balance_infos'][0]['total_balance'],'110.00')
        self.assertNotIn('secret-balance-key',result.text)
        with self.app.state.engine.connect() as conn:
            entry=conn.execute(sa.select(T['audit_logs']).where(T['audit_logs'].c.action_code=='settings.ai.balance_view')).mappings().one()
        self.assertNotIn('110.00',entry['changes_json'])
        self.login('employee-a')
        self.assertEqual(self.client.get('/api/ai/balance').status_code,403)

    def test_balance_rejects_non_deepseek_endpoint_before_sending_secret(self):
        self.client.put('/api/ai/settings',json={'enabled':True,'endpoint_url':'https://ai.example.test/v1',
            'model_name':'support-model','api_key':'secret-test-key','timeout_seconds':15,'max_results':4,
            'system_prompt':'只回答 IT 支持问题。','version':0})
        with patch('portal.ai.httpx.get') as provider:
            result=self.client.get('/api/ai/balance')
        self.assertEqual(result.status_code,422,result.text);self.assertFalse(provider.called)

    def test_ai_chat_uses_openai_contract_and_does_not_block_ticket_fallback(self):
        self.client.put('/api/ai/settings',json={'enabled':True,'endpoint_url':'https://ai.example.test/v1',
            'model_name':'support-model','api_key':'secret-test-key','timeout_seconds':15,'max_results':4,
            'system_prompt':'只回答 IT 支持问题。','version':0})
        self.login('employee-a')
        class Response:
            def raise_for_status(self):pass
            def json(self):return {'choices':[{'message':{'content':'请先检查网线和网络图标。'}}]}
        with patch('portal.ai.httpx.post',return_value=Response()) as request:
            result=self.client.post('/api/ai/chat',json={'messages':[{'role':'user','content':'电脑无法联网'}]})
        self.assertEqual(result.status_code,200,result.text);self.assertIn('检查网线',result.json()['answer'])
        sent=request.call_args.kwargs;self.assertEqual(sent['json']['model'],'support-model')
        self.assertEqual(request.call_args.args[0],'https://ai.example.test/v1/chat/completions')
        self.assertEqual(sent['headers']['Authorization'],'Bearer secret-test-key')
        import httpx
        with patch('portal.ai.httpx.post',side_effect=httpx.ConnectError('provider unavailable')):
            failed=self.client.post('/api/ai/chat',json={'messages':[{'role':'user','content':'仍然无法联网'}]})
        self.assertEqual(failed.status_code,502);self.assertNotIn('provider unavailable',failed.text)
        ticket=self.create_ticket('AI 不可用时仍可提交工单');self.assertTrue(ticket['id'])

    def test_ai_strict_mode_skips_provider_without_knowledge(self):
        saved=self.client.put('/api/ai/settings',json={'enabled':True,'endpoint_url':'https://ai.example.test/v1',
            'model_name':'support-model','api_key':'secret-test-key','timeout_seconds':15,'max_results':4,
            'answer_mode':'strict','no_match_action':'general_advice','system_prompt':'只回答 IT 支持问题。','version':0})
        self.assertEqual(saved.status_code,200,saved.text);self.assertEqual(saved.json()['answer_mode'],'strict')
        self.login('employee-a')
        with patch('portal.ai.httpx.post') as provider:
            result=self.client.post('/api/ai/chat',json={'messages':[{'role':'user','content':'一个知识库中没有的问题'}]})
        self.assertEqual(result.status_code,200,result.text);self.assertFalse(provider.called)
        self.assertEqual(result.json()['basis'],'none');self.assertTrue(result.json()['need_ticket'])

    def test_ai_uses_matching_published_html_content_as_context(self):
        category=self.client.get('/api/options/knowledge_categories').json()[0]
        upload=self.client.post('/api/knowledge/upload',files={'file':('guide.html',b'<html><body><h1>Remote access</h1><p>ABC-7788 means restart the secure access client.</p></body></html>','text/html')},
            data={'title':'远程接入手册','category_id':category['id']})
        self.assertEqual(upload.status_code,201,upload.text);article=upload.json()['article']
        published=self.client.post('/api/knowledge/'+article['id']+'/publish',json={'state':'published','version':article['version'],'version_no':1})
        self.assertEqual(published.status_code,200,published.text)
        self.client.put('/api/ai/settings',json={'enabled':True,'endpoint_url':'https://ai.example.test/v1',
            'model_name':'support-model','api_key':'secret-test-key','timeout_seconds':15,'max_results':4,
            'answer_mode':'hybrid','no_match_action':'general_advice','system_prompt':'只回答 IT 支持问题。','version':0})
        self.login('employee-a')
        class Response:
            def raise_for_status(self):pass
            def json(self):return {'choices':[{'message':{'content':'根据《远程接入手册》，请重启客户端。'}}]}
        with patch('portal.ai.httpx.post',return_value=Response()) as provider:
            result=self.client.post('/api/ai/chat',json={'messages':[{'role':'user','content':'出现 ABC-7788 怎么办'}]})
        self.assertEqual(result.status_code,200,result.text);self.assertEqual(result.json()['basis'],'knowledge_base')
        self.assertFalse(result.json()['need_ticket']);self.assertEqual(result.json()['recommendations'][0]['title'],'远程接入手册')
        self.assertIn('ABC-7788',provider.call_args.kwargs['json']['messages'][0]['content'])

    def test_consumable_stock_history_standalone_and_computer_issue(self):
        from datetime import date
        site=self.client.get('/api/lookups').json()['sites'][0]['id']
        computer=self.client.post('/api/computers',json={'asset_code':'PC-CONSUMABLE','device_type':'台式机','assignment_type':'shared',
            'site_id':site,'asset_status':'in_use','adapters':[],'accessories':[]})
        self.assertEqual(computer.status_code,201,computer.text);computer=computer.json()
        consumable_options=self.client.get('/api/consumables/options').json();computer_option=next(v for v in consumable_options['computers'] if v['id']==computer['id'])
        self.assertIn('PC-CONSUMABLE · 公共设备 · 台式机',computer_option['name'])
        created=self.client.post('/api/consumables',json={'name':'无线鼠标','category':'电脑配件','specification':'2.4G','unit':'个','minimum_stock':'2'})
        self.assertEqual(created.status_code,201,created.text);item_id=created.json()['id']
        item=self.client.get('/api/consumables').json()['items'][0]
        inbound=self.client.post('/api/consumables/'+item_id+'/movements',json={'movement_type':'inbound','version':item['version'],
            'quantity':'10','occurred_on':date.today().isoformat(),'unit_cost':'39.90','supplier':'测试供应商','reference_no':'PO-001'})
        self.assertEqual(inbound.status_code,201,inbound.text);self.assertEqual(inbound.json()['current_stock'],'10.00')
        item=self.client.get('/api/consumables').json()['items'][0]
        linked=self.client.post('/api/consumables/'+item_id+'/movements',json={'movement_type':'outbound','version':item['version'],
            'quantity':'2','occurred_on':date.today().isoformat(),'computer_id':computer['id'],'purpose':'电脑配件领用'})
        self.assertEqual(linked.status_code,201,linked.text)
        detail=self.client.get('/api/computers/'+computer['id']).json();self.assertEqual(detail['consumable_issues'][0]['name'],'无线鼠标')
        item=self.client.get('/api/consumables').json()['items'][0]
        standalone=self.client.post('/api/consumables/'+item_id+'/movements',json={'movement_type':'outbound','version':item['version'],
            'quantity':'1','occurred_on':date.today().isoformat(),'recipient_text':'一楼会议室','purpose':'会议设备使用'})
        self.assertEqual(standalone.status_code,201,standalone.text);self.assertEqual(standalone.json()['current_stock'],'7.00')
        history=self.client.get('/api/consumables/'+item_id+'/movements').json()
        self.assertEqual(history['total'],3);self.assertEqual(history['current_stock'],'7.00')
        item=self.client.get('/api/consumables').json()['items'][0]
        shortage=self.client.post('/api/consumables/'+item_id+'/movements',json={'movement_type':'outbound','version':item['version'],
            'quantity':'8','occurred_on':date.today().isoformat(),'recipient_text':'测试','purpose':'测试'})
        self.assertEqual(shortage.status_code,409,shortage.text)
        linked_movement=linked.json()['movement'];item=self.client.get('/api/consumables').json()['items'][0]
        returned=self.client.post(f'/api/consumables/{item_id}/movements/{linked_movement["id"]}/reverse',json={
            'version':item['version'],'reason':'员工归还未使用耗材'})
        self.assertEqual(returned.status_code,201,returned.text);self.assertEqual(returned.json()['current_stock'],'9.00')
        self.assertEqual(self.client.get('/api/computers/'+computer['id']).json()['consumable_issues'],[])
        item=self.client.get('/api/consumables').json()['items'][0]
        repeated=self.client.post(f'/api/consumables/{item_id}/movements/{linked_movement["id"]}/reverse',json={
            'version':item['version'],'reason':'重复返库'})
        self.assertEqual(repeated.status_code,409,repeated.text)
        inbound_movement=inbound.json()['movement'];item=self.client.get('/api/consumables').json()['items'][0]
        cannot_revoke=self.client.post(f'/api/consumables/{item_id}/movements/{inbound_movement["id"]}/reverse',json={
            'version':item['version'],'reason':'测试撤销'})
        self.assertEqual(cannot_revoke.status_code,409,cannot_revoke.text)
        item=self.client.get('/api/consumables').json()['items'][0]
        standalone_return=self.client.post(f'/api/consumables/{item_id}/movements/{standalone.json()["movement"]["id"]}/reverse',json={
            'version':item['version'],'reason':'会议室退回'})
        self.assertEqual(standalone_return.status_code,201,standalone_return.text);self.assertEqual(standalone_return.json()['current_stock'],'10.00')
        item=self.client.get('/api/consumables').json()['items'][0]
        revoked=self.client.post(f'/api/consumables/{item_id}/movements/{inbound_movement["id"]}/reverse',json={
            'version':item['version'],'reason':'采购记录录入错误'})
        self.assertEqual(revoked.status_code,201,revoked.text);self.assertEqual(revoked.json()['current_stock'],'0.00')
        self.login('employee-a');self.assertEqual(self.client.get('/api/consumables').status_code,403)

    def test_consumable_item_delete_only_without_movements(self):
        created=self.client.post('/api/consumables',json={'name':'临时品类','unit':'个','minimum_stock':'0'}).json()
        deleted=self.client.request('DELETE','/api/consumables/'+created['id'],json={'version':created['version']})
        self.assertEqual(deleted.status_code,200,deleted.text)
        self.assertEqual(self.client.get('/api/consumables',params={'q':'临时品类'}).json()['total'],0)

    def test_secure_memo_it_access_encryption_reveal_and_delete(self):
        private=self.client.post('/api/memos',json={'title':'核心交换机','category':'network','system_address':'10.10.0.1',
            'username':'net-admin','password':'memo-secret-2026','tags':'网络, 核心','notes':'机房设备'})
        self.assertEqual(private.status_code,201,private.text);private=private.json()
        self.assertTrue(private['has_password']);self.assertNotIn('password_ciphertext',private);self.assertNotIn('memo-secret-2026',json.dumps(private))
        shared=self.client.post('/api/memos',json={'title':'供应商平台','category':'supplier','system_address':'https://vendor.example.test',
            'username':'service-user','password':'shared-secret-2026','tags':'供应商','notes':'IT 共用'})
        self.assertEqual(shared.status_code,201,shared.text);shared=shared.json()
        listing=self.client.get('/api/memos').json();self.assertEqual(listing['total'],2)
        self.assertNotIn('shared-secret-2026',json.dumps(listing,ensure_ascii=False))
        self.assertEqual(self.client.get('/api/memos',params={'q':'shared-secret-2026'}).json()['total'],0)
        with self.app.state.engine.connect() as conn:
            ciphertext=conn.execute(sa.select(T['secure_memos'].c.password_ciphertext).where(T['secure_memos'].c.id==shared['id'])).scalar_one()
            self.assertNotEqual(ciphertext,'shared-secret-2026');self.assertNotIn('shared-secret-2026',ciphertext)

        self.login('it-a')
        it_listing=self.client.get('/api/memos')
        self.assertEqual(it_listing.status_code,200,it_listing.text);self.assertEqual({v['id'] for v in it_listing.json()['items']},{private['id'],shared['id']})
        revealed=self.client.post('/api/memos/'+shared['id']+'/secret',json={})
        self.assertEqual(revealed.status_code,200,revealed.text);self.assertEqual(revealed.json()['password'],'shared-secret-2026')
        self.assertEqual(revealed.headers['cache-control'],'no-store')
        denied=self.client.put('/api/memos/'+shared['id'],json={'version':shared['version'],'title':'无权修改','category':'supplier'})
        self.assertEqual(denied.status_code,403,denied.text)

        self.login('employee-a')
        self.assertEqual(self.client.get('/api/memos').status_code,403)

        self.login('admin','test-admin-2026')
        updated=self.client.put('/api/memos/'+private['id'],json={'version':private['version'],'title':'核心交换机更新','category':'network',
            'system_address':'10.10.0.1','username':'net-admin','tags':'网络','notes':'更新说明'})
        self.assertEqual(updated.status_code,200,updated.text);updated=updated.json()
        self.assertEqual(self.client.post('/api/memos/'+private['id']+'/secret',json={}).json()['password'],'memo-secret-2026')
        cleared=self.client.put('/api/memos/'+private['id'],json={'version':updated['version'],'title':updated['title'],'category':'network',
            'system_address':'10.10.0.1','username':'net-admin','tags':'网络','notes':'更新说明','clear_password':True})
        self.assertEqual(cleared.status_code,200,cleared.text);self.assertFalse(cleared.json()['has_password'])
        self.assertEqual(self.client.post('/api/memos/'+private['id']+'/secret',json={}).status_code,404)
        deleted=self.client.request('DELETE','/api/memos/'+shared['id'],json={'version':shared['version']})
        self.assertEqual(deleted.status_code,200,deleted.text)
        audits=self.client.get('/api/audit',params={'page':1,'page_size':50}).json()['items']
        self.assertFalse(any(v['action_code']=='memo.secret.view' and v['target_id']==shared['id'] for v in audits))

    def test_ticket_delete_preserves_audit_and_no_orphans(self):
        t=self.create_ticket();self.client.post('/api/tickets/'+t['id']+'/events',json={'body':'test'})
        r=self.client.request('DELETE','/api/tickets/'+t['id'],json={'version':t['version'],'confirm':t['ticket_number'],'reason':'测试清理'})
        self.assertEqual(r.status_code,200,r.text)
        with self.app.state.engine.connect() as conn:
            self.assertEqual(conn.execute(sa.select(sa.func.count()).select_from(T['ticket_cycles'])).scalar_one(),0)
            self.assertIsNotNone(conn.execute(sa.select(T['audit_logs']).where(T['audit_logs'].c.action_code=='ticket.delete')).first())

    def test_manual_backup_endpoint_is_removed(self):
        r=self.client.post('/api/backups',json={'confirm':'BACKUP'})
        self.assertEqual(r.status_code,404,r.text)

    def test_ddl_compiles_for_both_target_engines(self):
        for dialect in (mssql.dialect(),mysql.dialect()):
            for table in metadata.tables.values():
                self.assertTrue(str(CreateTable(table).compile(dialect=dialect)))
                for index in table.indexes:self.assertTrue(str(CreateIndex(index).compile(dialect=dialect)))

    def test_new_ids_are_uuid7_and_sort_by_creation_order(self):
        values=[uid() for _ in range(5)]
        self.assertTrue(all(uuid.UUID(value).version==7 for value in values));self.assertEqual(values,sorted(values))

    def test_user_anonymization_and_role_disable(self):
        self.login('employee-a');t=self.create_ticket();self.login('admin','test-admin-2026')
        user=next(v for v in self.client.get('/api/users').json()['items'] if v['id']==self.employee)
        r=self.client.request('DELETE','/api/users/'+self.employee,json={'version':user['version'],'confirm':self.employee,'reason':'清理测试账号'})
        self.assertEqual(r.status_code,200,r.text)
        detail=self.client.get('/api/tickets/'+t['id']).json();self.assertEqual(detail['requester_name_snapshot'],'已删除用户')
        role=next(r for r in self.client.get('/api/roles').json()['items'] if r['code']=='employee')
        r=self.client.post('/api/roles/'+role['id']+'/state',json={'disabled':True,'version':role['version']})
        self.assertEqual(r.status_code,200,r.text);self.login('employee-b')
        self.assertEqual(self.client.get('/api/tickets').status_code,403)

    def test_background_session_poll_does_not_extend_idle(self):
        self.login('employee-a')
        with self.app.state.engine.begin() as conn:
            s=T['user_sessions'];before=conn.execute(sa.select(s.c.idle_expires_at).where(s.c.user_id==self.employee)).scalar_one()
        self.assertIsNotNone(self.client.get('/api/session',headers={'X-Portal-Activity':'0'}).json()['user'])
        with self.app.state.engine.begin() as conn:
            after=conn.execute(sa.select(s.c.idle_expires_at).where(s.c.user_id==self.employee)).scalar_one()
            self.assertEqual(before,after)
            conn.execute(s.update().where(s.c.user_id==self.employee).values(expires_at=utcnow()-timedelta(seconds=1)))
        self.assertIsNone(self.client.get('/api/session').json()['user'])

    def test_simultaneous_claims_only_one_succeeds(self):
        from concurrent.futures import ThreadPoolExecutor
        t=self.create_ticket();clients=[]
        for account in ['it-a','it-b']:
            c=TestClient(self.app);r=c.post('/api/auth/login',json={'login_name':account,'password':'test-user-2026'})
            self.assertEqual(r.status_code,200);c.headers['X-CSRF-Token']=r.json()['user']['csrf'];clients.append(c)
        try:
            def claim(c):return c.post('/api/tickets/'+t['id']+'/actions',json={'action':'claim','version':t['version']}).status_code
            with ThreadPoolExecutor(max_workers=2) as executor:statuses=list(executor.map(claim,clients))
            self.assertEqual(sorted(statuses),[200,409])
        finally:
            for c in clients:c.close()

    def test_existing_file_import_endpoints_are_removed(self):
        self.assertIn(self.client.get('/api/knowledge/existing-files').status_code,(404,405))
        self.assertIn(self.client.post('/api/knowledge/import-existing',json={}).status_code,(404,405))

    def test_resource_edit_cannot_move_target_into_own_scope(self):
        site=self.client.get('/api/lookups').json()['sites'][0]['id']
        r=self.client.post('/api/resources/device',json={'resource':{'resource_code':'SW-SCOPE','name':'他人资源','site_id':site,'owner_user_id':self.it_b},'details':{'device_type_code':'switch'}})
        self.assertEqual(r.status_code,201,r.text);resource=r.json()['resource']
        role=self.client.post('/api/roles',json={'code':'scoped_resource','name':'仅编辑负责资源','permissions':[
            {'code':'resource.view','scope':'all'},{'code':'resource.edit','scope':'assigned'},{'code':'resource.create','scope':'assigned'}]}).json()
        u=next(v for v in self.client.get('/api/users').json()['items'] if v['id']==self.employee)
        r=self.client.put('/api/users/'+self.employee,json={'version':u['version'],'role_ids':[self.roles['employee'],role['id']]})
        self.assertEqual(r.status_code,200,r.text);self.login('employee-a')
        r=self.client.put('/api/data/resources/'+resource['id'],json={'version':resource['version'],'owner_user_id':self.employee,'name':'越权修改'})
        self.assertEqual(r.status_code,403)
        self.assertEqual(self.client.put('/api/data/devices/'+resource['id'],json={'version':resource['version'],'model':'越权参数'}).status_code,403)
        self.assertEqual(self.client.get('/api/resources/'+resource['id']+'/full').json()['resource']['name'],'他人资源')

    def test_pending_file_recovery_integrity_report_and_structured_log(self):
        storage=self.app.state.storage;raw=b'%PDF-1.4\nmaintenance test';key=uid()+'.pdf'
        staged=storage.stage(raw,'.pdf','ticket_attachment',key)
        with self.app.state.engine.begin() as conn:
            file_row=insert_row(conn,'file_objects',{'storage_key':key,'original_name':'test.pdf','mime_type':'application/pdf',
                'size_bytes':staged.size_bytes,'sha256':staged.sha256,'purpose':'ticket_attachment','uploaded_by_user_id':self.admin['id'],'file_state':'pending'},self.admin['id'])
        report=storage.reconcile(self.app.state.engine,T)
        self.assertIn(key,report['recovered_pending']);self.assertTrue(staged.final_path.is_file());self.assertFalse(staged.temp_path.exists())
        with self.app.state.engine.begin() as conn:
            self.assertEqual(conn.execute(sa.select(T['file_objects'].c.file_state).where(T['file_objects'].c.id==file_row['id'])).scalar_one(),'ready')
        orphan=Path(self.temp,'attachments','orphan.bin');orphan.write_bytes(b'orphan')
        report=storage.reconcile(self.app.state.engine,T)
        self.assertIn('orphan.bin',[v['storage_key'] for v in report['orphan_files']])
        self.assertEqual(self.client.get('/api/system/file-integrity').status_code,200)
        for handler in self.app.state.logger.handlers:handler.flush()
        entries=[json.loads(v) for v in Path(self.temp,'logs','portal.jsonl').read_text(encoding='utf-8').splitlines() if v]
        self.assertTrue(any(v['event']=='http.request' and v.get('request_id') for v in entries))

    def test_maintenance_retains_only_180_days_and_logs_90_days(self):
        old=utcnow()-timedelta(days=181);recent=utcnow()-timedelta(days=179)
        with self.app.state.engine.begin() as conn:
            notification=insert_row(conn,'notifications',{'recipient_user_id':self.employee,'event_key':'old-retention-test',
                'title':'旧消息','message_text':'应清理','read_at':None})
            conn.execute(T['notifications'].update().where(T['notifications'].c.id==notification['id']).values(created_at=old))
            recent_notification=insert_row(conn,'notifications',{'recipient_user_id':self.employee,'event_key':'recent-retention-test',
                'title':'保留消息','message_text':'应保留','read_at':None})
            conn.execute(T['notifications'].update().where(T['notifications'].c.id==recent_notification['id']).values(created_at=recent))
            audit(conn,None,'test.old.audit','tests','old')
            conn.execute(T['audit_logs'].update().where(T['audit_logs'].c.action_code=='test.old.audit').values(occurred_at=old))
            audit(conn,None,'test.recent.audit','tests','recent')
            conn.execute(T['audit_logs'].update().where(T['audit_logs'].c.action_code=='test.recent.audit').values(occurred_at=recent))
        old_log=Path(self.temp,'logs','portal.jsonl.2000-01-01');old_log.write_text('{}\n',encoding='utf-8')
        timestamp=(datetime.now()-timedelta(days=91)).timestamp();os.utime(old_log,(timestamp,timestamp))
        result=self.app.state.run_maintenance();self.assertIsNotNone(result)
        self.assertGreaterEqual(result['deleted']['notifications'],1);self.assertGreaterEqual(result['deleted']['audit_logs'],1)
        self.assertFalse(old_log.exists())
        with self.app.state.engine.begin() as conn:
            self.assertIsNone(conn.execute(sa.select(T['notifications'].c.id).where(T['notifications'].c.id==notification['id'])).first())
            self.assertIsNotNone(conn.execute(sa.select(T['notifications'].c.id).where(T['notifications'].c.id==recent_notification['id'])).first())
            self.assertIsNone(conn.execute(sa.select(T['audit_logs'].c.id).where(T['audit_logs'].c.action_code=='test.old.audit')).first())
            self.assertIsNotNone(conn.execute(sa.select(T['audit_logs'].c.id).where(T['audit_logs'].c.action_code=='test.recent.audit')).first())
            self.assertIsNotNone(conn.execute(sa.select(T['audit_logs'].c.id).where(T['audit_logs'].c.action_code=='system.retention')).first())


if __name__=='__main__':unittest.main()
