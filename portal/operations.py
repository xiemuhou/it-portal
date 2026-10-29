"""File durability, structured logs, and scheduled data retention."""
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
import hashlib
import json
import logging
import os
import time

import sqlalchemy as sa


_REQUEST_ID = ContextVar('portal_request_id', default='')


def set_request_id(value):
    return _REQUEST_ID.set(value)


def reset_request_id(token):
    _REQUEST_ID.reset(token)


def current_request_id():
    return _REQUEST_ID.get() or os.urandom(16).hex()


class JsonFormatter(logging.Formatter):
    def format(self, record):
        item = {
            'timestamp': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
            'level': record.levelname,
            'logger': record.name,
            'event': getattr(record, 'event', record.getMessage()),
        }
        for name in ('request_id','method','path','status','duration_ms','client','job','counts','error_type'):
            value = getattr(record, name, None)
            if value is not None:item[name] = value
        if record.exc_info:
            item['exception'] = self.formatException(record.exc_info)
        return json.dumps(item, ensure_ascii=False, default=str)


def configure_logging(data_dir, retention_days=90):
    folder = Path(data_dir) / 'logs';folder.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger('it_portal');logger.setLevel(logging.INFO);logger.propagate=False
    for handler in list(logger.handlers):
        handler.close();logger.removeHandler(handler)
    handler = TimedRotatingFileHandler(folder/'portal.jsonl', when='midnight', interval=1,
        backupCount=max(1,int(retention_days)), encoding='utf-8', utc=True)
    handler.setFormatter(JsonFormatter());logger.addHandler(handler)
    cleanup_logs(folder,retention_days)
    return logger


def close_logging(logger):
    for handler in list(logger.handlers):
        handler.flush();handler.close();logger.removeHandler(handler)


def cleanup_logs(folder, retention_days=90, now=None):
    cutoff=(now or datetime.now(timezone.utc))-timedelta(days=max(1,int(retention_days)))
    removed=0
    for path in Path(folder).glob('portal.jsonl.*'):
        try:
            modified=datetime.fromtimestamp(path.stat().st_mtime,timezone.utc)
            if modified<cutoff:path.unlink();removed+=1
        except FileNotFoundError:pass
    return removed


@dataclass(frozen=True)
class StagedFile:
    storage_key: str
    purpose: str
    temp_path: Path
    final_path: Path
    size_bytes: int
    sha256: str


