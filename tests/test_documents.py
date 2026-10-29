import hashlib
from pathlib import Path
import tempfile
import time
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from document_library import KnowledgeLibrary
import pymupdf


class DocumentTests(unittest.TestCase):
    def test_pdf_preview_pages_version_and_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / '示例.pdf'
            with pymupdf.open() as doc:
                doc.new_page().insert_text((40, 40), 'Page one')
                doc.new_page().insert_text((40, 40), 'Page two')
                doc.save(source)
            original = hashlib.sha256(source.read_bytes()).hexdigest()
            library = KnowledgeLibrary(root, root / 'cache')
            self.assertEqual(library.describe(source)['pages'], 2)
            deadline = time.monotonic() + 15
            while (info := library.info(source.name))['status'] == 'processing' and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertEqual(info['status'], 'ready', info)
            for number in [1, 2]:
                image = library.page(source.name, number, info['version'])
                self.assertEqual(image.read_bytes()[:8], b'\x89PNG\r\n\x1a\n')
            with self.assertRaises(FileNotFoundError):
                library.page(source.name, 3)
            with self.assertRaises(ValueError):
                library.page(source.name, 1, 'outdated')
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), original)
            source.touch()
            self.assertNotEqual(library.version(source), info['version'])

    def test_reject_traversal_and_unsupported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'private.txt').write_text('secret')
            library = KnowledgeLibrary(root, root / 'cache')
            for name in ['../private.txt', 'sub/file.pdf', '..\\private.pdf', 'private.txt', 'missing.pdf']:
                with self.assertRaises(FileNotFoundError):
                    library.resolve(name)
