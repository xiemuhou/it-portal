"""Isolated native rendering/Office automation: never run macros or modify original files."""
import argparse
import os
from pathlib import Path
import sys


def convert(source, output):
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    app = presentation = None
    try:
        app = win32com.client.DispatchEx('PowerPoint.Application')
        app.AutomationSecurity = 3  # msoAutomationSecurityForceDisable
        app.DisplayAlerts = 1  # ppAlertsNone
        presentation = app.Presentations.Open(str(source), -1, 0, 0)
        presentation.SaveAs(str(output), 32)  # ppSaveAsPDF; avoids optional COM PrintRange marshalling
    finally:
        if presentation is not None:
            presentation.Close()
        if app is not None:
            # Leave any other open presentation alone, including the user's existing documents.
            try:
                if app.Presentations.Count == 0:
                    app.Quit()
            except Exception:
                pass
        presentation = app = None
        pythoncom.CoUninitialize()


def render(source, output, page):
    import pymupdf
    with pymupdf.open(source) as document:
        if not 1 <= page <= len(document):
            raise ValueError('页码超出范围')
        sheet = document[page - 1]
        # Keep large engineering drawings bounded, while providing readable ordinary pages.
        scale = min(2, 2600 / max(sheet.rect.width, sheet.rect.height))
        pixmap = sheet.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        temporary = output.with_name(output.stem + '.tmp.png')
        pixmap.save(temporary)
        os.replace(temporary, output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['convert', 'render'])
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--page', type=int, default=1)
    args = parser.parse_args()
    try:
        source, output = args.source.resolve(), args.output.resolve()
        if args.operation == 'convert':
            convert(source, output)
        else:
            render(source, output, args.page)
    except Exception as exc:
        sys.stderr.buffer.write(str(exc).encode('utf-8', errors='replace'))
        sys.exit(1)
