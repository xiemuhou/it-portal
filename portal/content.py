"""Published knowledge, announcements, reports, and attachments."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from io import BytesIO
from urllib.parse import quote
from urllib.parse import urlparse
import json
import mimetypes
import os
import secrets
import shutil

import sqlalchemy as sa
from fastapi import Request,UploadFile,File,Form
from fastapi.responses import JSONResponse,FileResponse,HTMLResponse,Response,RedirectResponse

from .database import ROOT,TABLES as T,insert_row,row,utcnow,jsonable,uid
from .security import require,allow,current_user,fail,audit,csrf,password_hash
from . import catalog,tickets,transfers
from .ai import _document_text
from document_library import KnowledgeLibrary,SUPPORTED


def out(data,status=200):return JSONResponse(jsonable(data),status_code=status)


def published_version(conn,key,editor=False):
    article=row(conn,'knowledge_articles',key)
    if not article or article['is_archived'] or (not editor and article['publication_state']!='published'):fail('知识文章不存在',404)
    v=T['knowledge_versions'];query=sa.select(v).where(v.c.article_id==key)
    if not editor:query=query.where(v.c.version_no==article['published_version_no'])
    version=conn.execute(query.order_by(v.c.version_no.desc()).limit(1)).mappings().first()
    if not version:fail('知识文章没有可用版本',404)
    file=row(conn,'file_objects',version['file_id'])
    if not file or file['file_state']!='ready':fail('知识文件不可用',404)
    return dict(article),dict(version),dict(file)


def register_content(app,engine,folder,config,storage,logger):
    knowledge_root=folder/'knowledge';knowledge_root.mkdir(parents=True,exist_ok=True)
    attachment_root=folder/'attachments';attachment_root.mkdir(parents=True,exist_ok=True)
    assets_root=folder/'knowledge-assets';assets_root.mkdir(parents=True,exist_ok=True)
    library=KnowledgeLibrary(knowledge_root,folder/'knowledge-cache')

    def file_path(file):
        path=(knowledge_root/file['storage_key']).resolve()
        if path.parent!=knowledge_root.resolve() or not path.is_file():fail('文件不存在',404)
        return path

    def upload_knowledge(conn,user,name,ext,staged,title,category_id,key=None):
        require(conn,user,'knowledge.edit')
        category=row(conn,'knowledge_categories',category_id)
        if not category or not category['is_enabled'] or category['is_archived']:fail('请选择有效知识分类')
        file=insert_row(conn,'file_objects',{'storage_key':staged.storage_key,'original_name':name,
            'mime_type':mimetypes.guess_type(name)[0] or 'application/octet-stream','size_bytes':staged.size_bytes,
            'sha256':staged.sha256,'purpose':'knowledge','uploaded_by_user_id':user['id'],'file_state':'pending'},user['id'])
        if key:
            article=row(conn,'knowledge_articles',key)
            if not article or article['is_archived']:fail('知识文章不存在',404)
            number=conn.execute(sa.select(sa.func.max(T['knowledge_versions'].c.version_no)).where(T['knowledge_versions'].c.article_id==key)).scalar_one()+1
        else:
            article=insert_row(conn,'knowledge_articles',{'article_code':'KB-'+uid().replace('-','')[-8:].upper(),'category_id':category_id,
                'title':tickets.text(title,'知识标题',200,True),'publication_state':'draft','view_count':0},user['id']);key=article['id'];number=1
        version=insert_row(conn,'knowledge_versions',{'article_id':key,'version_no':number,'file_id':file['id'],
            'file_format':ext[1:],'conversion_state':'ready' if ext in ('.html','.htm','.pdf') else 'pending'},user['id'])
        audit(conn,user,'knowledge.upload','knowledge_articles',key,{'version':number})
        return {'article':dict(article),'version':version},file['id']

    @app.get('/api/public')
    def public():
        with engine.begin() as conn:
            a=T['announcements'];u=T['users'];services=T['service_catalog']
            announcements=list(conn.execute(sa.select(a.c.id,a.c.title,a.c.published_at,a.c.is_pinned,u.c.display_name.label('publisher_name')).select_from(a.outerjoin(u,a.c.published_by_user_id==u.c.id)).where(a.c.is_archived==False,
                a.c.publication_state=='published',sa.or_(a.c.expires_at.is_(None),a.c.expires_at>utcnow())).order_by(a.c.is_pinned.desc(),a.c.published_at.desc(),a.c.id).limit(5)).mappings())
            return out({'announcements':announcements,'monitor_url':config['monitor_url'],
                'services':list(conn.execute(sa.select(services).where(services.c.is_published==True,services.c.is_archived==False).order_by(services.c.sort_order,services.c.id)).mappings())})

    @app.get('/api/announcements')
    def public_announcements(page:int=1,page_size:int=10):
        if page_size not in (10,20,50):fail('每页条数仅支持 10、20、50',422)
        with engine.begin() as conn:
            t,u=T['announcements'],T['users'];q=sa.select(t.c.id,t.c.title,t.c.published_at,t.c.is_pinned,u.c.display_name.label('publisher_name')).select_from(t.outerjoin(u,t.c.published_by_user_id==u.c.id)).where(t.c.is_archived==False,t.c.publication_state=='published',sa.or_(t.c.expires_at.is_(None),t.c.expires_at>utcnow()))
            total=conn.execute(sa.select(sa.func.count()).select_from(q.subquery())).scalar_one()
            return out({'items':list(conn.execute(q.order_by(t.c.is_pinned.desc(),t.c.published_at.desc(),t.c.id).offset((max(1,page)-1)*page_size).limit(page_size)).mappings()),'total':total,'page':max(1,page),'page_size':page_size})

    @app.get('/api/announcements/{key}')
    def public_announcement(key:str):
        with engine.begin() as conn:
            a=row(conn,'announcements',key)
            if not a or a['is_archived'] or a['publication_state']!='published' or a['expires_at'] and a['expires_at']<=utcnow():fail('公告不存在或已撤下',404)
            af,f=T['announcement_files'],T['file_objects']
            files=[dict(v) for v in conn.execute(sa.select(af.c.id,f.c.original_name,f.c.size_bytes,f.c.mime_type)
                .select_from(af.join(f,af.c.file_id==f.c.id)).where(af.c.announcement_id==key,f.c.file_state=='ready')
                .order_by(af.c.created_at,af.c.id)).mappings()]
            for item in files:item['url']='/api/files/announcement/'+item['id']
            publisher=row(conn,'users',a['published_by_user_id']) if a['published_by_user_id'] else None
            return out({**{k:a[k] for k in ('id','title','body','published_at')},
                'publisher_name':publisher['display_name'] if publisher else None,'attachments':files})

    def announcement_file_rows(conn,key):
        af,f=T['announcement_files'],T['file_objects']
        return list(conn.execute(sa.select(af.c.id,af.c.announcement_id,f.c.original_name,f.c.size_bytes,f.c.mime_type)
            .select_from(af.join(f,af.c.file_id==f.c.id)).where(af.c.announcement_id==key,f.c.file_state=='ready')
            .order_by(af.c.created_at,af.c.id)).mappings())

    @app.get('/api/announcements/{key}/attachments')
    def announcement_attachments(request:Request,key:str):
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'announcement.edit');a=row(conn,'announcements',key)
            if not a:fail('公告不存在',404)
            return out(announcement_file_rows(conn,key))

    @app.post('/api/announcements/{key}/attachments')
    def announcement_attachment_upload(request:Request,key:str,files:list[UploadFile]=File(...)):
        allowed={'.pdf','.doc','.docx','.xls','.xlsx','.ppt','.pptx','.png','.jpg','.jpeg','.txt','.zip'}
        staged_files=[];pending=[];result=[]
        try:
            with engine.begin() as conn:
                user=current_user(conn,request);require(conn,user,'announcement.edit');a=row(conn,'announcements',key)
                if not a:fail('公告不存在',404)
                if a['publication_state']=='published':fail('请先撤下公告，再修改附件',409)
                existing=len(announcement_file_rows(conn,key))
                if not files or existing+len(files)>10:fail('每个公告最多 10 个附件')
                for upload in files:
                    name=Path((upload.filename or '').replace('\\','/')).name;ext=Path(name).suffix.lower()
                    raw=upload.file.read(20*1024*1024+1)
                    if ext not in allowed or not raw or len(raw)>20*1024*1024:fail('附件须为 20 MB 以内的常用文档、图片、文本或 ZIP 文件')
                    if ext=='.pdf' and not raw.startswith(b'%PDF'):fail(f'{name} 不是有效的 PDF 文件')
                    if ext in ('.docx','.xlsx','.pptx','.zip') and not raw.startswith(b'PK'):fail(f'{name} 的文件签名无效')
                    if ext in ('.doc','.xls','.ppt') and not raw.startswith(bytes.fromhex('D0CF11E0A1B11AE1')):fail(f'{name} 的文件签名无效')
                    staged=storage.stage(raw,ext,'announcement',uid()+ext);staged_files.append(staged)
                    file_row=insert_row(conn,'file_objects',{'storage_key':staged.storage_key,'original_name':name,
                        'mime_type':mimetypes.guess_type(name)[0] or 'application/octet-stream','size_bytes':staged.size_bytes,
                        'sha256':staged.sha256,'purpose':'announcement','uploaded_by_user_id':user['id'],'file_state':'pending'},user['id'])
                    relation=insert_row(conn,'announcement_files',{'announcement_id':key,'file_id':file_row['id'],'label':None},user['id'])
                    pending.append((file_row['id'],staged));result.append({'id':relation['id'],'original_name':name,'size_bytes':staged.size_bytes})
                audit(conn,user,'announcement.attachment.upload','announcements',key,{'count':len(result)})
        except Exception:
            for staged in staged_files:storage.discard(staged)
            raise
        try:
            for file_id,staged in pending:storage.finalize(engine,T,file_id,staged)
        except Exception as exc:
            logger.exception('file.finalize.failed',extra={'event':'file.finalize.failed','error_type':type(exc).__name__})
            fail('公告附件保存未完成，后台将自动重试',503)
        return out({'items':result},201)

    @app.delete('/api/announcements/{key}/attachments/{attachment_id}')
    def announcement_attachment_delete(request:Request,key:str,attachment_id:str,body:dict):
        file=None
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'announcement.edit');a=row(conn,'announcements',key)
            if not a:fail('公告不存在',404)
            if a['publication_state']=='published':fail('请先撤下公告，再修改附件',409)
            relation=row(conn,'announcement_files',attachment_id)
            if not relation or relation['announcement_id']!=key:fail('附件不存在',404)
            file=row(conn,'file_objects',relation['file_id'])
            if not file:fail('附件文件记录不存在',404)
            conn.execute(T['announcement_files'].delete().where(T['announcement_files'].c.id==attachment_id))
            conn.execute(T['file_objects'].delete().where(T['file_objects'].c.id==file['id']))
            audit(conn,user,'announcement.attachment.delete','announcements',key,{'filename':file['original_name']})
        if file:storage.delete(file['storage_key'],file['purpose'])
        return out({'ok':True})

    @app.get('/api/files/announcement/{attachment_id}')
    def public_announcement_attachment(attachment_id:str,download:bool=False):
        with engine.begin() as conn:
            relation=row(conn,'announcement_files',attachment_id)
            if not relation:fail('附件不存在',404)
            a=row(conn,'announcements',relation['announcement_id'])
            if not a or a['is_archived'] or a['publication_state']!='published' or a['expires_at'] and a['expires_at']<=utcnow():fail('附件不存在或公告已撤下',404)
            file=row(conn,'file_objects',relation['file_id'])
            if not file or file['file_state']!='ready':fail('附件不存在',404)
            path=(attachment_root/file['storage_key']).resolve()
            if path.parent!=attachment_root.resolve() or not path.is_file():fail('附件不存在',404)
            disposition=f"{'attachment' if download else 'inline'}; filename*=UTF-8''{quote(file['original_name'])}"
            return FileResponse(path,media_type=file['mime_type'],headers={'Content-Disposition':disposition})

    @app.get('/api/knowledge')
    def knowledge(request:Request,page:int=1,page_size:int=10,q:str='',manage:bool=False):
        if page_size not in (10,20,50):fail('每页条数仅支持 10、20、50',422)
        with engine.begin() as conn:
            t=T['knowledge_articles'];query=sa.select(t).where(t.c.is_archived==False)
            if manage:require(conn,current_user(conn,request),'knowledge.view')
            else:query=query.where(t.c.publication_state=='published')
            if q:query=query.where(sa.or_(t.c.title.contains(q,autoescape=True),t.c.summary.contains(q,autoescape=True),t.c.tags_text.contains(q,autoescape=True)))
            total=conn.execute(sa.select(sa.func.count()).select_from(query.subquery())).scalar_one()
            rows=[dict(v) for v in conn.execute(query.order_by(t.c.updated_at.desc(),t.c.id).offset((max(1,page)-1)*page_size).limit(page_size)).mappings()]
            for r in rows:r['reader_url']='/read/'+r['id']
            return out({'items':rows,'total':total,'page':max(1,page),'page_size':page_size})

    @app.post('/api/knowledge/upload')
    def knowledge_upload(request:Request,file:UploadFile=File(...),title:str=Form(''),category_id:str=Form(''),article_id:str=Form('')):
        raw=file.file.read(20*1024*1024+1);name=Path((file.filename or '').replace('\\','/')).name;ext=Path(name).suffix.lower()
        if ext not in SUPPORTED or not raw or len(raw)>20*1024*1024:fail('请上传 20 MB 以内的 HTML、PDF、PPT 或 PPTX 文件')
        if ext=='.pdf' and not raw.startswith(b'%PDF'):fail('PDF 文件签名无效')
        if ext=='.pptx' and not raw.startswith(b'PK'):fail('PPTX 文件签名无效')
        if ext=='.ppt' and not raw.startswith(bytes.fromhex('D0CF11E0A1B11AE1')):fail('PPT 文件签名无效')
        staged=storage.stage(raw,ext,'knowledge',uid()+ext)
        try:
            with engine.begin() as conn:
                user=current_user(conn,request);require(conn,user,'knowledge.edit')
                result,file_id=upload_knowledge(conn,user,name,ext,staged,title,category_id,article_id or None)
        except Exception:
            storage.discard(staged);raise
        try:storage.finalize(engine,T,file_id,staged)
        except Exception as exc:
            logger.exception('file.finalize.failed',extra={'event':'file.finalize.failed','error_type':type(exc).__name__})
            fail('知识文件保存未完成，后台将自动重试',503)
        return out(result,201)

    @app.get('/api/knowledge/{key}/versions')
    def knowledge_versions(request:Request,key:str):
        with engine.begin() as conn:
            require(conn,current_user(conn,request),'knowledge.edit');a=row(conn,'knowledge_articles',key)
            if not a:fail('知识不存在',404)
            rows=list(conn.execute(sa.select(T['knowledge_versions']).where(T['knowledge_versions'].c.article_id==key).order_by(T['knowledge_versions'].c.version_no.desc())).mappings())
            return out({'article':dict(a),'versions':rows})

    @app.post('/api/knowledge/{key}/publish')
    def knowledge_publish(request:Request,key:str,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'knowledge.publish');a=row(conn,'knowledge_articles',key)
            if not a:fail('知识不存在',404)
            state=body.get('state')
            if state not in ('published','withdrawn'):fail('发布状态无效')
            values={'publication_state':state}
            if state=='published':
                v=T['knowledge_versions'];version=conn.execute(sa.select(v).where(v.c.article_id==key,v.c.version_no==body.get('version_no'))).mappings().first()
                if not version:fail('请选择要发布的版本')
                file=row(conn,'file_objects',version['file_id']);path=file_path(file)
                search_text=_document_text(path)
                if path.suffix.lower() not in ('.html','.htm'):
                    info=library.info(path.name)
                    if info['status']!='ready':fail(info['message'],409)
                    conn.execute(v.update().where(v.c.id==version['id']).values(conversion_state='ready',page_count=info['pages'],search_text=search_text or None))
                elif search_text:
                    conn.execute(v.update().where(v.c.id==version['id']).values(search_text=search_text))
                values.update(published_version_no=version['version_no'],published_at=utcnow(),published_by_user_id=user['id'])
            t=T['knowledge_articles']
            if body.get('version')!=a['version']:fail('文章已更新，请刷新',409)
            if conn.execute(t.update().where(t.c.id==key,t.c.version==a['version']).values(**values,version=a['version']+1,updated_at=utcnow(),updated_by_user_id=user['id'])).rowcount!=1:fail('文章已更新',409)
            audit(conn,user,'knowledge.'+state,'knowledge_articles',key)
            return out({'ok':True})

    @app.delete('/api/knowledge/{key}')
    def knowledge_delete(request:Request,key:str,body:dict):
        storage_keys=[]
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'knowledge.delete');article=row(conn,'knowledge_articles',key)
            if not article:fail('知识不存在',404)
            if body.get('confirm')!=key:fail('请确认删除对象')
            if body.get('version')!=article['version']:fail('文章已更新，请刷新',409)
            if article['publication_state']=='published':fail('请先撤下知识文章，再永久删除',409)
            reason=tickets.text(body.get('reason'),'删除原因',1024,True)
            versions=list(conn.execute(sa.select(T['knowledge_versions']).where(T['knowledge_versions'].c.article_id==key)).mappings())
            file_ids={v[field] for v in versions for field in ('file_id','preview_file_id') if v.get(field)}
            if file_ids:
                files=list(conn.execute(sa.select(T['file_objects']).where(T['file_objects'].c.id.in_(file_ids))).mappings())
                storage_keys=[v['storage_key'] for v in files]
            conn.execute(T['knowledge_versions'].delete().where(T['knowledge_versions'].c.article_id==key))
            if file_ids:conn.execute(T['file_objects'].delete().where(T['file_objects'].c.id.in_(file_ids)))
            conn.execute(T['knowledge_articles'].delete().where(T['knowledge_articles'].c.id==key))
            audit(conn,user,'knowledge.deleted','knowledge_articles',key,{'title':article['title'],'versions':len(versions)},reason)
        for storage_key in storage_keys:
            storage.delete(storage_key,'knowledge')
            shutil.rmtree(assets_root/Path(storage_key).stem,ignore_errors=True)
        return out({'ok':True})

    @app.get('/api/knowledge/{key}/preview-status')
    def knowledge_preview(request:Request,key:str):
        with engine.begin() as conn:
            require(conn,current_user(conn,request),'knowledge.edit')
            a,v,f=published_version(conn,key,True);path=file_path(f)
            return out({'status':'ready','pages':None} if path.suffix.lower() in ('.html','.htm') else library.info(path.name))

    @app.post('/api/knowledge/recommendations')
    def recommendations(request:Request,body:dict):
        with engine.begin() as conn:
            current_user(conn,request);description=tickets.text(body.get('description'),'问题描述',20000)
            if len(description)<2:return out({'mode':'keyword','items':[],'trace_id':uid(),'fallback_reason':'description_too_short'})
            t=T['knowledge_articles'];candidates=conn.execute(sa.select(t).where(t.c.publication_state=='published',t.c.is_archived==False).limit(1000)).mappings()
            import re
            words=set(re.findall(r'[a-z0-9]{2,}',description.lower()))|{description[i:i+2].lower() for i in range(len(description)-1) if not description[i:i+2].isspace()}
            scored=[]
            for article in candidates:
                content=(article['title']+' '+(article['summary'] or '')+' '+(article['tags_text'] or '')).lower()
                score=sum(w in content for w in words)
                if score:scored.append((score,article))
            scored.sort(key=lambda v:(-v[0],v[1]['id']))
            maximum=body.get('max_results',5)
            if not isinstance(maximum,int) or not 1<=maximum<=10:fail('推荐数量须为 1～10')
            return out({'mode':'keyword','items':[{'article_id':a['id'],'title':a['title'],'summary':a['summary'],
                'reader_url':'/read/'+a['id'],'reason':'与问题描述的关键词匹配'} for _,a in scored[:maximum]],'trace_id':uid(),'fallback_reason':'external_ai_not_configured'})

    @app.get('/read/{key}')
    def read_knowledge(key:str):
        with engine.begin() as conn:
            a,v,f=published_version(conn,key);path=file_path(f)
            t=T['knowledge_articles'];conn.execute(t.update().where(t.c.id==key).values(view_count=t.c.view_count+1))
            if path.suffix.lower() in ('.html','.htm'):
                return RedirectResponse('/knowledge-content/'+key+'/document.html',status_code=302)
            return FileResponse(ROOT/'portal_static'/'reader.html')

    @app.get('/knowledge-content/{key}/{asset:path}')
    def knowledge_asset(key:str,asset:str):
        with engine.begin() as conn:
            a,v,f=published_version(conn,key);original=file_path(f)
            if original.suffix.lower() not in ('.html','.htm'):fail('此文章不是 HTML 内容包',404)
            if asset=='document.html':path=original
            else:
                root=(assets_root/original.stem).resolve();path=(root/asset).resolve()
                if not path.is_relative_to(root) or not path.is_file():fail('内容资源不存在',404)
            policy="sandbox allow-scripts allow-popups allow-popups-to-escape-sandbox; default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data:; connect-src 'none'; object-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'self'"
            return FileResponse(path,media_type='text/html' if asset=='document.html' else mimetypes.guess_type(path.name)[0],headers={'Content-Security-Policy':policy,'Access-Control-Allow-Origin':'*'})

    @app.get('/api/knowledge/{key}/document')
    def document(key:str,retry:bool=False):
        with engine.begin() as conn:
            a,v,f=published_version(conn,key);path=file_path(f)
            if path.suffix.lower() in ('.html','.htm'):fail('HTML 请直接打开原阅读页面')
            return out({'title':a['title'],**library.info(path.name,retry)})

    @app.get('/api/knowledge/{key}/page/{number}')
    def document_page(key:str,number:int):
        with engine.begin() as conn:
            a,v,f=published_version(conn,key);path=file_path(f)
            try:picture=library.page(path.name,number)
            except (ValueError,FileNotFoundError):fail('页面尚未就绪或不存在',404)
            return FileResponse(picture,media_type='image/png')

    @app.post('/api/tickets/{key}/attachments')
    def attachment_upload(request:Request,key:str,file:UploadFile=File(...),message:str=Form('附件'),internal:bool=Form(False)):
        raw=file.file.read(20*1024*1024+1);name=transfers.PathName(file.filename or 'attachment')
        ext=Path(name).suffix.lower();magic={'.png':b'\x89PNG\r\n\x1a\n','.jpg':b'\xff\xd8\xff','.jpeg':b'\xff\xd8\xff','.pdf':b'%PDF'}
        if ext not in magic or not raw.startswith(magic[ext]) or len(raw)>20*1024*1024:fail('附件仅支持 20 MB 以内的 PNG、JPG、PDF')
        staged=storage.stage(raw,ext,'ticket_attachment',uid()+ext)
        try:
            with engine.begin() as conn:
                user=current_user(conn,request);tickets.ticket(conn,key,user,'ticket.internal_note' if internal else 'ticket.comment')
                file_row=insert_row(conn,'file_objects',{'storage_key':staged.storage_key,'original_name':name,'mime_type':mimetypes.guess_type(name)[0],
                    'size_bytes':staged.size_bytes,'sha256':staged.sha256,'purpose':'ticket_attachment','uploaded_by_user_id':user['id'],'file_state':'pending'},user['id'])
                ev=tickets.comment(conn,user,key,{'body':message or '附件','internal':internal})
                relation=insert_row(conn,'ticket_attachments',{'event_id':ev['id'],'file_id':file_row['id']},user['id'])
        except Exception:
            storage.discard(staged);raise
        try:storage.finalize(engine,T,file_row['id'],staged)
        except Exception as exc:
            logger.exception('file.finalize.failed',extra={'event':'file.finalize.failed','error_type':type(exc).__name__})
            fail('工单附件保存未完成，后台将自动重试',503)
        return out({'id':relation['id'],'name':name},201)

    @app.get('/api/tickets/{key}/attachments')
    def attachments(request:Request,key:str):
        with engine.begin() as conn:
            user=current_user(conn,request);old=tickets.ticket(conn,key,user)
            a,e,f=(T[n] for n in ('ticket_attachments','ticket_events','file_objects'))
            q=sa.select(a.c.id,f.c.original_name,e.c.id.label('event_id')).select_from(a.join(e,a.c.event_id==e.c.id).join(f,a.c.file_id==f.c.id)).where(e.c.ticket_id==key,f.c.file_state=='ready')
            if not allow(conn,user,'ticket.internal_note',old):q=q.where(e.c.audience=='requester')
            return out(list(conn.execute(q).mappings()))

    @app.get('/api/files/ticket/{key}')
    def attachment_read(request:Request,key:str):
        with engine.begin() as conn:
            user=current_user(conn,request);rel=row(conn,'ticket_attachments',key)
            if not rel:fail('附件不存在',404)
            ev=row(conn,'ticket_events',rel['event_id']);old=tickets.ticket(conn,ev['ticket_id'],user)
            if ev['audience']=='internal':require(conn,user,'ticket.internal_note',old)
            f=row(conn,'file_objects',rel['file_id'])
            if not f or f['file_state']!='ready':fail('附件不存在',404)
            path=(attachment_root/f['storage_key']).resolve()
            if path.parent!=attachment_root.resolve() or not path.is_file():fail('附件不存在',404)
            return FileResponse(path,media_type=f['mime_type'],headers={'Content-Disposition':'inline'})

    @app.delete('/api/tickets/{key}')
    def delete_ticket(request:Request,key:str,body:dict):
        files=[]
        with engine.begin() as conn:
            user=current_user(conn,request);old=tickets.ticket(conn,key,user,'ticket.delete')
            reason=tickets.text(body.get('reason'),'删除原因',1024,True)
            if body.get('confirm')!=old['ticket_number'] or body.get('version')!=old['version']:fail('请核对工单编号及版本后确认永久删除',409)
            events=sa.select(T['ticket_events'].c.id).where(T['ticket_events'].c.ticket_id==key)
            file_ids=list(conn.execute(sa.select(T['ticket_attachments'].c.file_id).where(T['ticket_attachments'].c.event_id.in_(events))).scalars())
            if file_ids:files=[dict(v) for v in conn.execute(sa.select(T['file_objects']).where(T['file_objects'].c.id.in_(file_ids))).mappings()]
            conn.execute(T['ticket_attachments'].delete().where(T['ticket_attachments'].c.event_id.in_(events)))
            if file_ids:conn.execute(T['file_objects'].delete().where(T['file_objects'].c.id.in_(file_ids)))
            for name in ['notifications','ticket_handling_segments','ticket_resources','ticket_events','ticket_cycles']:
                conn.execute(T[name].delete().where(T[name].c.ticket_id==key))
            conn.execute(T['idempotency_keys'].delete().where(T['idempotency_keys'].c.result_object_id==key,T['idempotency_keys'].c.operation_code=='ticket.create'))
            conn.execute(T['tickets'].delete().where(T['tickets'].c.id==key,T['tickets'].c.version==old['version']))
            audit(conn,user,'ticket.delete','tickets',key,reason=reason)
        for file in files:storage.delete(file['storage_key'],file['purpose'])
        return out({'ok':True})

    @app.get('/api/reports/tickets')
    def reports(request:Request,start:str='',end:str='',site_id:str='',handler_id:str=''):
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'report.view');cy,t=T['ticket_cycles'],T['tickets']
            query=sa.select(cy,t.c.site_id).select_from(cy.join(t,cy.c.ticket_id==t.c.id)).where(catalog.scope_expression(conn,user,'report.view',t),cy.c.end_kind=='closed',cy.c.duration_ms.is_not(None))
            if not start and not end:
                today=datetime.now(timezone(timedelta(hours=8))).date()
                start=(today-timedelta(days=29)).isoformat();end=today.isoformat()
            try:
                if start:query=query.where(cy.c.completed_at>=datetime.fromisoformat(start)-timedelta(hours=8))
                if end:query=query.where(cy.c.completed_at<datetime.fromisoformat(end)+timedelta(days=1,hours=-8))
            except ValueError:fail('日期筛选格式错误')
            if site_id:query=query.where(t.c.site_id==site_id)
            if handler_id:query=query.where(cy.c.final_handler_id==handler_id)
            cycles=[dict(v) for v in conn.execute(query).mappings()]
            groups={};handlers={};unique=set();duration=0
            categories={v['id']:v['name'] for v in conn.execute(sa.select(T['ticket_categories'])).mappings()}
            for c in cycles:
                unique.add(c['ticket_id']);duration+=c['duration_ms'];key=c['category_id']
                g=groups.setdefault(key,{'category_id':key,'name':categories.get(key,'历史分类'),'count':0,'duration_ms':0})
                g['count']+=1;g['duration_ms']+=c['duration_ms']
                h=handlers.setdefault(c['final_handler_id'] or c['final_handler_name_snapshot'],{'name':c['final_handler_name_snapshot'] or '未匹配历史人员','closed_count':0,'duration_ms':0,'participated_cycles':set()})
                h['closed_count']+=1
            seg=T['ticket_handling_segments']
            ids=[c['id'] for c in cycles]
            # Chunk to stay below SQL Server's parameter limit.
            for i in range(0,len(ids),500):
                for s in conn.execute(sa.select(seg).where(seg.c.cycle_id.in_(ids[i:i+500]),seg.c.duration_ms.is_not(None))).mappings():
                    key=s['handler_user_id'] or s['handler_name_snapshot'];h=handlers.setdefault(key,{'name':s['handler_name_snapshot'] or '未匹配历史人员','closed_count':0,'duration_ms':0,'participated_cycles':set()})
                    h['duration_ms']+=s['duration_ms'];h['participated_cycles'].add(s['cycle_id'])
            for h in handlers.values():h['participated_cycles']=len(h['participated_cycles'])
            states=dict(conn.execute(sa.select(t.c.status,sa.func.count()).where(catalog.scope_expression(conn,user,'report.view',t)).group_by(t.c.status)).all())
            return out({'closed_cycles':len(cycles),'unique_tickets':len(unique),'duration_ms':duration,'average_ms':duration//len(cycles) if cycles else None,
                'categories':list(groups.values()),'handlers':list(handlers.values()),'states':states,'time_basis':'completed_at','timezone':'Asia/Shanghai',
                'start':start or None,'end':end or None})

    def quick_link_values(body):
        title=tickets.text(body.get('title'),'链接名称',120,True)
        raw=tickets.text(body.get('url'),'链接地址',1000,True).strip()
        if '://' not in raw:raw='http://'+raw
        parsed=urlparse(raw)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:fail('链接地址须为有效的 HTTP 或 HTTPS 地址，且不能包含账号密码')
        category=body.get('link_category')
        if category not in ('general','it'):fail('链接分类无效')
        icon=tickets.text(body.get('icon_text'),'图标',16).strip() or title[:1].upper()
        description=tickets.text(body.get('description'),'说明',300).strip() or None
        enabled=body.get('is_enabled',True)
        if not isinstance(enabled,bool):fail('启用状态无效')
        try:sort_order=int(body.get('sort_order',0))
        except (TypeError,ValueError):fail('排序须为整数')
        if not -9999<=sort_order<=9999:fail('排序须在 -9999 到 9999 之间')
        return {'title':title,'url':raw,'icon_text':icon,'description':description,'link_category':category,'is_enabled':enabled,'sort_order':sort_order}

    def quick_link_it_access(conn,user):
        ur,roles=T['user_roles'],T['roles']
        return bool(conn.execute(sa.select(ur.c.id).select_from(ur.join(roles,ur.c.role_id==roles.c.id)).where(
            ur.c.user_id==user['id'],roles.c.code.in_(('it','admin')),roles.c.is_archived==False).limit(1)).first()) or allow(conn,user,'quicklink.edit')

    @app.get('/api/quick-links')
    def quick_links(request:Request):
        with engine.begin() as conn:
            user=current_user(conn,request);can_manage=allow(conn,user,'quicklink.edit');it_access=quick_link_it_access(conn,user);t=T['quick_links']
            query=sa.select(t).where(t.c.is_archived==False)
            if not can_manage:query=query.where(t.c.is_enabled==True)
            if not it_access:query=query.where(t.c.link_category=='general')
            items=[dict(v) for v in conn.execute(query.order_by(t.c.link_category,t.c.sort_order,t.c.title,t.c.id)).mappings()]
            return out({'items':items,'can_manage':can_manage,'it_access':it_access})

    @app.post('/api/quick-links')
    def quick_link_create(request:Request,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'quicklink.edit');item=insert_row(conn,'quick_links',quick_link_values(body),user['id'])
            audit(conn,user,'quicklink.create','quick_links',item['id'],{'title':item['title'],'category':item['link_category']});return out(item,201)

    @app.put('/api/quick-links/{key}')
    def quick_link_update(request:Request,key:str,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'quicklink.edit');old=row(conn,'quick_links',key)
            if not old or old['is_archived']:fail('快捷链接不存在',404)
            if body.get('version')!=old['version']:fail('快捷链接已变化，请刷新后重试',409)
            values=quick_link_values(body);values.update(version=old['version']+1,updated_at=utcnow(),updated_by_user_id=user['id'])
            if conn.execute(T['quick_links'].update().where(T['quick_links'].c.id==key,T['quick_links'].c.version==old['version']).values(**values)).rowcount!=1:fail('快捷链接修改冲突',409)
            audit(conn,user,'quicklink.edit','quick_links',key,{'title':values['title'],'category':values['link_category']});return out(dict(row(conn,'quick_links',key)))

    @app.delete('/api/quick-links/{key}')
    def quick_link_delete(request:Request,key:str,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'quicklink.delete');old=row(conn,'quick_links',key)
            if not old or old['is_archived']:fail('快捷链接不存在',404)
            if body.get('version')!=old['version']:fail('快捷链接已变化，请刷新后重试',409)
            conn.execute(T['quick_links'].delete().where(T['quick_links'].c.id==key,T['quick_links'].c.version==old['version']))
            audit(conn,user,'quicklink.delete','quick_links',key,{'title':old['title']},tickets.text(body.get('reason'),'删除原因',300,True));return out({'ok':True})

    @app.get('/api/notifications')
    def notifications(request:Request):
        with engine.begin() as conn:
            user=current_user(conn,request);t=T['notifications']
            return out(list(conn.execute(sa.select(t).where(t.c.recipient_user_id==user['id']).order_by(t.c.created_at.desc(),t.c.id).limit(100)).mappings()))

    @app.get('/api/notifications/unread-count')
    def notification_unread_count(request:Request):
        with engine.begin() as conn:
            user=current_user(conn,request);t=T['notifications']
            count=conn.execute(sa.select(sa.func.count()).select_from(t).where(t.c.recipient_user_id==user['id'],t.c.read_at.is_(None))).scalar_one()
            return out({'unread_count':count})

    @app.post('/api/notifications/read-all')
    def mark_all_notifications_read(request:Request,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);t=T['notifications'];now=utcnow()
            result=conn.execute(t.update().where(t.c.recipient_user_id==user['id'],t.c.read_at.is_(None)).values(read_at=now))
            return out({'ok':True,'updated_count':result.rowcount,'unread_count':0})

    @app.post('/api/notifications/{key}/read')
    def mark_read(request:Request,key:str,body:dict):
        with engine.begin() as conn:
            user=current_user(conn,request);t=T['notifications']
            conn.execute(t.update().where(t.c.id==key,t.c.recipient_user_id==user['id']).values(read_at=utcnow()))
            count=conn.execute(sa.select(sa.func.count()).select_from(t).where(t.c.recipient_user_id==user['id'],t.c.read_at.is_(None))).scalar_one()
            return out({'ok':True,'unread_count':count})

    @app.get('/api/audit')
    def audit_list(request:Request,page:int=1,page_size:int=10):
        if page_size not in (10,20,50):fail('每页条数仅支持 10、20、50',422)
        with engine.begin() as conn:
            user=current_user(conn,request);require(conn,user,'audit.view');t=T['audit_logs']
            total=conn.execute(sa.select(sa.func.count()).select_from(t)).scalar_one()
            return out({'items':list(conn.execute(sa.select(t).order_by(t.c.occurred_at.desc(),t.c.id).offset((max(1,page)-1)*page_size).limit(page_size)).mappings()),'total':total,'page':max(page,1),'page_size':page_size})


