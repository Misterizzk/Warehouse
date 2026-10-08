import tempfile
from pathlib import Path
import tkinter as tk
from warehouse.ui import Application

with tempfile.TemporaryDirectory() as folder:
    root=tk.Tk()
    callback_errors=[]
    root.report_callback_exception=lambda *args: callback_errors.append(args)
    app=Application(root,Path(folder)/'demo.db')
    for size in ('1366x768','1920x1080','1000x600'):
        root.geometry(size)
        app.show_locations()
        root.update()
        page=app.location_page
        assert len(page.table.get_children())==162
        assert page.table.winfo_height()>100
    page.query.set('A-B01')
    assert len(page.table.get_children())==27
    page.open_form()
    root.update()
    for var,value in zip(page.values,('A','B01')):var.set(value)
    assert str(page.save_button['state'])=='disabled'
    page.save()
    assert 'sudah tersedia' in page.error.get()
    for var,value in zip(page.values,('C','B04')):var.set(value)
    assert 'C-B04-K01-R01-T01' in page.preview.get()
    page.save()
    root.update()
    assert page.table.selection()==('C-B04-K01-R01-T01',)
    assert len(page.table.get_children())==189
    app.show('Data Barang')
    root.update()
    assert len(app.rows)==50
    assert not callback_errors,callback_errors
    app.close()
print('Location UI: filter, duplicate, save, selection and navigation passed')
