"""Local operator commands. Secrets are prompted, never passed on the command line."""
import argparse
import getpass
from pathlib import Path
import sys
import sqlalchemy as sa
from .database import settings,database_url,make_engine
from .security import seed


def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('init-admin',help='Initialize permissions and administrator after alembic upgrade head')
    restore=sub.add_parser('restore-local',help='Decrypt a local backup to a NEW SQLite file; stop app first')
    restore.add_argument('backup',type=Path);restore.add_argument('--target',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='init-admin':
        config=settings();engine=make_engine(database_url(config))
        if not sa.inspect(engine).has_table('users'):parser.error('Run alembic upgrade head first.')
        with engine.begin() as conn:seed(conn,config['data_dir'])
        print('Administrator and permissions initialized. Handover file, if generated: data/business/initial-account.txt')
        engine.dispose()
    elif args.command=='restore-local':
        if args.target.exists():parser.error('Target must not already exist. Never overwrite an active database.')
        raw=args.backup.read_bytes()
        if not raw.startswith(b'ITBK1') or len(raw)<50:parser.error('Invalid encrypted backup.')
        password=getpass.getpass('Backup password: ')
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.exceptions import InvalidTag
        key=PBKDF2HMAC(algorithm=hashes.SHA256(),length=32,salt=raw[5:21],iterations=600000).derive(password.encode())
        try:plain=AESGCM(key).decrypt(raw[21:33],raw[33:],b'ITBK1')
        except InvalidTag:parser.error('Wrong backup password or damaged backup.')
        if not plain.startswith(b'SQLite format 3\x00'):parser.error('Backup is not a SQLite database.')
        args.target.parent.mkdir(parents=True,exist_ok=True)
        with args.target.open('xb') as f:f.write(plain)
        import sqlite3
        with sqlite3.connect(args.target) as conn:
            if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok':parser.error('Restored database integrity check failed; do not switch to it.')
            # Existing sessions must not become valid again after restoration.
            conn.execute('UPDATE user_sessions SET revoked_at=CURRENT_TIMESTAMP')
        print('Restored and checked NEW database; sessions revoked. Restore files separately before switching configuration.')


if __name__=='__main__':main()
