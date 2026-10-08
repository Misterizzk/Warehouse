"""Preview, export and print routing with temporary data; no physical print jobs."""
import tempfile
from pathlib import Path
from unittest.mock import patch
import tkinter as tk
from PIL import Image
from warehouse.ui import Application
from warehouse.labels import payload
import cv2
import numpy as np

with tempfile.TemporaryDirectory() as folder:
    root=tk.Tk()
    app=Application(root,Path(folder)/'demo.db')
    app.show('Data Barang')
    app.edit_batch()
    for key,value in dict(material='TEST-QR',description='QR test',plant='BHT',storage_location='PBHT',location_code='A-B01-K01-R01-T01',stock='5').items():
        app.editor.values[key].set(value)
    app.editor.save()
    root.update()
    key=app.table.selected
    preview=app.label_preview
    assert preview.winfo_exists() and preview.batch_id==key
    for scale in (96/72,120/72):
        root.tk.call('tk','scaling',scale)
        for size in ('1366x768','1920x1080'):
            root.geometry(size)
            preview.geometry('760x500')
            root.update()
            for button in preview.buttons:
                assert button.winfo_rootx()+button.winfo_width() <= preview.winfo_rootx()+preview.winfo_width()
                assert button.winfo_rooty()+button.winfo_height() <= preview.winfo_rooty()+preview.winfo_height()
    for full in (False,True):
        path=Path(folder)/f'export-{full}.png'
        with patch('warehouse.label_ui.filedialog.asksaveasfilename',return_value=str(path)):
            preview.download(full)
        with Image.open(path) as image:
            assert cv2.QRCodeDetector().detectAndDecode(np.array(image))[0]==payload(key)
    with patch('warehouse.label_ui.filedialog.asksaveasfilename',return_value=''):
        preview.download(True)
    with patch('warehouse.label_ui.webbrowser.open',return_value=True) as opened:
        preview.print_label()
        assert opened.call_args.args[0].startswith('file:')
    with patch('warehouse.label_ui.webbrowser.open',return_value=False):
        preview.print_label()
        assert 'Gagal' in preview.message.cget('text')
    preview.destroy()
    app.show_label('DEMO-0001')
    root.update()
    assert app.label_preview.batch_id=='DEMO-0001'
    app.close()
print('Stage 5 UI checks passed: automatic preview, existing batch, layout, export and print routing')
