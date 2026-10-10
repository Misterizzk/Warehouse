"""Report history, snapshot detail, PDF preview and explicit file export."""
import tempfile
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog
from PIL import ImageTk
from .reports import history,report_data,export_excel,export_pdf,decision_target
from .inventory_table import InventoryTable
from .ui import BG,PANEL,FG,MUTED,BLUE,display_time
from .theme import (
    ACCENT_HOVER, DANGER, DISABLED_FG, FIELD_BORDER, FOCUS,
    ROW_ALT, SUCCESS, SURFACE_ALT,
)


def action(parent,text,command,primary=False):
    return tk.Button(parent,text=text,command=command,bg=BLUE if primary else PANEL,fg=FG,
                     activebackground=ACCENT_HOVER if primary else SURFACE_ALT,activeforeground=FG,
                     disabledforeground=DISABLED_FG,relief='flat',padx=12,pady=10,
                     font=('Segoe UI',10,'bold' if primary else 'normal'),cursor='hand2',
                     highlightthickness=1,highlightbackground=BG,highlightcolor=FOCUS)


class ReportPage:
    def __init__(self,app):
        self.app,self.body=app,app.body
        self.list_page()

    def clear(self):
        for child in self.body.winfo_children():child.destroy()

    def list_page(self):
        self.clear()
        self.filters={}
        tk.Label(self.body,text='Riwayat laporan',bg=BG,fg=FG,font=('Segoe UI',19,'bold'),
                 anchor='w').pack(fill='x',pady=(0,3))
        tk.Label(self.body,text='Cari sesi pengecekan, lalu buka untuk melihat hasil dan menyimpan laporan.',
                 bg=BG,fg=MUTED,font=('Segoe UI',10),anchor='w').pack(fill='x',pady=(0,12))
        filters=tk.Frame(self.body,bg=PANEL,padx=14,pady=12)
        filters.pack(fill='x')
        filters.columnconfigure(0,weight=1)
        for i,(key,title,value) in enumerate((('query','Cari nomor, petugas, atau area',''),('status','Status sesi','Semua'),('date_from','Dari tanggal (YYYY-MM-DD)',''),('date_to','Hingga tanggal (YYYY-MM-DD)',''))):
            var=tk.StringVar(value=value)
            self.filters[key]=var
            tk.Label(filters,text=title,bg=PANEL,fg=MUTED,font=('Segoe UI',10)).grid(row=0,column=i,sticky='w',padx=(0,10),pady=(0,5))
            entry=ttk.Combobox(filters,textvariable=var,values=('Semua','Draft','Selesai'),state='readonly',width=12,style='Warehouse.TCombobox') if key=='status' else tk.Entry(filters,textvariable=var,bg=PANEL,fg=FG,insertbackground=FG,width=18,font=('Segoe UI',10),relief='flat',highlightthickness=1,highlightbackground=FIELD_BORDER,highlightcolor=FOCUS)
            entry.grid(row=1,column=i,sticky='ew',padx=(0,10),ipady=5)
            entry.bind('<Return>',lambda e:self.refresh())
        toolbar=tk.Frame(self.body,bg=BG)
        toolbar.pack(fill='x',pady=10)
        action(toolbar,'Tampilkan hasil',self.refresh,True).pack(side='left')
        action(toolbar,'Hapus filter',self.reset).pack(side='left',padx=8)
        self.open_button=action(toolbar,'Buka laporan yang dipilih',self.open_selected)
        self.open_button.pack(side='right')
        self.info=self.app.label(self.body,'',10)
        host=tk.Frame(self.body,bg=BG)
        host.pack(fill='both',expand=True)
        host.columnconfigure(0,weight=1)
        host.rowconfigure(0,weight=1)
        self.table=ttk.Treeview(host,columns=('id','officer','area','started','finished','state','count'),show='headings',selectmode='browse')
        for key,title,width in [('id','Nomor laporan',135),('officer','Petugas',155),('area','Area',110),('started','Mulai',190),('finished','Selesai',190),('state','Status sesi',105),('count','Hasil',70)]:
            self.table.heading(key,text=title)
            self.table.column(key,width=width,minwidth=width)
        self.table.tag_configure('even',background=PANEL,foreground=FG)
        self.table.tag_configure('odd',background=ROW_ALT,foreground=FG)
        self.table.grid(row=0,column=0,sticky='nsew')
        sy=ttk.Scrollbar(host,command=self.table.yview)
        sy.grid(row=0,column=1,sticky='ns')
        sx=ttk.Scrollbar(host,orient='horizontal',command=self.table.xview)
        sx.grid(row=1,column=0,sticky='ew')
        self.table.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
        self.table.bind('<Double-1>',lambda e:self.open_selected())
        self.table.bind('<Return>',lambda e:self.open_selected())
        self.refresh()

    def reset(self):
        for key,var in self.filters.items():var.set('Semua' if key=='status' else '')
        self.refresh()

    def refresh(self):
        values={key:var.get().strip() for key,var in self.filters.items()}
        if values['status']=='Semua':values['status']=''
        try:rows=history(self.app.db,**values)
        except ValueError as exc:
            self.info.configure(text=str(exc),fg=DANGER)
            return
        self.table.delete(*self.table.get_children())
        for index,r in enumerate(rows):
            self.table.insert('','end',iid=str(r['id']),tags=('even' if index%2==0 else 'odd',),
                              values=(f"CHK-{r['id']:06d}",r['officer'],r['area'],display_time(r['started_at']),display_time(r['finished_at']),r['status'],r['total']))
        self.info.configure(text=(f'{len(rows)} laporan ditemukan. Tanggal mengacu pada awal sesi. Klik dua kali baris untuk membuka.'
                                  if rows else 'Belum ada laporan yang sesuai. Ubah atau hapus filter untuk melihat laporan lain.'),fg=MUTED)

    def open_selected(self):
        selected=self.table.selection()
        if selected:self.detail(int(selected[0]))
        else:self.info.configure(text='Pilih satu laporan pada tabel terlebih dahulu.')

    def detail(self,key):
        self.data=report_data(self.app.db,key)
        self.clear()
        session=self.data['session']
        toolbar=tk.Frame(self.body,bg=BG)
        toolbar.pack(fill='x')
        action(toolbar,'Kembali ke riwayat',self.list_page).pack(side='left')
        self.preview_button=action(toolbar,'Pratinjau PDF',self.preview)
        self.preview_button.pack(side='left',padx=8)
        self.excel_button=action(toolbar,'Simpan Excel',lambda:self.export('xlsx'))
        self.excel_button.pack(side='left')
        self.pdf_button=action(toolbar,'Simpan PDF',lambda:self.export('pdf'),True)
        self.pdf_button.pack(side='left',padx=8)
        self.app.label(self.body,f"Laporan CHK-{key:06d}  •  {session['status']}",18,FG,True)
        self.app.label(self.body,f"Petugas: {session['officer']}   •   Area: {session['area']}\nMulai: {display_time(session['started_at'])}   •   Selesai: {display_time(session['finished_at']) if session['finished_at'] else 'Belum selesai'}",10)
        count_text='   •   '.join(f"{'Peringatan' if status=='Warning' else status}: {count}"
                                     for status,count in self.data['counts'].items())
        self.app.label(self.body,f"Normal ≤ {session['normal_max']} hari   •   Peringatan ≤ {session['age_limit']} hari   •   {count_text}",10)
        explanation=('Hasil Draft dapat bertambah sampai sesi diselesaikan.' if session['status']=='Draft'
                     else 'Sesi selesai. Hasil dan catatan tersimpan sesuai waktu pengecekan.')
        self.info=self.app.label(self.body,explanation,10)
        bottom=tk.Frame(self.body,bg=BG)
        bottom.pack(side='bottom',fill='x',pady=8)
        action(bottom,'Catatan sesi',lambda:self.notes()).pack(side='left')
        self.detail_button=action(bottom,'Detail & catatan hasil',self.selected_detail)
        self.detail_button.pack(side='left',padx=8)
        self.detail_button.configure(state='disabled')
        self.selected=None
        self.result_table=InventoryTable(self.body,self.data['rows'],self.select,inspection=True)
        self.result_table.pack(fill='both',expand=True)

    def select(self,row):
        self.selected=row
        self.detail_button.configure(state='normal')

    def selected_detail(self):
        if self.selected:self.notes(self.selected)

    def notes(self,row=None):
        win=tk.Toplevel(self.app.root)
        win.title('Detail laporan — hanya baca')
        win.geometry('680x520')
        win.configure(bg=BG)
        box=tk.Text(win,bg=PANEL,fg=FG,font=('Segoe UI',11),wrap='word',padx=16,pady=16)
        sy=ttk.Scrollbar(win,command=box.yview)
        sy.pack(side='right',fill='y')
        box.pack(fill='both',expand=True,padx=12,pady=12)
        box.configure(yscrollcommand=sy.set)
        if row:
            lines=[f"{label}: {display_time(row[field]) if field == 'checked_at' else row[field]}" for field,label in [('id','Batch'),('material','Material'),('description','Deskripsi'),('plant','Plant'),('storage_location','Storage Location'),('location_code','Lokasi'),('received_date','Tanggal masuk (GR)'),('stock','Stok'),('age','Umur (hari)'),('status','Status'),('checked_at','Waktu pengecekan'),('note','Catatan')]]
            advice_label=('REKOMENDASI SAAT CEK • DATA SIMULASI'
                          if row['recommendation'].get('source')=='Simulasi'
                          else 'SARAN BERDASARKAN UMUR SAAT CEK')
            lines.extend(['',advice_label,row['recommendation']['next_action'],
                          '', 'KEPUTUSAN PETUGAS'])
            decision=row.get('decision')
            if decision:
                lines.extend((f"Kondisi fisik: {decision['physical_condition']}",
                              f"Keputusan: {decision['choice']}",
                              f"Tujuan tindakan: {decision_target(decision) or '—'}",
                              f"Alasan: {decision['reason']}",
                              f"Petugas: {decision['officer']}",
                              f"Waktu keputusan: {display_time(decision['decided_at'])}"))
            else:lines.append('Belum ada keputusan yang dicatat pada sesi ini.')
            content='\n'.join(lines)
        else:content=self.data['session']['note'] or 'Tidak ada catatan sesi.'
        box.insert('1.0',content)
        box.configure(state='disabled')

    def export(self,kind):
        key=self.data['session']['id']
        path=filedialog.asksaveasfilename(parent=self.app.root,defaultextension='.'+kind,filetypes=[(kind.upper(),'*.'+kind)],initialfile=f'laporan_CHK-{key:06d}.{kind}')
        if not path:return
        try:
            (export_pdf if kind=='pdf' else export_excel)(self.data,path)
            self.info.configure(text='Laporan tersimpan: '+path,fg=SUCCESS)
        except Exception as exc:self.info.configure(text='Ekspor gagal: '+str(exc),fg=DANGER)

    def preview(self):
        try:self.pdf_preview=PDFPreview(self.app.root,self.data)
        except Exception as exc:self.info.configure(text='Preview gagal: '+str(exc),fg=DANGER)


