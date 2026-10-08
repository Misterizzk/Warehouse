"""Run separately on a desktop: python test_foundation_ui.py."""
import tempfile
from pathlib import Path
import tkinter as tk
from warehouse.ui import Application

with tempfile.TemporaryDirectory() as folder:
    root=tk.Tk()
    root.withdraw()
    app=Application(root,Path(folder)/'demo.db')
    for scale in (96/72,120/72):
        root.tk.call('tk','scaling',scale)
        for width,height in ((1366,768),(1920,1080),(1000,600)):
            root.geometry(f'{width}x{height}')
            root.deiconify()
            root.update()
            for page in app.nav:
                app.show(page)
                root.update()
                assert app.body.winfo_height()>100
                for button in app.nav.values():
                    assert button.winfo_rooty()+button.winfo_height() <= root.winfo_rooty()+root.winfo_height()
                if page=='Data Barang':
                    assert len(app.table.rows)==50
                    app.table.choose('DEMO-0001')
                    root.update()
                    assert 'DEMO-0001' in app.detail.get()
                    assert app.table.winfo_height()>70
                    app.close_detail()
                    root.update()
                    assert app.drawer is None
                    for key in ('DEMO-0026','DEMO-0041'):
                        app.table.choose(key)
                        root.update()
                        row,badge=app.table.widgets[key]
                        assert badge.cget('bg') != row.cget('bg')
    app.close()
print('UI navigation, resize, scale and selection checks passed')
