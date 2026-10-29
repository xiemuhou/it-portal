"""Local document discovery, immutable preview snapshots and background Office conversion."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from urllib.parse import quote
import zipfile
from xml.etree import ElementTree

SUPPORTED = {'.html', '.htm', '.pdf', '.ppt', '.pptx'}
_PREPARER = ThreadPoolExecutor(max_workers=1, thread_name_prefix='knowledge-preview')
_JOBS = {}
_LOCK = threading.RLock()
_META = {}
WORKER = Path(__file__).with_name('document_worker.py')


def quiet_process():
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}


def pdf_details(path):
    from pypdf import PdfReader
    reader = PdfReader(path)
    try:
        if reader.is_encrypted and not reader.decrypt(''):
            raise ValueError('此 PDF 已加密，请联系 IT 提供可预览的版本')
        count = len(reader.pages)
        if not count:
            raise ValueError('PDF 没有可显示的页面')
        return count
    finally:
        reader.close()


class KnowledgeLibrary:
    def __init__(self, root, cache):
        self.root = Path(root).resolve()
        self.cache = Path(cache).resolve()

    def resolve(self, name):
        if not isinstance(name, str) or not name or name in ['.', '..'] or '/' in name or '\\' in name or '\x00' in name:
            raise FileNotFoundError('文件名称无效')
        path = (self.root / name).resolve()
        if not path.is_relative_to(self.root) or not path.is_file() or path.suffix.lower() not in SUPPORTED:
            raise FileNotFoundError('知识库文件不存在或格式不支持')
        return path

    def version(self, path):
        stat = path.stat()
        return hashlib.sha256(f'{path}\0{stat.st_mtime_ns}\0{stat.st_size}'.encode()).hexdigest()[:32]

    def describe(self, path):
        key = self.version(path)
        with _LOCK:
            if (str(self.cache), key) in _META:
                return dict(_META[(str(self.cache), key)])
        kind = path.suffix[1:].upper()
        pages, issue = None, ''
        if kind == 'PDF':
            try:
                pages = pdf_details(path)
            except Exception as exc:
                issue = str(exc)[:180]
        elif kind == 'PPTX':
            try:
                with zipfile.ZipFile(path) as package:
                    tree = ElementTree.fromstring(package.read('ppt/presentation.xml'))
                    pages = len(tree.findall('.//{http://schemas.openxmlformats.org/presentationml/2006/main}sldId'))
            except Exception:
                issue = '无法读取演示文稿结构；阅读时会尝试使用本机转换器'
        result = {
            'id': path.name, 'title': path.stem, 'category': '未分类',
            'summary': f'{kind} 文档' + (f' · {pages} 页' if pages else '') + (' · 首次阅读自动转换预览' if kind in ['PPT', 'PPTX'] else ' · 滚动查看完整内容'),
            'updated': datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d'),
            'minutes': str(max(1, ((pages or 10) + 1) // 2)), 'pages': pages,
            'mode': 'pdf', 'file_type': kind, 'url': '/knowledge/' + quote(path.name),
            'reader_url': '/read?file=' + quote(path.name), 'metadata_issue': issue,
        }
        with _LOCK:
            _META[(str(self.cache), key)] = result
            if len(_META) > 1000:
                oldest = next(iter(_META))
                _META.pop(oldest, None)
        return dict(result)

    def _job(self, path):
        key = self.version(path)
        identity = (str(self.cache), key)
        folder = self.cache / key
        with _LOCK:
            if identity not in _JOBS:
                manifest = folder / 'ready.json'
                if manifest.is_file() and (folder / 'preview.pdf').is_file():
                    try:
                        data = json.loads(manifest.read_text(encoding='utf-8'))
                        if isinstance(data.get('pages'), int) and data['pages'] > 0:
                            _JOBS[identity] = {'status':'ready', 'pages':data['pages'], 'message':'预览已就绪', 'lock':threading.Lock()}
                    except (ValueError, OSError):
                        pass
                if identity not in _JOBS:
                    _JOBS[identity] = {'status':'processing', 'pages':None, 'message':'正在生成本地预览，首次转换可能需要一些时间', 'lock':threading.Lock()}
                    _PREPARER.submit(self._prepare, path, key, identity, folder)
            return key, identity, folder

    def _prepare(self, path, key, identity, folder):
        try:
            folder.mkdir(parents=True, exist_ok=True)
            staged = folder / ('original' + path.suffix.lower())
            shutil.copyfile(path, staged)
            if self.version(path) != key:
                raise ValueError('源文件在读取时发生变化，请重新打开阅读窗口')
            output = folder / 'preview.pdf'
            if path.suffix.lower() == '.pdf':
                os.replace(staged, output)
            else:
                libreoffice = os.getenv('IT_PORTAL_LIBREOFFICE') or shutil.which('soffice') or shutil.which('libreoffice')
                if libreoffice:
                    profile = (folder / 'office-profile').as_uri()
                    command = [libreoffice, '-env:UserInstallation=' + profile, '--headless', '--convert-to', 'pdf', '--outdir', str(folder), str(staged)]
                    result = subprocess.run(command, capture_output=True, timeout=120, **quiet_process())
                    converted = staged.with_suffix('.pdf')
                    if result.returncode or not converted.is_file():
                        raise ValueError('LibreOffice 转换失败，请确认文件可以正常打开')
                    os.replace(converted, output)
                elif os.name == 'nt':
                    result = subprocess.run([sys.executable, str(WORKER), 'convert', str(staged), str(output)], capture_output=True, timeout=120, **quiet_process())
                    if result.returncode:
                        message = result.stderr.decode('utf-8', errors='replace').strip()
                        raise ValueError(message[-300:] or 'PowerPoint 转换失败，请确认已安装并可正常使用 PowerPoint')
                else:
                    raise ValueError('此服务器未配置 PowerPoint 或 LibreOffice，请联系 IT 配置转换器')
            count = pdf_details(output)
            temporary = folder / 'ready.tmp'
            temporary.write_text(json.dumps({'pages':count}, ensure_ascii=False), encoding='utf-8')
            os.replace(temporary, folder / 'ready.json')
            with _LOCK:
                _JOBS[identity].update(status='ready', pages=count, message='预览已就绪')
        except subprocess.TimeoutExpired:
            with _LOCK:
                _JOBS[identity].update(status='error', message='文档转换超时，请稍后重试')
        except Exception as exc:
            with _LOCK:
                _JOBS[identity].update(status='error', message=str(exc)[:350])

    def info(self, name, retry=False):
        path = self.resolve(name)
        if retry:
            identity = (str(self.cache), self.version(path))
            with _LOCK:
                if _JOBS.get(identity, {}).get('status') == 'error':
                    _JOBS.pop(identity, None)
        key, identity, folder = self._job(path)
        with _LOCK:
            job = _JOBS[identity]
            return {'version':key, 'status':job['status'], 'pages':job['pages'], 'message':job['message']}

    def preview_pdf(self, name):
        path = self.resolve(name)
        _, identity, folder = self._job(path)
        with _LOCK:
            if _JOBS[identity]['status'] != 'ready':
                raise ValueError('预览尚未生成，请稍后再试')
        return folder / 'preview.pdf'

    def page(self, name, number, version=''):
        path = self.resolve(name)
        key, identity, folder = self._job(path)
        with _LOCK:
            job = _JOBS[identity]
            if version and version != key:
                raise ValueError('文档已更新，请刷新阅读窗口')
            if job['status'] != 'ready':
                raise ValueError('预览尚未生成')
            if number < 1 or number > job['pages']:
                raise FileNotFoundError('页码超出文档范围')
            render_lock = job['lock']
        output = folder / f'page-{number}.png'
        with render_lock:
            if not output.is_file():
                try:
                    result = subprocess.run([sys.executable, str(WORKER), 'render', str(folder / 'preview.pdf'), str(output), '--page', str(number)], capture_output=True, timeout=60, **quiet_process())
                except subprocess.TimeoutExpired:
                    raise ValueError('页面渲染超时，请刷新重试') from None
                if result.returncode or not output.is_file():
                    raise ValueError('该页渲染失败，请刷新重试')
        return output
