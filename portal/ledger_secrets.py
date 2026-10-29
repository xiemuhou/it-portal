"""Recoverable ledger credentials, encrypted with a deployment-local key."""
import os
from threading import Lock
from pathlib import Path
from cryptography.fernet import Fernet,InvalidToken
from .database import settings
from .security import fail
_key_lock=Lock()


def cipher(conn,create=True):
    folder=Path(getattr(conn.engine,'ledger_data_dir',settings()['data_dir']))
    folder.mkdir(parents=True,exist_ok=True);path=folder/'wifi-secrets.key'
    with _key_lock:
        if not path.exists():
            if not create:fail('凭据加密密钥文件缺失，请恢复部署密钥文件',503)
            try:
                fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'wb') as file:file.write(Fernet.generate_key())
            except FileExistsError:pass
        return Fernet(path.read_bytes())


def encrypt(conn,value):
    return cipher(conn).encrypt(value.encode('utf-8')).decode('ascii') if value else None


def decrypt(conn,value):
    if not value:return None
    try:return cipher(conn,create=False).decrypt(value.encode('ascii')).decode('utf-8')
    except InvalidToken:fail('凭据解密失败，请检查部署密钥文件',503)
