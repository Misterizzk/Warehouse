"""Synthetic QR frames exercise confirmation without requiring a physical webcam."""
import tempfile
import tkinter as tk
from pathlib import Path
from unittest.mock import patch
from warehouse.ui import Application
from warehouse.camera import decode_frame
from test_camera_reports import qr_frame

import subprocess
import sys
import unittest


def run_workflow():
    with tempfile.TemporaryDirectory() as folder:
        root=tk.Tk()
        app=Application(root,Path(folder)/'demo.db')
        try:
            app.show('Pengecekan')
            page=app.session_page
            key=page.service.start('Faiz','Area A')
            page.open_session(key)
            page.open_camera()
            camera=app.camera_window
            root.update()
            frame=qr_frame()
            camera.process_frame(frame,decode_frame(frame))
            assert camera.candidate=='ID:DEMO-0001'
            assert not page.service.results(key)
            camera.confirm_button.invoke()
            assert len(page.service.results(key))==1
            assert (app.last_camera_frame==frame).all()
            assert len(page.table.rows)==1
            assert camera.confirm_button.cget('state')=='disabled'
            camera.next_scan()
            camera.process_frame(frame,decode_frame(frame))
            camera.confirm_button.invoke()
            assert len(page.service.results(key))==1
            camera.next_scan()
            bad=qr_frame('MISSING')
            camera.process_frame(bad,decode_frame(bad))
            assert camera.candidate is None
            assert camera.confirm_button.cget('state')=='disabled'
            assert (app.last_camera_frame==frame).all()
            camera.next_scan()
            camera.process_frame(frame,decode_frame(frame))
            page.service.finish(key)
            camera.confirm()
            assert 'Belum tersimpan' in camera.banner.cget('text')
            app.stop_camera()
            app.show('Dashboard')
            root.update()
            assert 'kamera tidak aktif' in app.dashboard_page.camera_banner.cget('text')
            assert 'camera' in app.dashboard_page.images
            app.show('Laporan')
            report=app.report_page
            report.filters['query'].set('Faiz')
            report.filters['status'].set('Selesai')
            report.refresh()
            assert report.table.get_children()==(str(key),)
            report.detail(key)
            for scale in (96/72,120/72):
                root.tk.call('tk','scaling',scale)
                for size in ('1366x768','1920x1080','1000x600'):
                    root.geometry(size)
                    root.update()
                    assert report.result_table.winfo_height()>70
                    for button in (report.preview_button,report.excel_button,report.pdf_button):
                        assert button.winfo_rootx()+button.winfo_width()<=root.winfo_rootx()+root.winfo_width()
            for kind in ('xlsx','pdf'):
                output=Path(folder)/('report.'+kind)
                with patch('warehouse.report_ui.filedialog.asksaveasfilename',return_value=str(output)):
                    report.export(kind)
                assert output.exists(),report.info.cget('text')
            report.preview()
            root.update()
            assert report.pdf_preview.document
            report.pdf_preview.move(1)
            report.pdf_preview.zoom.set('150%')
            report.pdf_preview.render()
            report.pdf_preview.destroy()
        finally:app.close()
    print('Stages 8/9 UI passed: QR confirmation/dedup/error, report filters, exports, PDF preview and desktop layout')


class Stage89WorkflowTest(unittest.TestCase):
    def test_camera_and_reports(self):
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve())],
            cwd=Path(__file__).resolve().parent,
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    run_workflow()
