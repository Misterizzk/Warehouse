"""Desktop inventory import preview; workbook reads run off the UI thread."""
import queue
import sqlite3
import threading
import tkinter as tk
from tkinter import ttk, filedialog
from pathlib import Path
from .inventory_excel import read_inventory, preview, commit_import, write_inventory
from .ui import BG, PANEL, FG, MUTED, BLUE


class ExcelWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.source = []
        self.checked = []
        self.title('Impor dan ekspor data barang • Warehouse Check')
        self.geometry('1100x720')
        self.minsize(900,600)
        self.configure(bg=BG)
        self.transient(app.root)
        self.columnconfigure(0,weight=1)
        self.rowconfigure(3,weight=1)
        title=tk.Frame(self,bg=BG)
        title.grid(row=0,column=0,sticky='ew',padx=20,pady=(11,7))
        tk.Label(title,text='Impor & ekspor data barang',bg=BG,fg=FG,font=('Segoe UI',18,'bold')).pack(anchor='w')
        tk.Label(title,text='Gunakan impor untuk menambahkan banyak barang. Gunakan ekspor untuk menyimpan salinan inventori.',
                 bg=BG,fg=MUTED,font=('Segoe UI',10)).pack(anchor='w',pady=(3,0))

        options=tk.Frame(self,bg=BG)
        options.grid(row=1,column=0,sticky='ew',padx=20)
        options.columnconfigure(0,weight=7,uniform='options')
        options.columnconfigure(1,weight=3,uniform='options')
        importer=tk.Frame(options,bg=PANEL,highlightbackground='#26445E',highlightthickness=1,padx=15,pady=8)
        importer.grid(row=0,column=0,sticky='nsew',padx=(0,10))
        tk.Label(importer,text='Tambahkan barang dari Excel',bg=PANEL,fg=FG,font=('Segoe UI',13,'bold')).pack(anchor='w')
        tk.Label(importer,text='Ikuti langkah berikut. Data disimpan setelah Anda menekan tombol simpan.',
                 bg=PANEL,fg=MUTED,font=('Segoe UI',9)).pack(anchor='w',pady=(2,6))
        steps=tk.Frame(importer,bg=PANEL)
        steps.pack(fill='x')
        for column in (0,1):steps.columnconfigure(column,weight=1)
        first=tk.Frame(steps,bg=PANEL)
        first.grid(row=0,column=0,sticky='ew',padx=(0,8))
        second=tk.Frame(steps,bg=PANEL)
        second.grid(row=0,column=1,sticky='ew')
        tk.Label(first,text='1  Isi template',bg=PANEL,fg=FG,font=('Segoe UI',10,'bold')).pack(anchor='w')
        tk.Label(first,text='Unduh lalu isi sheet Inventory.',bg=PANEL,fg=MUTED,font=('Segoe UI',9),anchor='w').pack(anchor='w',pady=(2,5))
        self.template_button=self.button(first,'Unduh template Excel',lambda:self.export(True))
        self.template_button.pack(fill='x')
        tk.Label(second,text='2  Periksa file',bg=PANEL,fg=FG,font=('Segoe UI',10,'bold')).pack(anchor='w')
        tk.Label(second,text='Pilih file terisi untuk melihat hasilnya.',bg=PANEL,fg=MUTED,font=('Segoe UI',9),anchor='w').pack(anchor='w',pady=(2,5))
        self.choose_button=self.button(second,'Pilih & periksa file Excel…',self.load,primary=True)
        self.choose_button.pack(fill='x')
        self.template_status=tk.Label(importer,text='',bg=PANEL,fg='#58DCA5',font=('Segoe UI',9),anchor='w')
        self.path_label=tk.Label(importer,text='Belum ada file dipilih',bg=PANEL,fg=MUTED,font=('Segoe UI',9),anchor='w')
        self.path_label.pack(fill='x',pady=(8,0))

        exporter=tk.Frame(options,bg=PANEL,highlightbackground='#26445E',highlightthickness=1,padx=15,pady=8)
        exporter.grid(row=0,column=1,sticky='nsew')
        tk.Label(exporter,text='Simpan salinan inventori',bg=PANEL,fg=FG,font=('Segoe UI',13,'bold')).pack(anchor='w')
        description=tk.Label(exporter,text='Buat file Excel berisi semua data barang yang sekarang tersimpan. Data di aplikasi tetap sama.',
                             bg=PANEL,fg=MUTED,font=('Segoe UI',9),justify='left',anchor='nw',wraplength=225)
        description.pack(fill='x',pady=(5,10))
        self.export_button=self.button(exporter,'Ekspor inventori ke Excel',lambda:self.export(False))
        self.export_button.pack(fill='x')
        self.export_status=tk.Label(exporter,text='',bg=PANEL,fg='#58DCA5',font=('Segoe UI',9),
                                    justify='left',anchor='w',wraplength=220)
        exporter.bind('<Configure>',lambda e:description.configure(wraplength=max(150,e.width-34)))
        exporter.bind('<Configure>',lambda e:self.export_status.configure(wraplength=max(150,e.width-34)),add='+')

        summary=tk.Frame(self,bg=BG)
        summary.grid(row=2,column=0,sticky='ew',padx=20,pady=(10,6))
        self.validation_badge=tk.Label(summary,text='BELUM DIPERIKSA',bg='#253447',fg=MUTED,
                                       font=('Segoe UI',9,'bold'),padx=10,pady=5)
        self.validation_badge.pack(side='right',padx=(12,0))
        tk.Label(summary,text='3  Tinjau hasil sebelum menyimpan',bg=BG,fg=FG,font=('Segoe UI',13,'bold')).pack(anchor='w')
        self.info=tk.Label(summary,text='Belum ada file diperiksa. Pilih file Excel yang sudah diisi pada langkah 2.',
                           bg=BG,fg=MUTED,wraplength=920,justify='left',anchor='w',font=('Segoe UI',9))
        self.info.pack(fill='x',pady=(3,0))
        host=tk.Frame(self,bg=BG)
        host.grid(row=3,column=0,sticky='nsew',padx=20)
        host.columnconfigure(0,weight=1)
        host.rowconfigure(0,weight=1)
        self.table=ttk.Treeview(host,columns=('row','id','material','location','result'),show='headings',selectmode='browse')
        for key,label,width in [('row','Baris',70),('id','ID batch',145),('material','Material',215),('location','Lokasi barang',175),('result','Hasil pemeriksaan',420)]:
            self.table.heading(key,text=label)
            self.table.column(key,width=width,minwidth=width,anchor='w')
        self.table.grid(row=0,column=0,sticky='nsew')
        sy=ttk.Scrollbar(host,command=self.table.yview)
        sy.grid(row=0,column=1,sticky='ns')
        sx=ttk.Scrollbar(host,orient='horizontal',command=self.table.xview)
        sx.grid(row=1,column=0,sticky='ew')
        def sync_vertical(first,last):
            sy.set(first,last)
            if float(last)-float(first)>=0.999:sy.grid_remove()
            else:sy.grid(row=0,column=1,sticky='ns')
        def sync_horizontal(first,last):
            sx.set(first,last)
            if float(last)-float(first)>=0.999:sx.grid_remove()
            else:sx.grid(row=1,column=0,sticky='ew')
        self.table.configure(yscrollcommand=sync_vertical,xscrollcommand=sync_horizontal)
        self.table.tag_configure('error',background='#3A2534',foreground='#FFD1D4')
        self.table.tag_configure('ready',background='#143D34',foreground='#B5F5D8')
        self.table.bind('<<TreeviewSelect>>',self.selected)
        self.detail=tk.Label(self,text='Pilih baris untuk melihat detail dan cara memperbaikinya.',bg=BG,fg=MUTED,wraplength=920,justify='left',anchor='w',font=('Segoe UI',9))
        self.detail.grid(row=4,column=0,sticky='ew',padx=20,pady=8)
        self.bind('<Configure>',self.resize)
        footer=tk.Frame(self,bg=BG)
        footer.grid(row=5,column=0,sticky='ew',padx=20,pady=(0,15))
        self.save_button=self.button(footer,'Simpan semua barang',self.save,primary=True)
        self.save_button.configure(state='disabled',bg='#31506C',disabledforeground='#B2C0CD',padx=18,pady=10)
        self.save_button.pack(side='right')
        self.done_button=self.button(footer,'Lihat Data Barang',self.close_to_inventory)
        tk.Label(footer,text='Tombol simpan aktif jika semua baris valid. Data lama tidak ditimpa.',
                 bg=BG,fg=MUTED,font=('Segoe UI',9)).pack(side='left')
        self.pending=None

    def button(self,parent,text,command,primary=False):
        return tk.Button(parent,text=text,command=command,bg=BLUE if primary else '#193A59',fg=FG,
                         activebackground='#22598C',activeforeground=FG,relief='flat',
                         font=('Segoe UI',10,'bold' if primary else 'normal'),padx=12,pady=7,cursor='hand2')

    def close_to_inventory(self):
        self.destroy()
        self.app.show('Data Barang')

    def resize(self,event):
        if event.widget is self:
            for label in (self.info,self.detail):label.configure(wraplength=max(300,event.width-50))

    def export(self,template):
        path=filedialog.asksaveasfilename(parent=self,defaultextension='.xlsx',filetypes=[('Excel','*.xlsx')],initialfile='template_inventory.xlsx' if template else 'inventory_export.xlsx')
        if not path:return
        try:
            write_inventory(path,self.app.db,template)
            if template:self.template_status.configure(text='Template tersimpan: '+Path(path).name,fg='#58DCA5')
            else:self.export_status.configure(text='File tersimpan: '+Path(path).name,fg='#58DCA5')
        except (OSError,ValueError,sqlite3.Error) as exc:
            target=self.template_status if template else self.export_status
            target.configure(text='Gagal menyimpan: '+str(exc),fg='#FFA3AA')
        target=self.template_status if template else self.export_status
        if not target.winfo_manager():target.pack(fill='x',pady=(6,0))

    def load(self):
        if self.pending is not None:return
        path=filedialog.askopenfilename(parent=self,filetypes=[('Excel','*.xlsx')])
        if not path:return
        self.path_label.configure(text='File: '+Path(path).name)
        self.source=[]
        self.checked=[]
        self.table.delete(*self.table.get_children())
        self.detail.configure(text='Pilih baris untuk melihat detail dan cara memperbaikinya.')
        self.save_button.configure(state='disabled',bg='#31506C')
        self.validation_badge.configure(text='MEMERIKSA FILE',bg='#243C55',fg='#B8D4F3')
        self.info.configure(text='Sedang memeriksa file '+Path(path).name+'…',fg=MUTED)
        mailbox=queue.Queue()
        def worker():
            try:mailbox.put((read_inventory(path),None))
            except Exception as exc:mailbox.put((None,str(exc)))
        threading.Thread(target=worker,daemon=True).start()
        def poll():
            self.pending=None
            if not self.winfo_exists():return
            try:source,error=mailbox.get_nowait()
            except queue.Empty:
                self.pending=self.after(80,poll)
                return
            if error:
                self.info.configure(text='File belum dapat dibaca: '+error+' Periksa sheet Inventory dan coba pilih file lagi.',fg='#FFA3AA')
                self.validation_badge.configure(text='FILE BERMASALAH',bg='#492935',fg='#FFA3AA')
            else:
                self.source=source
                self.render_preview()
        self.pending=self.after(80,poll)

    def render_preview(self):
        self.checked=preview(self.app.db,self.source)
        self.table.delete(*self.table.get_children())
        for i,row in enumerate(self.checked):
            data=row['values']
            error=row['errors'][0] if row['errors'] else ''
            if error.startswith('Kolom tampak bergeser'):
                error='Susunan kolom bergeser — lihat detail'
            elif len(error)>55:
                error=error[:52]+'…'
            ready_label = 'Siap ditambahkan'
            if row.get('notices'):
                ready_label = 'Siap · kode lama diterjemahkan'
            self.table.insert('', 'end',iid=str(i),values=(f"  {row['row']}",
                '  '+str(data.get('id') or '(otomatis)'),
                '  '+str(data.get('material') or '—'),
                '  '+str(data.get('location_code') or '—'),
                '  '+(error or ready_label)),
                tags=('error',) if row['errors'] else ('ready',))
        bad=sum(bool(r['errors']) for r in self.checked)
        ready_count=len(self.checked)-bad
        self.validation_badge.configure(text=f'{ready_count} SIAP  •  {bad} PERLU PERBAIKAN',
                                        bg='#492935' if bad else '#173D34',fg='#FFA3AA' if bad else '#70E5B3')
        self.info.configure(text=f'{len(self.checked)} baris diperiksa • {bad} perlu diperbaiki. '+
                            ('Lihat kolom Hasil validasi, perbaiki di Excel, lalu pilih file lagi.' if bad else 'Semua baris siap ditambahkan.'),
                            fg='#FFA3AA' if bad else '#58DCA5')
        ready=bool(self.checked and not bad)
        self.save_button.configure(state='normal' if ready else 'disabled',bg=BLUE if ready else '#31506C')
        self.save_button.configure(text=f'Simpan {len(self.checked)} barang baru' if self.checked and not bad else 'Simpan semua barang')

    def selected(self,event=None):
        selected=self.table.selection()
        if selected:
            row=self.checked[int(selected[0])]
            data=row['values']
            text='; '.join(row['errors']) if row['errors'] else f"Siap disimpan • Material: {data.get('material')} • Lokasi: {data.get('location_code')} • Stok: {data.get('stock')}"
            if row.get('notices'):
                text += ' • ' + ' '.join(row['notices'])
            self.detail.configure(text=f"Baris {row['row']}: "+text,fg='#FFA3AA' if row['errors'] else MUTED)

    def save(self):
        try:keys=commit_import(self.app.db,self.source)
        except (ValueError,sqlite3.Error) as exc:
            self.render_preview()
            self.info.configure(text=str(exc),fg='#FFA3AA')
            return
        self.source=[]
        self.save_button.configure(state='disabled',bg='#31506C')
        self.validation_badge.configure(text=f'{len(keys)} TERSIMPAN',bg='#173D34',fg='#70E5B3')
        self.info.configure(text=f'{len(keys)} barang baru berhasil disimpan. QR tersedia di detail tiap barang.',fg='#58DCA5')
        self.done_button.pack(side='right',padx=(0,10))
        self.app.show('Data Barang')

    def destroy(self):
        if getattr(self,'pending',None) is not None:self.after_cancel(self.pending)
        super().destroy()
