"""Preview and explicit export/print actions. No printer job on save."""
import tempfile
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog
from PIL import Image, ImageTk
from .labels import label_image, qr_image, print_document, resolve, payload
from .ui import BG, PANEL, FG, MUTED, BLUE
from .theme import (
    ACCENT_HOVER, DANGER, EDGE, SUCCESS, SURFACE_ALT,
)


class LabelPreview(tk.Toplevel):
    def __init__(self, app, batch_id):
        source = label_image(resolve(app.db,payload(batch_id)))
        super().__init__(app.root)
        self.app, self.batch_id = app, batch_id
        self.title('Label QR barang')
        self.configure(bg=BG)
        self.geometry('760x500')
        self.minsize(660, 460)
        self.transient(app.root)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        header=tk.Frame(self,bg=BG)
        header.grid(row=0,column=0,sticky='ew',padx=24,pady=(18,8))
        tk.Label(header, text='Label QR barang', bg=BG, fg=FG,
                 font=('Segoe UI',20,'bold')).pack(anchor='w')
        tk.Label(header,text='Batch '+batch_id+'  •  Pilih simpan gambar atau buka pratinjau cetak.',
                 bg=BG,fg=MUTED,font=('Segoe UI',10)).pack(anchor='w',pady=(2,0))
        self.preview = tk.Label(self,bg=PANEL,highlightbackground=EDGE,highlightthickness=1)
        self.preview.grid(row=1,column=0,sticky='nsew',padx=24,pady=8)
        self.source = source
        self.preview.bind('<Configure>',self.resize)
        self.message=tk.Label(self,text='QR berisi ID batch tetap. Label berukuran 100 × 50 mm; lokasi pada gambar mengikuti data saat label dibuat.',
                              bg=BG,fg=MUTED,font=('Segoe UI',10),wraplength=700,justify='left',anchor='w')
        self.message.grid(row=2,column=0,sticky='w',padx=24,pady=8)
        actions=tk.Frame(self,bg=BG)
        actions.grid(row=3,column=0,sticky='ew',padx=24,pady=16)
        self.buttons=[]
        for text,command in [('Simpan QR (PNG)',lambda:self.download(False)),('Simpan label (PNG)',lambda:self.download(True)),
                             ('Pratinjau cetak',self.print_label),('Tutup',self.destroy)]:
            button=tk.Button(actions,text=text,command=command,bg=BLUE if text=='Pratinjau cetak' else PANEL,fg=FG,
                             activebackground=ACCENT_HOVER if text=='Pratinjau cetak' else SURFACE_ALT,activeforeground=FG,relief='flat',
                             padx=12,pady=11,font=('Segoe UI',10),cursor='hand2')
            button.pack(side='left',padx=(0,8))
            self.buttons.append(button)
        self.bind('<Escape>',lambda e:self.destroy())

    def current(self):
        return resolve(self.app.db,payload(self.batch_id))

    def resize(self,event):
        width=min(event.width,max(1,event.height)*2)
        self.photo=ImageTk.PhotoImage(self.source.resize((max(1,width),max(1,width//2)),Image.Resampling.LANCZOS))
        self.preview.configure(image=self.photo)

    def download(self, full_label):
        path=filedialog.asksaveasfilename(parent=self,title='Simpan label' if full_label else 'Simpan QR',
            defaultextension='.png',filetypes=[('Gambar PNG','*.png')],
            initialfile=('label_' if full_label else 'qr_')+self.batch_id+'.png')
        if not path:return
        try:
            image=label_image(self.current()) if full_label else qr_image(self.batch_id)
            image.save(path,format='PNG',dpi=(304.8,304.8))
            self.message.configure(text='Tersimpan: '+path,fg=SUCCESS)
        except (OSError,ValueError) as exc:
            self.message.configure(text='Gagal menyimpan: '+str(exc),fg=DANGER)

    def print_label(self):
        try:
            # Dedicated file per click; no overwritten document during print preview.
            with tempfile.NamedTemporaryFile(mode='w',suffix='.html',prefix='warehouse_label_',encoding='utf-8',delete=False) as file:
                file.write(print_document(self.current()))
            url=Path(file.name).as_uri()
            if not webbrowser.open(url):
                raise OSError('Browser tidak dapat dibuka. Unduh label PNG lalu cetak dari aplikasi gambar.')
            self.message.configure(text='Halaman cetak dibuka di browser. Klik Cetak, lalu pilih printer dan ukuran kertas.',fg=SUCCESS)
        except (OSError,ValueError) as exc:
            self.message.configure(text='Gagal membuka cetak: '+str(exc),fg=DANGER)
