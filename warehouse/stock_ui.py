"""Stock-out entry and immutable history, using the stock movement service."""
import re
import sqlite3
import tkinter as tk
from tkinter import ttk
from datetime import date, datetime
from uuid import uuid4
from .stock_movements import StockMovements
from .ui import BG, PANEL, FG, MUTED, BLUE


def button(parent, text, command, primary=False):
    return tk.Button(parent, text=text, command=command, bg=BLUE if primary else PANEL,
                     fg=FG, activebackground='#1A6CD0' if primary else '#1B3A57', activeforeground=FG,
                     disabledforeground='#9DB0C0', relief='flat', font=('Segoe UI',10),
                     padx=14, pady=9, cursor='hand2',highlightthickness=1,
                     highlightbackground=BG,highlightcolor='#68B7FF')


class StockOutDialog(tk.Toplevel):
    def __init__(self, app, batch_id):
        self.item=next((r for r in app.inventory.list_batches(query=batch_id) if r['id']==batch_id),None)
        if self.item is None:raise ValueError('Barang tidak ditemukan. Buka ulang Data Barang.')
        super().__init__(app.root)
        self.app,self.batch_id=app,batch_id
        self.service=StockMovements(app.db)
        self.operation_id='OUT-'+uuid4().hex.upper()
        self.saving=False
        self.title('Catat pengeluaran barang')
        self.configure(bg=BG)
        self.geometry('680x600')
        self.minsize(600,500)
        self.transient(app.root)
        self.columnconfigure(0,weight=1)
        self.rowconfigure(1,weight=1)
        title=tk.Frame(self,bg=BG)
        title.grid(row=0,column=0,sticky='ew',padx=22,pady=(15,10))
        tk.Label(title,text='Catat pengeluaran barang',bg=BG,fg=FG,font=('Segoe UI',19,'bold')).pack(anchor='w')
        tk.Label(title,text='Isi jumlah, tanggal, dan petugas. Periksa sisa stok sebelum menyimpan.',
                 bg=BG,fg=MUTED,font=('Segoe UI',10),anchor='w').pack(fill='x',pady=(4,0))
        host=tk.Frame(self,bg=BG)
        host.grid(row=1,column=0,sticky='nsew',padx=22)
        host.columnconfigure(0,weight=1)
        host.rowconfigure(0,weight=1)
        self.canvas=tk.Canvas(host,bg=BG,highlightthickness=0)
        self.canvas.grid(row=0,column=0,sticky='nsew')
        self.scroll=ttk.Scrollbar(host,command=self.canvas.yview)
        self.scroll.grid(row=0,column=1,sticky='ns')
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.form=tk.Frame(self.canvas,bg=BG)
        window=self.canvas.create_window(0,0,window=self.form,anchor='nw')
        self.canvas.bind('<Configure>',lambda e:(self.canvas.itemconfigure(window,width=e.width),
                                                 self.after_idle(self.update_scrollregion)))
        self.form.bind('<Configure>',lambda e:self.update_scrollregion())
        self.form.columnconfigure((0,1),weight=1,uniform='stock-fields')
        self.item_label=tk.Label(self.form,bg=PANEL,fg=FG,font=('Segoe UI',10),anchor='w',
                                 justify='left',padx=12,pady=10,wraplength=570)
        self.item_label.grid(row=0,column=0,columnspan=2,sticky='ew',pady=(0,10))
        self.item_label.bind('<Configure>',lambda e:self.item_label.configure(wraplength=max(200,e.width-24)))
        self.values={}
        self.inputs={}
        for name,label,value,row,col,span in (
            ('quantity','Jumlah barang keluar (unit)','1',1,0,1),
            ('occurred_on','Tanggal keluar (YYYY-MM-DD)',date.today().isoformat(),1,1,1),
            ('officer','Nama atau NIK petugas',getattr(app,'stock_officer',''),2,0,2)):
            cell=tk.Frame(self.form,bg=BG)
            cell.grid(row=row,column=col,columnspan=span,sticky='ew',padx=(0,10 if col==0 and span==1 else 0),pady=(0,10))
            tk.Label(cell,text=label,bg=BG,fg=MUTED,font=('Segoe UI',10)).pack(anchor='w',pady=(0,4))
            self.values[name]=tk.StringVar(value=value)
            entry=tk.Entry(cell,textvariable=self.values[name],bg=PANEL,fg=FG,insertbackground=FG,
                           font=('Segoe UI',11),relief='flat',highlightthickness=1,
                           highlightbackground='#345470',highlightcolor=BLUE)
            entry.pack(fill='x',ipady=5)
            entry.bind('<FocusIn>',lambda e:self.reveal(e.widget))
            self.inputs[name]=entry
        tk.Label(self.form,text='Tujuan atau keterangan (opsional)',bg=BG,fg=MUTED,font=('Segoe UI',10)).grid(row=3,column=0,columnspan=2,sticky='w',pady=(0,4))
        self.note_text=tk.Text(self.form,height=3,bg=PANEL,fg=FG,insertbackground=FG,
                               font=('Segoe UI',11),wrap='word',relief='flat',padx=8,pady=7)
        self.note_text.grid(row=4,column=0,columnspan=2,sticky='ew',pady=(0,10))
        self.note_text.bind('<FocusIn>',lambda e:self.reveal(e.widget))
        self.remaining=tk.Label(self,text='',bg=PANEL,fg=FG,font=('Segoe UI',11,'bold'),
                                 anchor='w',justify='left',padx=12,pady=9,wraplength=610)
        self.remaining.grid(row=2,column=0,sticky='ew',padx=22,pady=(10,6))
        self.message=tk.Label(self,text='Tanggal keluar tidak boleh sebelum tanggal masuk atau setelah hari ini.',
                              bg=BG,fg=MUTED,font=('Segoe UI',9),anchor='w',justify='left',wraplength=620)
        self.message.grid(row=3,column=0,sticky='ew',padx=22)
        actions=tk.Frame(self,bg=BG)
        actions.grid(row=4,column=0,sticky='ew',padx=22,pady=(10,15))
        self.save_button=button(actions,'Simpan & kurangi stok',self.save,True)
        self.save_button.pack(side='right')
        button(actions,'Batal',self.destroy).pack(side='right',padx=(0,10))
        self.values['quantity'].trace_add('write',lambda *_:self.refresh_remaining())
        self.bind('<Configure>',self.resize)
        self.bind('<Escape>',lambda e:self.destroy())
        self.bind_scroll(self.form)
        self.canvas.bind('<MouseWheel>',self.wheel)
        self.refresh_remaining()
        self.grab_set()
        self.inputs['quantity'].focus_set()
        self.inputs['quantity'].selection_range(0,'end')

    def resize(self,event):
        if event.widget is self:
            self.remaining.configure(wraplength=max(250,event.width-68))
            self.message.configure(wraplength=max(250,event.width-44))

    def update_scrollregion(self):
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))
        if self.form.winfo_height()>self.canvas.winfo_height()+2:self.scroll.grid()
        else:self.scroll.grid_remove()

    def bind_scroll(self,widget):
        if isinstance(widget,tk.Text):return
        widget.bind('<MouseWheel>',self.wheel,add='+')
        for child in widget.winfo_children():self.bind_scroll(child)

    def wheel(self,event):
        self.canvas.yview_scroll(-1 if event.delta>0 else 1,'units')
        return 'break'

    def reveal(self,widget):
        self.update_idletasks()
        top=widget.winfo_rooty()-self.form.winfo_rooty()
        bottom=top+widget.winfo_height()
        visible_top=self.canvas.canvasy(0)
        visible_bottom=visible_top+self.canvas.winfo_height()
        if top<visible_top:self.canvas.yview_moveto(max(0,top-8)/max(1,self.form.winfo_height()))
        elif bottom>visible_bottom:self.canvas.yview_moveto((bottom-self.canvas.winfo_height()+8)/max(1,self.form.winfo_height()))

    def refresh_remaining(self):
        stock=self.item['stock']
        self.item_label.configure(text=f"{self.item['material']} — {self.item['description']}\nBatch: {self.batch_id}\nLokasi: {self.item['location_code']} • Stok tersedia: {stock} unit")
        text=self.values['quantity'].get().strip()
        quantity=int(text) if re.fullmatch(r'[0-9]{1,9}',text) else 0
        valid=0<quantity<=stock
        if valid:
            info=f'Stok {stock} unit  −  Keluar {quantity} unit  =  Sisa {stock-quantity} unit'
        elif stock==0:info='Stok barang ini sudah habis.'
        elif quantity>stock:info=f'Jumlah keluar melebihi stok tersedia ({stock} unit).'
        else:info='Isi jumlah keluar dengan bilangan bulat lebih dari 0.'
        self.remaining.configure(text=info,fg='#76E1B2' if valid else '#FFA3AA')
        self.save_button.configure(state='normal' if valid and not self.saving else 'disabled',bg=BLUE if valid else '#31506C')

    def save(self):
        if self.saving:return
        self.saving=True
        self.save_button.configure(state='disabled')
        try:
            result=self.service.issue(self.batch_id,self.values['quantity'].get(),
                self.values['occurred_on'].get(),self.values['officer'].get(),
                self.note_text.get('1.0','end-1c'),operation_id=self.operation_id)
        except (ValueError,sqlite3.Error) as exc:
            self.saving=False
            self.message.configure(text=str(exc),fg='#FFA3AA')
            fresh=next((r for r in self.app.inventory.list_batches(query=self.batch_id) if r['id']==self.batch_id),None)
            if fresh:self.item=fresh
            self.refresh_remaining()
            if not self.values['officer'].get().strip():self.inputs['officer'].focus_set()
            return
        self.app.stock_officer=self.values['officer'].get().strip()
        self.destroy()
        self.app.show('Data Barang')
        self.app.table.choose(self.batch_id)
        self.app.inventory_notice.configure(text=f"Pengeluaran {result['quantity']} unit tersimpan. Sisa stok: {result['stock_after']} unit.",fg='#76E1B2')