class PDFPreview(tk.Toplevel):
    def __init__(self,root,data):
        import pypdfium2 as pdfium
        self.folder=tempfile.TemporaryDirectory()
        path=Path(self.folder.name)/'preview.pdf'
        try:
            export_pdf(data,path)
            self.document=pdfium.PdfDocument(path)
        except Exception:
            self.folder.cleanup()
            raise
        super().__init__(root)
        self.title('Preview PDF laporan')
        self.geometry(f'{min(1100,root.winfo_screenwidth()-60)}x{min(720,root.winfo_screenheight()-100)}')
        self.configure(bg=BG)
        self.columnconfigure(0,weight=1)
        self.rowconfigure(1,weight=1)
        toolbar=tk.Frame(self,bg=BG)
        toolbar.grid(row=0,column=0,sticky='ew',padx=12,pady=10)
        action(toolbar,'Halaman sebelumnya',lambda:self.move(-1)).pack(side='left')
        action(toolbar,'Halaman berikutnya',lambda:self.move(1)).pack(side='left',padx=8)
        self.page_label=tk.Label(toolbar,bg=BG,fg=FG)
        self.page_label.pack(side='left',padx=12)
        self.zoom=tk.StringVar(value='100%')
        zoom=ttk.Combobox(toolbar,textvariable=self.zoom,values=('75%','100%','150%'),state='readonly',width=8,style='Warehouse.TCombobox')
        zoom.pack(side='right')
        tk.Label(toolbar,text='Ukuran:',bg=BG,fg=MUTED,font=('Segoe UI',10)).pack(side='right',padx=(8,6))
        zoom.bind('<<ComboboxSelected>>',lambda e:self.render())
        host=tk.Frame(self,bg=BG)
        host.grid(row=1,column=0,sticky='nsew')
        host.columnconfigure(0,weight=1)
        host.rowconfigure(0,weight=1)
        self.canvas=tk.Canvas(host,bg=SURFACE_ALT,highlightthickness=0)
        self.canvas.grid(row=0,column=0,sticky='nsew')
        sy=ttk.Scrollbar(host,command=self.canvas.yview)
        sy.grid(row=0,column=1,sticky='ns')
        sx=ttk.Scrollbar(host,orient='horizontal',command=self.canvas.xview)
        sx.grid(row=1,column=0,sticky='ew')
        self.canvas.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
        self.canvas.bind('<MouseWheel>',lambda e:self.canvas.yview_scroll(-1 if e.delta>0 else 1,'units'))
        self.index=0
        self.render()
        self.protocol('WM_DELETE_WINDOW',self.destroy)

    def move(self,step):
        self.index=max(0,min(len(self.document)-1,self.index+step))
        self.render()

    def render(self):
        page=self.document[self.index]
        bitmap=page.render(scale=float(self.zoom.get().rstrip('%'))/100*1.2)
        try:self.photo=ImageTk.PhotoImage(bitmap.to_pil().copy())
        finally:
            bitmap.close()
            page.close()
        self.canvas.delete('all')
        self.canvas.create_image(12,12,anchor='nw',image=self.photo)
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))
        self.canvas.yview_moveto(0)
        self.page_label.configure(text=f'Halaman {self.index+1} / {len(self.document)}')

    def destroy(self):
        self.document.close()
        self.folder.cleanup()
        super().destroy()