class FileStorage:
    PURPOSE_ROOT={'knowledge':'knowledge','announcement':'attachments','ticket_attachment':'attachments'}

    def __init__(self,data_dir):
        self.root=Path(data_dir).resolve()
        self.staging=(self.root/'.staging').resolve()
        self.reports=(self.root/'reports'/'file-integrity').resolve()
        self.staging.mkdir(parents=True,exist_ok=True);self.reports.mkdir(parents=True,exist_ok=True)
        for name in set(self.PURPOSE_ROOT.values()):(self.root/name).mkdir(parents=True,exist_ok=True)

    def final_path(self,storage_key,purpose):
        name=Path(storage_key).name
        if name!=storage_key:raise ValueError('Invalid storage key')
        directory=(self.root/self.PURPOSE_ROOT[purpose]).resolve();path=(directory/name).resolve()
        if path.parent!=directory:raise ValueError('Invalid storage path')
        return path

    def stage(self,raw,extension,purpose,storage_key):
        if purpose not in self.PURPOSE_ROOT:raise ValueError('Unsupported file purpose')
        key=Path(storage_key).name
        if key!=storage_key or not key.endswith(extension):raise ValueError('Invalid storage key')
        temp=(self.staging/(key+'.part')).resolve()
        if temp.parent!=self.staging:raise ValueError('Invalid staging path')
        with temp.open('xb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        return StagedFile(key,purpose,temp,self.final_path(key,purpose),len(raw),hashlib.sha256(raw).hexdigest())

    def discard(self,staged):
        staged.temp_path.unlink(missing_ok=True)

    def finalize(self,engine,tables,file_id,staged):
        staged.final_path.parent.mkdir(parents=True,exist_ok=True)
        last=None
        for attempt in range(3):
            try:os.replace(staged.temp_path,staged.final_path);last=None;break
            except OSError as exc:
                last=exc;time.sleep(0.05*(attempt+1))
        if last:raise last
        with engine.begin() as conn:
            table=tables['file_objects'];old=conn.execute(sa.select(table).where(table.c.id==file_id)).mappings().first()
            if not old:raise RuntimeError('File database record disappeared after commit')
            conn.execute(table.update().where(table.c.id==file_id,table.c.file_state=='pending').values(
                file_state='ready',updated_at=_utcnow(),version=table.c.version+1))

    def delete(self,storage_key,purpose):
        if purpose in self.PURPOSE_ROOT:self.final_path(storage_key,purpose).unlink(missing_ok=True)
        temp=(self.staging/(Path(storage_key).name+'.part')).resolve()
        if temp.parent==self.staging:temp.unlink(missing_ok=True)

    def reconcile(self,engine,tables,now=None):
        now=now or _utcnow();objects=[]
        with engine.begin() as conn:objects=[dict(v) for v in conn.execute(sa.select(tables['file_objects'])).mappings()]
        known=set();recovered=[];missing=[];mismatch=[];stale_pending=[]
        for item in objects:
            purpose=item['purpose']
            if purpose not in self.PURPOSE_ROOT:continue
            key=item['storage_key'];known.add((purpose,key));final=self.final_path(key,purpose);temp=self.staging/(key+'.part')
            candidate=final if final.is_file() else temp if temp.is_file() else None
            if item['file_state']=='pending' and candidate:
                size=candidate.stat().st_size;digest=_sha256(candidate)
                if size==item['size_bytes'] and digest==item['sha256']:
                    if candidate==temp:os.replace(temp,final)
                    with engine.begin() as conn:
                        table=tables['file_objects'];conn.execute(table.update().where(table.c.id==item['id'],table.c.file_state=='pending').values(
                            file_state='ready',updated_at=now,version=table.c.version+1))
                    recovered.append(key);continue
                mismatch.append({'storage_key':key,'purpose':purpose,'state':'pending'})
            if item['file_state']=='pending' and not candidate:
                if item['created_at']<now-timedelta(hours=1):stale_pending.append({'storage_key':key,'purpose':purpose})
                continue
            if item['file_state']=='ready':
                if not final.is_file():missing.append({'storage_key':key,'purpose':purpose});continue
                if final.stat().st_size!=item['size_bytes'] or _sha256(final)!=item['sha256']:
                    mismatch.append({'storage_key':key,'purpose':purpose,'state':'ready'})
        orphans=[]
        for directory_name in set(self.PURPOSE_ROOT.values()):
            directory=self.root/directory_name
            for path in directory.iterdir():
                owners=[purpose for purpose,name in self.PURPOSE_ROOT.items() if name==directory_name]
                if path.is_file() and not any((purpose,path.name) in known for purpose in owners):
                    orphans.append({'storage_key':path.name,'directory':directory_name})
        known_keys={item['storage_key'] for item in objects}
        orphan_staging=[p.name for p in self.staging.glob('*.part') if p.name[:-5] not in known_keys]
        knowledge_stems={Path(key).stem for purpose,key in known if purpose=='knowledge'}
        assets_root=self.root/'knowledge-assets'
        orphan_assets=[p.name for p in assets_root.iterdir() if p.is_dir() and p.name not in knowledge_stems] if assets_root.is_dir() else []
        secret_key=self.root/'wifi-secrets.key'
        report={'checked_at':now.isoformat()+'Z','database_objects':len(objects),'recovered_pending':recovered,
            'missing_files':missing,'hash_mismatches':mismatch,'stale_pending':stale_pending,
            'orphan_files':orphans,'orphan_staging':orphan_staging,'orphan_knowledge_assets':orphan_assets,
            'credential_key':{'exists':secret_key.is_file(),'size_bytes':secret_key.stat().st_size if secret_key.is_file() else None}}
        day=self.reports/(now.date().isoformat()+'.json');_atomic_json(day,report);_atomic_json(self.reports/'latest.json',report)
        return report


def purge_expired(engine,tables,audit_days=180,notification_days=180,now=None,batch_size=1000):
    now=now or _utcnow();counts={}
    for name,column,days in [('notifications','created_at',notification_days),('audit_logs','occurred_at',audit_days)]:
        cutoff=now-timedelta(days=max(1,int(days)));total=0;table=tables[name]
        while True:
            with engine.begin() as conn:
                ids=list(conn.execute(sa.select(table.c.id).where(table.c[column]<cutoff).order_by(table.c[column]).limit(batch_size)).scalars())
                if ids:total+=conn.execute(table.delete().where(table.c.id.in_(ids))).rowcount
            if len(ids)<batch_size:break
        counts[name]=total
    return counts


def _sha256(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path,value):
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(temp,path)


def _utcnow():
    value=datetime.now(timezone.utc)
    return value.replace(tzinfo=None,microsecond=(value.microsecond//1000)*1000)