class StockHistoryWindow(tk.Toplevel):
    def __init__(self,app,batch_id=None):
        super().__init__(app.root)
        self.app,self.batch_id=app,batch_id
        self.service=StockMovements(app.db)
        self.title('Riwayat barang keluar')
        self.geometry('1000x620')
        self.minsize(720,480)
        self.configure(bg=BG)
        self.transient(app.root)
        self.columnconfigure(0,weight=1)
        self.rowconfigure(3,weight=1)
        tk.Label(self,text='Riwayat barang keluar',bg=BG,fg=FG,font=('Segoe UI',19,'bold')).grid(row=0,column=0,sticky='w',padx=20,pady=(15,5))
        description='Semua pengeluaran stok yang dicatat. Pilih transaksi untuk melihat rincian stok dan petugas.'
        if batch_id:description='Batch '+batch_id+' • Riwayat pengeluaran tetap tersimpan saat stok habis.'
        self.subtitle=tk.Label(self,text=description,bg=BG,fg=MUTED,font=('Segoe UI',10),wraplength=940,justify='left',anchor='w')
        self.subtitle.grid(row=1,column=0,sticky='ew',padx=20,pady=(0,12))
        filters=tk.Frame(self,bg=BG)
        filters.grid(row=2,column=0,sticky='ew',padx=20,pady=(0,12))
        filters.columnconfigure(0,weight=1)
        tk.Label(filters,text='Cari material, batch, petugas, atau keterangan',bg=BG,fg=MUTED,font=('Segoe UI',10)).grid(row=0,column=0,sticky='w',pady=(0,4))
        self.query=tk.StringVar()
        tk.Entry(filters,textvariable=self.query,bg=PANEL,fg=FG,insertbackground=FG,
                 font=('Segoe UI',11),relief='flat').grid(row=1,column=0,sticky='ew',ipady=6)
        tk.Label(filters,text='Hasil berubah saat Anda mengetik.',bg=BG,fg=MUTED,
                 font=('Segoe UI',9)).grid(row=1,column=1,padx=(10,0),sticky='w')
        host=tk.Frame(self,bg=BG)
        host.grid(row=3,column=0,sticky='nsew',padx=20)
        host.columnconfigure(0,weight=1)
        host.rowconfigure(0,weight=1)
        self.table=ttk.Treeview(host,columns=('date','material','location','quantity','balance','officer'),show='headings',selectmode='browse')
        for name,title,width in [('date','Tanggal keluar',130),('material','Material',180),('location','Lokasi saat keluar',165),('quantity','Jumlah keluar',105),('balance','Sisa stok',105),('officer','Petugas',160)]:
            self.table.heading(name,text=title,anchor='w')
            self.table.column(name,width=width,minwidth=width,anchor='w')
        self.table.tag_configure('even',background=PANEL,foreground=FG)
        self.table.tag_configure('odd',background='#152E47',foreground=FG)
        self.table.grid(row=0,column=0,sticky='nsew')
        sy=ttk.Scrollbar(host,command=self.table.yview)
        sx=ttk.Scrollbar(host,orient='horizontal',command=self.table.xview)
        sy.grid(row=0,column=1,sticky='ns')
        sx.grid(row=1,column=0,sticky='ew')
        self.table.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
        self.table.bind('<<TreeviewSelect>>',self.select)
        self.info=tk.Label(self,bg=BG,fg=MUTED,font=('Segoe UI',9),anchor='w')
        self.info.grid(row=4,column=0,sticky='ew',padx=20,pady=(9,5))
        self.detail=tk.Text(self,height=4,bg=PANEL,fg=FG,font=('Segoe UI',10),wrap='word',relief='flat',padx=10,pady=8,state='disabled')
        self.detail.grid(row=5,column=0,sticky='ew',padx=20,pady=(0,15))
        self.query.trace_add('write',lambda *_:self.refresh())
        self.bind('<Configure>',lambda e:self.subtitle.configure(wraplength=max(300,e.width-40)) if e.widget is self else None)
        self.bind('<Escape>',lambda e:self.destroy())
        self.refresh()

    def set_detail(self,text):
        self.detail.configure(state='normal')
        self.detail.delete('1.0','end')
        self.detail.insert('1.0',text)
        self.detail.configure(state='disabled')

    def refresh(self):
        self.rows=self.service.list(batch_id=self.batch_id,query=self.query.get())
        self.by_id={r['id']:r for r in self.rows}
        self.table.delete(*self.table.get_children())
        for index,row in enumerate(self.rows):
            self.table.insert('','end',iid=row['id'],tags=('even' if index%2==0 else 'odd',),
                              values=(row['occurred_on'],row['material'],row['location_code'],row['quantity'],row['stock_after'],row['officer']))
        self.info.configure(text=f'{len(self.rows)} transaksi ditemukan. Pilih baris untuk melihat rinciannya.' if self.rows else 'Tidak ada transaksi yang sesuai. Coba kata pencarian lain.')
        self.set_detail('Pilih transaksi untuk melihat jumlah sebelum/sesudah, waktu pencatatan, dan keterangan.')

    def select(self,event=None):
        selected=self.table.selection()
        if not selected:return
        row=self.by_id[selected[0]]
        when=datetime.fromisoformat(row['recorded_at']).astimezone().strftime('%d/%m/%Y %H:%M:%S')
        self.set_detail(f"{row['material']} — {row['description']}\nBatch: {row['batch_id']} • {row['location_code']}\nStok sebelum: {row['stock_before']}  |  Keluar: {row['quantity']}  |  Sisa saat itu: {row['stock_after']}\nTanggal keluar: {row['occurred_on']} • Dicatat: {when} • Petugas: {row['officer']}\nKeterangan: {row['note'] or '—'}\nID transaksi: {row['id']}")
