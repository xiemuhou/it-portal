"""Small encrypted IT memo store with explicit secret access auditing."""
import sqlalchemy as sa
from fastapi import Request

from .database import TABLES as T,insert_row,row,utcnow
from .ledger_secrets import encrypt,decrypt
from .security import audit,fail,require


CATEGORIES={'system','network','server','database','supplier','other'}


def _text(value,label,limit,required=False,strip=True):
    if value is None:value=''
    if not isinstance(value,str):fail(label+'格式无效')
    value=value.strip() if strip else value
    if required and not value:fail('请填写'+label)
    if '\x00' in value or len(value)>limit:fail(label+'内容过长或无效')
    return value or None


def _result(value):
    result=dict(value)
    result['has_password']=bool(result.pop('password_ciphertext',None))
    return result


def _editable(item,user):
    if item['created_by_user_id']!=user['id']:fail('只能修改或删除自己创建的备忘录',403)


def _authorize(conn,user,permission):
    require(conn,user,permission)
    roles=T['roles'];user_roles=T['user_roles']
    allowed=conn.execute(sa.select(roles.c.id).select_from(user_roles.join(roles,roles.c.id==user_roles.c.role_id)).where(
        user_roles.c.user_id==user['id'],roles.c.code.in_(('admin','it')),roles.c.is_archived==False).limit(1)).first()
    if not allowed:fail('IT 备忘录仅管理员和 IT 人员可访问',403)


def register(app,engine,out,current_user):
    @app.get('/api/memos')
    def list_memos(request:Request,page:int=1,page_size:int=10,q:str='',category:str=''):
        if page_size not in (10,20,50):fail('每页条数仅支持 10、20、50')
        if category and category not in CATEGORIES:fail('分类无效')
        with engine.begin() as conn:
            user=current_user(conn,request);_authorize(conn,user,'memo.view');memos=T['secure_memos'];creators=T['users'].alias('memo_creators')
            query=sa.select(memos,creators.c.display_name.label('creator_name')).select_from(
                memos.join(creators,creators.c.id==memos.c.created_by_user_id)).where(memos.c.is_archived==False)
            q=q.strip()
            if q:
                query=query.where(sa.or_(memos.c.title.contains(q,autoescape=True),memos.c.system_address.contains(q,autoescape=True),
                    memos.c.username.contains(q,autoescape=True),memos.c.tags.contains(q,autoescape=True),memos.c.notes.contains(q,autoescape=True)))
            if category:query=query.where(memos.c.category==category)
            total=conn.execute(sa.select(sa.func.count()).select_from(query.subquery())).scalar_one();page=max(1,page)
            values=conn.execute(query.order_by(memos.c.updated_at.desc(),memos.c.id.desc()).offset((page-1)*page_size).limit(page_size)).mappings().all()
            return out({'items':[_result(v) for v in values],'total':total,'page':page,'page_size':page_size})

    @app.post('/api/memos')
    def create_memo(request:Request,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);_authorize(conn,user,'memo.edit')
            category=body.get('category')
            if category not in CATEGORIES:fail('请选择有效分类')
            password=_text(body.get('password'),'密码',4096,strip=False)
            value=insert_row(conn,'secure_memos',{'title':_text(body.get('title'),'标题',160,True),'category':category,
                'system_address':_text(body.get('system_address'),'系统或设备地址',1000),'username':_text(body.get('username'),'用户名',256),
                'password_ciphertext':encrypt(conn,password),'tags':_text(body.get('tags'),'标签',500),
                'notes':_text(body.get('notes'),'备注',10000)},user['id'])
            audit(conn,user,'memo.create','secure_memos',value['id'],{'category':category,'has_password':bool(password)})
            return out(_result(value),201)

    @app.put('/api/memos/{key}')
    def update_memo(request:Request,key:str,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);_authorize(conn,user,'memo.edit');old=row(conn,'secure_memos',key)
            if not old or old['is_archived']:fail('备忘录不存在',404)
            _editable(old,user)
            if body.get('version')!=old['version']:fail('备忘录已发生变化，请刷新后重试',409)
            category=body.get('category')
            if category not in CATEGORIES:fail('请选择有效分类')
            password_ciphertext=old['password_ciphertext']
            password_changed=False
            if body.get('clear_password') is True:password_ciphertext=None;password_changed=bool(old['password_ciphertext'])
            elif 'password' in body:
                password=_text(body.get('password'),'密码',4096,strip=False)
                password_ciphertext=encrypt(conn,password);password_changed=True
            values={'title':_text(body.get('title'),'标题',160,True),'category':category,
                'system_address':_text(body.get('system_address'),'系统或设备地址',1000),'username':_text(body.get('username'),'用户名',256),
                'password_ciphertext':password_ciphertext,'tags':_text(body.get('tags'),'标签',500),
                'notes':_text(body.get('notes'),'备注',10000),'version':old['version']+1,'updated_at':utcnow(),'updated_by_user_id':user['id']}
            if conn.execute(T['secure_memos'].update().where(T['secure_memos'].c.id==key,T['secure_memos'].c.version==old['version']).values(**values)).rowcount!=1:fail('备忘录已发生变化，请刷新后重试',409)
            audit(conn,user,'memo.edit','secure_memos',key,{'category':category,'password_changed':password_changed})
            return out(_result(row(conn,'secure_memos',key)))

    @app.post('/api/memos/{key}/secret')
    def reveal_secret(request:Request,key:str,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);_authorize(conn,user,'memo.secret_view');memos=T['secure_memos']
            item=conn.execute(sa.select(memos).where(memos.c.id==key,memos.c.is_archived==False)).mappings().first()
            if not item:fail('备忘录不存在',404)
            if not item['password_ciphertext']:fail('该备忘录没有保存密码',404)
            password=decrypt(conn,item['password_ciphertext'])
            response=out({'password':password});response.headers['Cache-Control']='no-store';response.headers['Pragma']='no-cache'
            return response

    @app.delete('/api/memos/{key}')
    def delete_memo(request:Request,key:str,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);_authorize(conn,user,'memo.delete');old=row(conn,'secure_memos',key)
            if not old or old['is_archived']:fail('备忘录不存在',404)
            _editable(old,user)
            if body.get('version')!=old['version']:fail('备忘录已发生变化，请刷新后重试',409)
            count=conn.execute(T['secure_memos'].update().where(T['secure_memos'].c.id==key,T['secure_memos'].c.version==old['version']).values(
                is_archived=True,password_ciphertext=None,version=old['version']+1,updated_at=utcnow(),updated_by_user_id=user['id'])).rowcount
            if count!=1:fail('备忘录已发生变化，请刷新后重试',409)
            audit(conn,user,'memo.delete','secure_memos',key,{'password_erased':bool(old['password_ciphertext'])})
            return out({'deleted':True})
