"""Master rack addresses for the fixed 3×3×3 prototype layout."""
import sqlite3
import tkinter as tk
from tkinter import ttk
from .locations import Locations, parse_location
from .theme import (
    ACCENT_HOVER, DANGER, DISABLED_BG, DISABLED_FG, FIELD_BORDER,
    FOCUS, ROW_ALT, SURFACE_ALT,
)


class LocationPage:
    def __init__(self, app):
        self.app = app
        self.service = Locations(app.db)
        self.dialog = None
        # Reuse the shell palette and table style.
        from .ui import BG, FG, BLUE, MUTED, PANEL
        self.colors = BG, FG, BLUE, MUTED, PANEL
        toolbar = tk.Frame(app.body, bg=BG)
        toolbar.pack(fill="x", pady=(0,12))
        tk.Button(toolbar,text="← Data Barang",command=lambda:app.show("Data Barang"),bg=PANEL,fg=FG,
                  activebackground=SURFACE_ALT,activeforeground=FG,relief="flat",padx=14,pady=10,cursor='hand2').pack(side="left")
        tk.Button(toolbar,text="+ Tambah rak (27 lokasi)",command=self.open_form,bg=BLUE,fg=FG,
                  activebackground=ACCENT_HOVER,activeforeground=FG,relief="flat",padx=18,pady=10,
                  font=('Segoe UI',10,'bold'),cursor='hand2').pack(side="right")
        app.label(app.body,"Lokasi penyimpanan",18,FG,True)
        app.label(app.body,"Setiap rak memiliki 3 kolom × 3 baris × 3 tingkat. Tingkat 01 paling bawah; kolom dan baris mengikuti denah.",10)
        filters=tk.Frame(app.body,bg=BG)
        filters.pack(fill='x',pady=(0,12))
        tk.Label(filters,text='Cari kode lokasi',bg=BG,fg=MUTED,font=('Segoe UI',10)).pack(side='left',padx=(0,12))
        self.query=tk.StringVar()
        tk.Entry(filters,textvariable=self.query,bg=PANEL,fg=FG,insertbackground=FG,relief='flat',
                 font=('Segoe UI',11),highlightthickness=1,highlightbackground=FIELD_BORDER,
                 highlightcolor=FOCUS).pack(side='left',fill='x',expand=True,ipady=6)
        self.status=tk.StringVar()
        tk.Label(app.body,textvariable=self.status,bg=BG,fg=MUTED,anchor="w",pady=10).pack(side="bottom",fill="x")
        frame=tk.Frame(app.body,bg=BG)
        frame.pack(fill="both",expand=True)
        cols=("Kode lokasi","Area","Rak","Kolom","Baris","Tingkat","Batch tersimpan")
        self.table=ttk.Treeview(frame,columns=cols,show="headings",selectmode="browse")
        for c,w in zip(cols,(230,65,75,75,75,75,120)):
            self.table.heading(c,text=c)
            self.table.column(c,width=w,minwidth=70,anchor='w' if c!="Batch tersimpan" else 'center')
        sy=ttk.Scrollbar(frame,orient="vertical",command=self.table.yview)
        sx=ttk.Scrollbar(frame,orient="horizontal",command=self.table.xview)
        def sync_vertical(first,last):
            sy.set(first,last)
            if float(last)-float(first)>=0.999:sy.grid_remove()
            else:sy.grid(row=0,column=1,sticky='ns')
        def sync_horizontal(first,last):
            sx.set(first,last)
            if float(last)-float(first)>=0.999:sx.grid_remove()
            else:sx.grid(row=1,column=0,sticky='ew')
        self.table.configure(yscrollcommand=sync_vertical,xscrollcommand=sync_horizontal)
        self.table.grid(row=0,column=0,sticky="nsew")
        sy.grid(row=0,column=1,sticky="ns")
        sx.grid(row=1,column=0,sticky="ew")
        frame.rowconfigure(0,weight=1)
        frame.columnconfigure(0,weight=1)
        self.table.tag_configure("odd",background=ROW_ALT)
        self.table.tag_configure("even",background=PANEL)
        self.query.trace_add('write',lambda *args:self.refresh())
        self.refresh()

    def refresh(self, selected=None):
        self.table.delete(*self.table.get_children())
        all_rows=self.service.list()
        query=self.query.get().strip().upper()
        rows=[r for r in all_rows if query in r['code']]
        for i,r in enumerate(rows):
            self.table.insert("","end",iid=r['code'],values=(r['code'],r['area'],r['rack'],
                f"{r['column']:02d}",f"{r['row']:02d}",f"{r['level']:02d}",r['batches']),
                tags=("odd" if i%2 else "even",))
        self.status.set(f"Menampilkan {len(rows)} dari {len(all_rows)} lokasi  •  Batch tersimpan = jumlah batch yang memakai lokasi ini.")
        if selected:
            self.table.selection_set(selected)
            self.table.see(selected)

    def open_form(self):
        if self.dialog and self.dialog.winfo_exists():
            self.dialog.lift()
            return
        BG,FG,BLUE,MUTED,PANEL=self.colors
        win=self.dialog=tk.Toplevel(self.app.root)
        win.title("Tambah rak")
        win.configure(bg=BG)
        win.resizable(False,False)
        win.transient(self.app.root)
        win.grab_set()
        form=tk.Frame(win,bg=BG,padx=24,pady=20)
        form.pack(fill="both",expand=True)
        tk.Label(form,text='Tambah rak',bg=BG,fg=FG,font=('Segoe UI',18,'bold'),
                 anchor='w').grid(row=0,column=0,columnspan=2,sticky='ew',pady=(0,4))
        tk.Label(form,text='Isi area dan kode rak. Aplikasi membuat 27 alamat (3 kolom × 3 baris × 3 tingkat).',
                 bg=BG,fg=MUTED,font=('Segoe UI',10),anchor='w',justify='left',wraplength=410).grid(
                     row=1,column=0,columnspan=2,sticky='ew',pady=(0,15))
        self.values=[tk.StringVar(value=v) for v in ("","")]
        first=None
        for i,(label,var) in enumerate(zip(("Area, contoh A","Rak, contoh B04"),self.values)):
            tk.Label(form,text=label,bg=BG,fg=MUTED,anchor="w",font=("Segoe UI",10)).grid(row=2+i,column=0,sticky="w",pady=8,padx=(0,20))
            entry=tk.Entry(form,textvariable=var,width=24,font=("Segoe UI",11),bg=PANEL,fg=FG,
                           insertbackground=FG,relief='flat',highlightthickness=1,
                           highlightbackground=FIELD_BORDER,highlightcolor=FOCUS)
            entry.grid(row=2+i,column=1,pady=8,ipady=6)
            if first is None:first=entry
        self.preview=tk.StringVar()
        self.error=tk.StringVar()
        preview_card=tk.Frame(form,bg=PANEL,padx=12,pady=8,highlightbackground=FIELD_BORDER,highlightthickness=1)
        preview_card.grid(row=4,column=0,columnspan=2,sticky='ew',pady=(14,4))
        tk.Label(preview_card,text='RENTANG ALAMAT YANG AKAN DIBUAT',bg=PANEL,fg=MUTED,
                 font=('Segoe UI',8,'bold'),anchor='w').pack(fill='x')
        tk.Label(preview_card,textvariable=self.preview,bg=PANEL,fg=FG,font=("Segoe UI",11,"bold"),
                 anchor='w').pack(fill='x')
        tk.Label(form,textvariable=self.error,bg=BG,fg=DANGER,wraplength=390,justify="left").grid(row=5,column=0,columnspan=2,sticky="w")
        self.save_button=tk.Button(form,text="Buat rak dan 27 lokasi",command=self.save,bg=BLUE,fg=FG,
                                   activebackground=ACCENT_HOVER,activeforeground=FG,relief="flat",
                                   disabledforeground=DISABLED_FG,font=('Segoe UI',10,'bold'),padx=15,pady=10,cursor='hand2')
        self.save_button.grid(row=6,column=1,sticky="e",pady=(16,0))
        tk.Button(form,text="Batal",command=win.destroy,bg=PANEL,fg=FG,activebackground=SURFACE_ALT,
                  activeforeground=FG,relief="flat",padx=15,pady=10,cursor='hand2').grid(row=6,column=0,sticky="w",pady=(16,0))
        for var in self.values:var.trace_add("write",self.update_preview)
        self.update_preview()
        win.bind("<Escape>",lambda e:win.destroy())
        win.bind("<Return>",lambda e:self.save())
        first.focus_set()

    def update_preview(self,*args):
        if self.dialog is None or not self.dialog.winfo_exists():
            return
        try:
            area,rack=(v.get().strip().upper() for v in self.values)
            first,*_=parse_location(area,rack,1,1,1)
            last,*_=parse_location(area,rack,3,3,3)
            self.preview.set(f"{first}  sampai  {last}")
            duplicate=any(r['area']==area and r['rack']==rack for r in self.service.list())
            self.error.set("Rak sudah tersedia. Gunakan kode rak lain." if duplicate else "")
            self.save_button.configure(state="disabled" if duplicate else "normal",
                                       bg=DISABLED_BG if duplicate else self.colors[2])
        except ValueError as exc:
            self.preview.set("Kode lokasi belum valid")
            self.error.set(str(exc))
            self.save_button.configure(state="disabled",bg=DISABLED_BG)

    def save(self):
        try:
            area,rack=(v.get().strip().upper() for v in self.values)
            parse_location(area,rack,1,1,1)
            if any(r['area']==area and r['rack']==rack for r in self.service.list()):
                self.error.set("Rak sudah tersedia. Gunakan kode rak lain.")
                return
            codes=self.service.create_rack(area,rack)
        except (ValueError,sqlite3.Error) as exc:
            self.error.set(str(exc))
            return
        self.dialog.destroy()
        self.dialog=None
        self.query.set("")
        self.refresh(codes[0])
        self.status.set(f"Rak baru tersimpan: {len(codes)} lokasi dibuat. Total {len(self.table.get_children())} lokasi.")
