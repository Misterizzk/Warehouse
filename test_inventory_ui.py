"""Isolated desktop CRUD and layout checks; never changes the user's database."""
import tempfile
from pathlib import Path
import tkinter as tk
from warehouse.ui import Application

with tempfile.TemporaryDirectory() as folder:
    root = tk.Tk()
    app = Application(root, Path(folder)/'demo.db')
    for scale in (96/72, 120/72):
        root.tk.call('tk','scaling',scale)
        for width, height in ((1366,768),(1920,1080),(1000,600)):
            root.geometry(f'{width}x{height}')
            app.show('Data Barang')
            root.update()
            assert app.table.winfo_height() > 100
            app.add_button.invoke()
            root.update()
            editor = app.editor
            assert editor.save_button.winfo_rooty()+editor.save_button.winfo_height() <= editor.winfo_rooty()+editor.winfo_height()
            assert editor.inputs['stock'].winfo_rooty()+editor.inputs['stock'].winfo_height() < editor.save_button.winfo_rooty()
            editor.destroy()
    app.edit_batch()
    editor = app.editor
    editor.save()
    assert editor.errors['material'].cget('text')
    for key, value in dict(material='TEST-UI',description='UI new batch',plant='BHT',storage_location='PBHT',location_code='A-B01-K01-R01-T01',stock='3').items():
        editor.values[key].set(value)
    editor.save()
    root.update()
    key = app.table.selected
    assert key.startswith('BAT-')
    assert len(app.table.rows) == 51
    app.edit_batch(next(r for r in app.rows if r['id']==key))
    app.editor.values['stock'].set('9')
    app.editor.save()
    root.update()
    assert next(r for r in app.rows if r['id']==key)['stock'] == 9
    app.search.set('TEST-UI')
    app.status_filter.set('Normal')
    app.location_filter.set('A-B01-K01-R01-T01')
    root.update()
    assert len(app.table.rows) == 1
    app.search.set('no matches')
    root.update()
    assert not app.table.rows
    app.table.move(1)
    app.close()
    root = tk.Tk()
    app = Application(root, Path(folder)/'demo.db')
    assert app.inventory.list_batches(query=key)[0]['stock'] == 9
    app.close()
print('Stage 4 UI checks passed: CRUD, filters, restart, layout and scaling')
