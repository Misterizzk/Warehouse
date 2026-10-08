"""End-to-end GUI workflow on a disposable database and workbook."""
import tempfile
import time
from pathlib import Path
from datetime import date
from unittest.mock import patch
import tkinter as tk
from openpyxl import load_workbook
from warehouse.ui import Application
from warehouse.inventory_excel import write_inventory

from contextlib import ExitStack
import subprocess
import sys
import unittest


def close_if_open(window, close):
    """A closed Tk interpreter raises TclError instead of reporting exists=0."""
    try:
        if window.winfo_exists():
            close()
    except tk.TclError:
        pass


def run_workflow():
    with tempfile.TemporaryDirectory() as folder, ExitStack() as cleanup:
        root=tk.Tk()
        cleanup.callback(lambda r=root: close_if_open(r,r.destroy))
        app=Application(root,Path(folder)/'demo.db')
        cleanup.callback(lambda a=app: close_if_open(a.root,a.close))
        errors=[]
        root.report_callback_exception=lambda *args:errors.append(args)
        path=Path(folder)/'import.xlsx'
        write_inventory(path,app.db,True)
        book=load_workbook(path)
        book['Inventory'].append(['IMPORT-UI','000007','UI part','BHT','PBHT','A-B01-01-01',date.today(),3])
        book.save(path)
        book.close()
        app.show_excel()
        excel=app.excel_window
        with patch('warehouse.excel_ui.filedialog.askopenfilename',return_value=str(path)):
            excel.load()
        deadline=time.monotonic()+10
        while excel.pending is not None and time.monotonic()<deadline:
            root.update()
            time.sleep(.02)
        assert len(excel.checked)==1,excel.info.cget('text')
        assert excel.save_button.cget('state')=='normal'
        original_location=excel.source[0]['values']['location_code']
        excel.source[0]['values']['location_code']='UNKNOWN'
        excel.render_preview()
        assert excel.save_button.cget('state')=='disabled'
        excel.source[0]['values']['location_code']=original_location
        excel.render_preview()
        excel.save_button.invoke()
        assert app.inventory.list_batches(query='IMPORT-UI')
        assert excel.save_button.cget('state')=='disabled'
        output=Path(folder)/'export.xlsx'
        with patch('warehouse.excel_ui.filedialog.asksaveasfilename',return_value=str(output)):
            excel.export(False)
        assert output.exists()
        excel.destroy()
        app.show('Pengecekan')
        page=app.session_page
        page.start_form()
        page.start_vars['officer'].set('Faiz')
        page.start_vars['area'].set('Area A')
        page.start_save.invoke()
        key=page.session_id
        assert key
        page.code.set('ID:IMPORT-UI')
        page.add_button.invoke()
        assert len(page.table.rows)==1
        page.code.set('IMPORT-UI')
        page.add_button.invoke()
        assert len(page.table.rows)==1
        page.table.choose('IMPORT-UI')
        page.item_detail()
        page.note_text.insert('end','Periksa kemasan')
        page.note_save.invoke()
        assert page.service.results(key)[0]['note']=='Periksa kemasan'
        page.note_dialog()
        page.note_text.insert('end','Pengecekan pagi')
        page.note_save.invoke()
        for scale in (96/72,120/72):
            root.tk.call('tk','scaling',scale)
            for width,height in ((1366,768),(1920,1080),(1000,600)):
                root.geometry(f'{width}x{height}')
                root.update()
                minimum_height = 70 if height >= 768 else 25
                assert page.table.winfo_height()>minimum_height,(scale,width,height,page.table.winfo_height())
                for widget in (page.finish_button,page.add_button,page.item_note_button):
                    assert widget.winfo_rooty()+widget.winfo_height() <= root.winfo_rooty()+root.winfo_height(),(scale,width,height,widget.cget('text'))
                    assert widget.winfo_rootx()+widget.winfo_width() <= root.winfo_rootx()+root.winfo_width()
        assert not errors,errors
        app.close()
        root=tk.Tk()
        cleanup.callback(lambda r=root: close_if_open(r,r.destroy))
        app=Application(root,Path(folder)/'demo.db')
        cleanup.callback(lambda a=app: close_if_open(a.root,a.close))
        app.show('Pengecekan')
        page=app.session_page
        page.list_table.selection_set(str(key))
        page.open_selected()
        assert page.table.rows[0]['note']=='Periksa kemasan'
        assert page.service.get(key)['note']=='Pengecekan pagi'
        with patch('warehouse.session_ui.messagebox.askyesno',return_value=True):
            page.finish_button.invoke()
        assert page.service.get(key)['status']=='Selesai'
        assert page.add_button.cget('state')=='disabled'
        page.note_dialog()
        assert page.note_save.cget('state')=='disabled'
        page.note_window.destroy()
        app.close()
    print('Stages 6/7 UI passed: import preview/export, session, notes, restart, locking and desktop layout')


class Stage67WorkflowTest(unittest.TestCase):
    def test_import_session_restart_and_layout(self):
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve())],
            cwd=Path(__file__).resolve().parent,
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    run_workflow()
