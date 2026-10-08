"""Desktop shell and navigation. Business logic lives outside this module."""
import tkinter as tk
from tkinter import ttk
from datetime import date,datetime
import time
from .database import connect, seed_demo, DEMO_PATH
from .inventory import Inventory
from .live_monitor import LiveMonitor, LiveSnapshot
from .recommendations import RecommendationService, recommend_for
from .recommendation_data import recommendation_context

BG = "#081827"
PANEL = "#10243A"
FG = "#F1F6FC"
MUTED = "#B1C3D5"
BLUE = "#1768CE"
SIDEBAR = "#0C2034"
HEADER = "#0E263F"
EDGE = "#24415C"
STATUS_COLORS = {"Normal":"#58DCA5", "Warning":"#F4C66A", "Melewati batas":"#FF8A8A", "Data perlu diperbaiki":"#CBD5E1"}
STATUS_BACKGROUNDS = {"Normal":"#12372F", "Warning":"#3B321B", "Melewati batas":"#40242D", "Data perlu diperbaiki":"#253447"}


def display_time(value):
    """Format a stored ISO timestamp for people without changing its value."""
    if not value:
        return '—'
    try:
        return datetime.fromisoformat(str(value)).astimezone().strftime('%d/%m/%Y %H:%M')
    except ValueError:
        return str(value)


def recommendation_rows(db, rows, today=None):
    """Add current advice and the last attributed decision to inventory rows."""
    service = RecommendationService(db)
    displayed = []
    contexts = {}
    for row in rows:
        item = dict(row)
        material = item['material']
        if material not in contexts:
            context = recommendation_context(db, material)
            contexts[material] = context if context['sites'] or context['customers'] else None
        context = contexts[material]
        item['recommendation'] = recommend_for(item, today=today, context=context)
        item['latest_action'] = service.latest_action_for_batch(item['id'])
        displayed.append(item)
    return displayed


class Application:
    def __init__(self, root, database_path=DEMO_PATH):
        self.root = root
        self.db = connect(database_path)
        seed_demo(self.db)
        self.inventory = Inventory(self.db)
        self.today = date.today()
        self.rows = self.inventory.list_batches()
        self.live_monitor = LiveMonitor()
        self.live_snapshot = LiveSnapshot(None, (), (), False)
        self.live_details = {}
        self.live_error = ''
        self.live_device_index = 0
        self.live_stopping = False
        self.live_paused_for_scan = False
        self.live_resume_ready = False
        self.live_resume_worker = None
        self.live_refresh_at = 0.0
        self.closing = False
        root.title("Warehouse Check — Demo")
        root.configure(bg=BG)
        root.geometry(f"{min(1440, root.winfo_screenwidth()-40)}x{min(900,root.winfo_screenheight()-70)}")
        root.minsize(800, 520)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG,
                        font=("Segoe UI", 10), rowheight=38, borderwidth=0, relief="flat")
        style.configure("Treeview.Heading", background="#1B3853", foreground="#D6E7F7",
                        font=("Segoe UI", 10, "bold"), padding=(12,11), relief="flat", borderwidth=0)
        style.map("Treeview.Heading", background=[("active", "#254C6E")])
        style.layout("Treeview", [("Treeview.treearea", {"sticky":"nswe"})])
        style.layout("Treeview.Heading", [("Treeheading.padding", {"sticky":"nswe", "children":[
            ("Treeheading.text", {"sticky":"we"})]})])
        for orientation in ("Vertical", "Horizontal"):
            name=f"{orientation}.TScrollbar"
            style.layout(name, [(f"{orientation}.Scrollbar.trough", {"sticky":"nswe", "children":[
                (f"{orientation}.Scrollbar.thumb", {"sticky":"nswe", "expand":"1"})]})])
            style.configure(name, background="#466987", troughcolor="#10283E", bordercolor="#10283E",
                            lightcolor="#466987", darkcolor="#466987", width=9, arrowsize=0,
                            borderwidth=0, relief="flat")
            style.map(name, background=[("active","#79A8CD"), ("pressed","#61B5F7")])
        style.map("Treeview", background=[("selected", "#17548D")], foreground=[("selected", "white")])
        style.configure('Dashboard.Treeview',rowheight=32,font=('Segoe UI',10),background=PANEL,fieldbackground=PANEL)
        style.configure('Dashboard.Treeview.Heading',background='#19334C',foreground='#B8D4F3',font=('Segoe UI',10,'bold'),padding=(10,8))
        for name in ('TCombobox', 'Warehouse.TCombobox'):
            style.configure(name,fieldbackground='#172F46',background='#172F46',foreground=FG,
                            arrowcolor='#81C6FF',bordercolor='#3B5F7E',lightcolor='#3B5F7E',
                            darkcolor='#3B5F7E',padding=7,relief='flat')
            style.map(name,fieldbackground=[('readonly','#172F46'),('focus','#1C3A56')],
                      foreground=[('readonly',FG)],bordercolor=[('focus','#58AFFF')],
                      arrowcolor=[('active','#B7E1FF')])
        root.option_add('*TCombobox*Listbox.background', '#172F46')
        root.option_add('*TCombobox*Listbox.foreground', FG)
        root.option_add('*TCombobox*Listbox.selectBackground', '#2563A2')
        root.option_add('*TCombobox*Listbox.selectForeground', FG)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(1, weight=1)
        from .visuals import icon
        sidebar = tk.Frame(root, bg=SIDEBAR, width=196, padx=10, pady=20)
        sidebar.grid(row=1,column=0,rowspan=2,sticky="nsew")
        sidebar.pack_propagate(False)
        self.brand_icons={}
        self.nav = {}
        self.nav_markers = {}
        for page,kind in (("Dashboard","home"),("Pengecekan","clipboard"),("Data Barang","box"),("Laporan","chart"),("Live","scan")):
            self.brand_icons[page]=icon(kind,25,master=root)
            nav_row=tk.Frame(sidebar,bg=SIDEBAR)
            nav_row.pack(fill='x',pady=(0,7))
            marker=tk.Frame(nav_row,bg=SIDEBAR,width=3)
            marker.pack(side='left',fill='y')
            marker.pack_propagate(False)
            b=tk.Button(nav_row,text='  '+page,image=self.brand_icons[page],compound='left',anchor="w",font=("Segoe UI",11),fg=FG,bg=SIDEBAR,activebackground='#205B90',activeforeground=FG,
                        relief="flat",borderwidth=0,padx=10,pady=13,highlightthickness=1,highlightbackground=SIDEBAR,highlightcolor='#76C5FF',cursor='hand2',
                        command=lambda p=page:self.show(p))
            b.pack(side='left',fill="x",expand=True)
            b.bind('<Enter>',lambda e,button=b,p=page:button.configure(bg='#173A5B') if self.page!=p else None)
            b.bind('<Leave>',lambda e,button=b,p=page:button.configure(bg=SIDEBAR) if self.page!=p else None)
            self.nav[page]=b
            self.nav_markers[page]=marker
        tk.Label(sidebar,text="BARANG TERKONTROL\nOPERASIONAL LEBIH MAJU",font=("Segoe UI",8),fg="#91ADCA",bg=SIDEBAR,justify="left",padx=10,pady=14).pack(side="bottom",anchor="w")
        tk.Frame(sidebar,bg='#284763',height=1).pack(side='bottom',fill='x',padx=8)
        header=tk.Frame(root,bg=HEADER,padx=18,pady=10,highlightbackground=EDGE,highlightthickness=1)
        header.grid(row=0,column=0,columnspan=2,sticky="ew")
        self.brand_icons['logo']=icon('warehouse',34,'#2C9DF4',master=root)
        tk.Label(header,image=self.brand_icons['logo'],bg=HEADER).pack(side='left',padx=(0,10))
        tk.Label(header,text='WAREHOUSE',font=('Segoe UI',20,'bold'),bg=HEADER,fg=FG).pack(side='left')
        tk.Label(header,text=' CHECK',font=('Segoe UI',20,'bold'),bg=HEADER,fg='#59B3FF').pack(side='left')
        self.title=tk.Label(header,text="",font=("Segoe UI",10),fg=MUTED,bg=HEADER,padx=20)
        self.title.pack(side='left')
        self.header_time=tk.Label(header,text=datetime.now().strftime('%d %b %Y  %H:%M'),font=('Segoe UI',10),bg=HEADER,fg=MUTED)
        self.header_time.pack(side='right',padx=8)
        self.live_indicator=tk.Label(header,text='● LIVE NONAKTIF',font=('Segoe UI',9,'bold'),
                                     bg=HEADER,fg='#91A8C1',cursor='hand2',padx=10)
        self.live_indicator.pack(side='right',padx=(5,10))
        self.live_indicator.bind('<Button-1>',lambda _event:self.show('Live'))
        self.body=tk.Frame(root,bg=BG,padx=14,pady=12)
        self.body.grid(row=1,column=1,sticky="nsew")
        footer=tk.Label(root,text="Data simulasi  •  Tersimpan di perangkat ini",bg=BG,fg='#7897B8',font=("Segoe UI",8),anchor="w",padx=16,pady=4)
        footer.grid(row=2,column=1,sticky="ew")
        footer.bind("<Configure>",lambda e:footer.configure(wraplength=max(200,e.width-40)))
        self.footer=footer
        self.page=None
        self.show("Dashboard")
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.timer=root.after(30000,self.check_day)
        self.live_timer=root.after(120,self.poll_live)

    def label(self, parent, text, size=12, color=MUTED, bold=False):
        w=tk.Label(parent,text=text,bg=BG,fg=color,font=("Segoe UI",size,"bold" if bold else "normal"),anchor="w",justify="left",wraplength=650)
        w.pack(anchor="w",fill="x",pady=7)
        w.bind("<Configure>", lambda e: w.configure(wraplength=max(180,e.width-8)))
        return w

    def action_button(self,parent,text,command,primary=False):
        return tk.Button(parent,text=text,command=command,bg=BLUE if primary else '#1A3651',
                         fg=FG,activebackground='#1A6CD0' if primary else '#254C70',
                         activeforeground=FG,relief='flat',borderwidth=0,padx=14,pady=9,
                         font=('Segoe UI',10,'bold' if primary else 'normal'),cursor='hand2',
                         highlightthickness=1,highlightbackground='#315574',highlightcolor='#7BC6FF')

    def scroll_content(self):
        canvas=tk.Canvas(self.body,bg=BG,highlightthickness=0)
        bar=ttk.Scrollbar(self.body,orient="vertical",command=canvas.yview)
        bar.pack(side="right",fill="y")
        canvas.pack(side="left",fill="both",expand=True)
        canvas.configure(yscrollcommand=bar.set)
        content=tk.Frame(canvas,bg=BG)
        item=canvas.create_window((0,0),window=content,anchor="nw")
        canvas.bind("<Configure>",lambda e:canvas.itemconfigure(item,width=e.width))
        content.bind("<Configure>",lambda e:canvas.configure(scrollregion=canvas.bbox("all")))
        def wheel(e):
            canvas.yview_scroll(-1 if e.delta>0 else 1,"units")
        canvas.bind("<MouseWheel>",wheel)
        return content

    def show(self, page):
        self.stop_camera()
        self.page=page
        self.title.configure(text=page+'  /  Data simulasi')
        self.footer.configure(text='Pemantauan sementara  •  Tidak membuat laporan' if page=='Live'
                              else 'Data simulasi  •  Tersimpan di perangkat ini')
        for name,b in self.nav.items():
            selected=name==page or (page=='Lokasi' and name=='Data Barang')
            b.configure(bg='#164F84' if selected else SIDEBAR)
            self.nav_markers[name].configure(bg='#69C3FF' if selected else SIDEBAR)
        for child in self.body.winfo_children():child.destroy()
        self.rows=self.inventory.list_batches()
        if page=="Dashboard":self.dashboard()
        elif page=="Data Barang":self.inventory_page()
        elif page=="Pengecekan":
            from .session_ui import SessionPage
            self.session_page=SessionPage(self)
        elif page=="Laporan":
            from .report_ui import ReportPage
            self.report_page=ReportPage(self)
        elif page=="Live":
            from .live_ui import LivePage
            self.live_page=LivePage(self)

    def start_live(self, index=0):
        """Start one read-only camera source; keep it active across page changes."""
        self.live_error = ''
        self.live_device_index = index
        self.live_paused_for_scan = False
        self.live_resume_ready = False
        try:
            self.live_monitor.start(index)
            self.live_stopping = False
        except ValueError as exc:
            self.live_error = str(exc)
        self.poll_live_once()

    def stop_live(self):
        self.live_paused_for_scan = False
        self.live_resume_ready = False
        self.live_resume_worker = None
        self.live_stopping = self.live_monitor.is_running
        self.live_monitor.stop()
        self.poll_live_once()

    def pause_live_for_scan(self):
        """Reserve the single camera for a confirmed Pengecekan scan."""
        if self.live_paused_for_scan:
            self.live_resume_ready = False
            self.live_resume_worker = None
            return
        if self.live_stopping:
            # A deliberate Matikan kamera must not become an automatic resume.
            return
        if not self.live_monitor.is_running:
            return
        self.live_paused_for_scan = True
        self.live_resume_ready = False
        self.live_resume_worker = None
        self.live_stopping = True
        self.live_monitor.stop()
        self.poll_live_once()

    def resume_live_after_scan(self, scan_worker=None):
        """Resume only after both camera workers have released the device."""
        if not self.live_paused_for_scan or self.closing:
            return
        self.live_resume_worker = scan_worker
        self.live_resume_ready = True

    def poll_live_once(self):
        from .live_ui import current_item
        snapshot = self.live_monitor.poll()
        self.live_snapshot = snapshot
        for kind, message in snapshot.messages:
            if kind == 'error':
                self.live_error = str(message)
            elif kind == 'stopped':
                self.live_stopping = False
        if self.live_resume_ready and not self.live_monitor.is_running:
            worker = self.live_resume_worker
            thread = getattr(worker, 'thread', None) if worker is not None else None
            if thread is None or not thread.is_alive():
                try:
                    self.live_monitor.start(self.live_device_index)
                except ValueError as exc:
                    self.live_error = str(exc)
                    self.live_paused_for_scan = False
                    self.live_resume_ready = False
                else:
                    self.live_error = ''
                    self.live_paused_for_scan = False
                    self.live_resume_ready = False
                    self.live_resume_worker = None
        now = time.monotonic()
        codes = {d.code for d in snapshot.detections}
        if codes != set(self.live_details) or (codes and now >= self.live_refresh_at):
            self.live_details = {code: current_item(self.db, code) for code in codes}
            self.live_refresh_at = now + 3.0
        red = sum(self.live_details.get(d.code, {}).get('status') == 'Melewati batas'
                  for d in snapshot.detections)
        if self.live_paused_for_scan:
            indicator, color = '● LIVE JEDA · Kamera dipakai pengecekan', '#F4C66A'
        elif self.live_monitor.is_running and not self.live_stopping:
            indicator = f'● LIVE AKTIF · {len(snapshot.detections)} QR · {red} lewat batas'
            color = '#58DCA5'
        else:
            indicator, color = '● LIVE NONAKTIF', '#91A8C1'
        self.live_indicator.configure(text=indicator, fg=color)
        if self.page == 'Live' and hasattr(self, 'live_page'):
            self.live_page.update(snapshot, self.live_details, self.live_error)

    def poll_live(self):
        if self.closing:
            return
        self.poll_live_once()
        self.live_timer = self.root.after(120, self.poll_live)

    def dashboard(self):
        from .dashboard_ui import DashboardPage
        self.dashboard_page=DashboardPage(self)

    def inventory_page(self):
        from .inventory_table import InventoryTable
        toolbar=tk.Frame(self.body,bg=BG)
        toolbar.pack(fill='x',pady=(0,12))
        self.add_button=self.action_button(toolbar,'+ Tambah batch barang',self.edit_batch,True)
        self.add_button.pack(side='left')
        self.stock_history_button=self.action_button(toolbar,'Riwayat barang keluar',self.show_stock_history)
        self.stock_history_button.pack(side='left',padx=(8,0))
        self.action_button(toolbar,'Kelola lokasi rak',self.show_locations).pack(side='right')
        self.action_button(toolbar,'Impor & ekspor Excel',self.show_excel).pack(side='right',padx=8)
        filters=tk.Frame(self.body,bg=BG)
        filters.pack(fill='x')
        filters.columnconfigure(0,weight=1)
        self.search=tk.StringVar()
        self.status_filter=tk.StringVar(value='Semua status')
        self.location_filter=tk.StringVar(value='Semua lokasi')
        self.availability_filter=tk.StringVar(value='Semua stok')
        from .locations import Locations
        for i,(label,var,values) in enumerate((('Cari material, batch, atau deskripsi',self.search,None),
                ('Status',self.status_filter,['Semua status',*STATUS_COLORS]),
                ('Lokasi',self.location_filter,['Semua lokasi',*Locations(self.db).choices()]),
                ('Ketersediaan',self.availability_filter,['Semua stok','Ada stok','Stok habis']))):
            tk.Label(filters,text=label,bg=BG,fg=MUTED,font=('Segoe UI',10)).grid(row=0,column=i,sticky='w',padx=(0,10),pady=(0,5))
            widget=(ttk.Combobox(filters,textvariable=var,values=values,state='readonly',
                                 width=13 if var is self.availability_filter else 20,
                                 style='Warehouse.TCombobox') if values else
                    tk.Entry(filters,textvariable=var,bg='#172F46',fg=FG,insertbackground=FG,
                             relief='flat',font=('Segoe UI',11),highlightthickness=1,
                             highlightbackground='#3B5F7E',highlightcolor='#58AFFF'))
            widget.grid(row=1,column=i,sticky='ew',padx=(0,10),ipady=6 if not values else 2)
        self.inventory_notice=self.label(self.body,'',10)
        self.inventory_host=tk.Frame(self.body,bg=BG)
        self.inventory_host.pack(fill='both',expand=True)
        self.inventory_host.columnconfigure(0,weight=1)
        self.inventory_host.rowconfigure(0,weight=1)
        self.table=InventoryTable(self.inventory_host,recommendation_rows(self.db,self.rows),self.show_item)
        self.table.grid(row=0,column=0,sticky='nsew')
        self.drawer=None
        self.detail=tk.StringVar()
        for var in (self.search,self.status_filter,self.location_filter,self.availability_filter):
            var.trace_add('write',lambda *_:self.filter_inventory())
        self.inventory_notice.configure(text=f'{len(self.rows)} batch • Klik satu baris untuk melihat detail, mengedit, atau membuka label QR.')

    def filter_inventory(self):
        from .inventory_table import InventoryTable
        self.close_detail()
        rows=self.inventory.list_batches(query=self.search.get(),
            status='' if self.status_filter.get()=='Semua status' else self.status_filter.get(),
            location='' if self.location_filter.get()=='Semua lokasi' else self.location_filter.get(),
            availability={'Ada stok':'active','Stok habis':'empty'}.get(self.availability_filter.get(),''))
        self.table.destroy()
        self.table=InventoryTable(self.inventory_host,recommendation_rows(self.db,rows),self.show_item)
        self.table.grid(row=0,column=0,sticky='nsew')
        self.inventory_notice.configure(text=f'{len(rows)} dari {len(self.rows)} batch • Klik baris untuk membuka detail.' if rows else 'Tidak ada barang yang cocok. Ubah kata pencarian atau filter.',fg=MUTED)

    def edit_batch(self, item=None):
        from .batch_ui import BatchEditor
        self.editor=BatchEditor(self,item)

    def show_excel(self):
        from .excel_ui import ExcelWindow
        self.excel_window=ExcelWindow(self)

    def show_stock_out(self,batch_id):
        from .stock_ui import StockOutDialog
        from tkinter import messagebox
        try:self.stock_out_window=StockOutDialog(self,batch_id)
        except ValueError as exc:messagebox.showerror('Barang keluar',str(exc),parent=self.root)

    def show_stock_history(self,batch_id=None):
        from .stock_ui import StockHistoryWindow
        previous=getattr(self,'stock_history_window',None)
        if previous is not None and previous.winfo_exists():previous.destroy()
        self.stock_history_window=StockHistoryWindow(self,batch_id)

    def show_label(self, batch_id):
        from .label_ui import LabelPreview
        from tkinter import messagebox
        try:
            previous=getattr(self,'label_preview',None)
            if previous is not None and previous.winfo_exists():previous.destroy()
            self.label_preview=LabelPreview(self,batch_id)
        except (ValueError,OSError) as exc:
            messagebox.showerror('QR belum tersedia',f'Data barang tetap tersimpan. Coba buka QR lagi.\n{exc}',parent=self.root)

    def close_detail(self):
        if self.drawer is not None:
            self.drawer.destroy()
            self.drawer=None

    def show_item(self,r):
        self.close_detail()
        from .inventory_table import COLORS
        self.drawer=tk.Frame(self.inventory_host,bg=PANEL,padx=14,pady=12,
                             highlightbackground=EDGE,highlightthickness=1)
        self.drawer.grid(row=0,column=1,sticky='ns',padx=(12,0))
        top=tk.Frame(self.drawer,bg=PANEL)
        top.pack(fill='x',pady=(0,9))
        tk.Label(top,text='Detail barang',bg=PANEL,fg=FG,font=('Segoe UI',14,'bold')).pack(side='left')
        tk.Button(top,text='Tutup ×',command=self.close_detail,bg=PANEL,fg='#82C9FF',
                  activebackground='#254C70',activeforeground=FG,relief='flat',padx=7,pady=5,
                  cursor='hand2',highlightthickness=1,highlightbackground=PANEL,
                  highlightcolor='#7BC6FF').pack(side='right')
        tk.Frame(self.drawer,bg=EDGE,height=1).pack(fill='x',pady=(0,10))
        self.stock_out_button=self.action_button(self.drawer,'Catat barang keluar',
                                                   lambda:self.show_stock_out(r['id']),True)
        self.stock_out_button.pack(fill='x',pady=(0,10))
        self.stock_out_button.configure(state='normal' if r['stock']>0 else 'disabled',
                                        bg=BLUE if r['stock']>0 else '#31506C',disabledforeground=MUTED)
        canvas=tk.Canvas(self.drawer,bg=PANEL,width=294,highlightthickness=0)
        bar=ttk.Scrollbar(self.drawer,orient='vertical',command=canvas.yview)
        bar.pack(side='right',fill='y')
        canvas.pack(fill='both',expand=True)
        canvas.configure(yscrollcommand=bar.set)
        content=tk.Frame(canvas,bg=PANEL)
        window=canvas.create_window(0,0,window=content,anchor='nw')
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(window,width=e.width))
        content.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        self.detail.set(r['id'])
        tk.Label(content,text=r['material'],bg=PANEL,fg=FG,font=('Segoe UI',17,'bold'),
                 anchor='w').pack(fill='x')
        tk.Label(content,text=r['description'],bg=PANEL,fg=MUTED,font=('Segoe UI',10),
                 justify='left',anchor='w',wraplength=270).pack(fill='x',pady=(1,11))
        shown_status='Stok habis' if r['stock']==0 else r['status']
        color,ink=COLORS[shown_status]
        summary=tk.Frame(content,bg='#182F45',padx=11,pady=10)
        summary.pack(fill='x',pady=(0,12))
        tk.Label(summary,text='STATUS SAAT INI',bg='#182F45',fg=MUTED,
                 font=('Segoe UI',8,'bold')).pack(anchor='w',pady=(0,5))
        tk.Label(summary,text=shown_status,bg=color,fg=ink,font=('Segoe UI',10,'bold'),
                 padx=10,pady=5).pack(anchor='w')
        tk.Label(summary,text=f"Stok tersedia  {r['stock']} unit",bg='#182F45',fg=FG,
                 font=('Segoe UI',10,'bold')).pack(anchor='w',pady=(9,0))
        advice = r.get('recommendation')
        if advice:
            source = ' · Simulasi' if advice.get('source') == 'Simulasi' else ''
            tk.Label(content,text='SARAN SISTEM' + source,bg=PANEL,fg=MUTED,
                     font=('Segoe UI',9,'bold')).pack(anchor='w',pady=(1,5))
            tk.Label(content,text=advice['title'],bg=PANEL,fg=ink if r['stock'] else MUTED,
                     font=('Segoe UI',11,'bold'),anchor='w',justify='left',
                     wraplength=270).pack(fill='x')
            tk.Label(content,text=advice['reason'],bg=PANEL,fg=MUTED,
                     font=('Segoe UI',9),anchor='w',justify='left',
                     wraplength=270).pack(fill='x',pady=(3,4))
            tk.Label(content,text=advice['next_action'],bg=PANEL,fg=FG,
                     font=('Segoe UI',10),anchor='w',justify='left',
                     wraplength=270).pack(fill='x',pady=(0,11))
            options = advice.get('options') or ()
            if options:
                tk.Label(content,text='PILIHAN TUJUAN',bg=PANEL,fg=MUTED,
                         font=('Segoe UI',9,'bold')).pack(anchor='w',pady=(0,5))
                for number, option in enumerate(options, start=1):
                    option_card = tk.Frame(content,bg='#182F45',padx=9,pady=7)
                    option_card.pack(fill='x',pady=(0,7))
                    tk.Label(option_card,text=f"{number}. {option['title']}",bg='#182F45',fg=FG,
                             font=('Segoe UI',10,'bold'),anchor='w',justify='left',
                             wraplength=252).pack(fill='x')
                    tk.Label(option_card,text=option['reason'],bg='#182F45',fg=MUTED,
                             font=('Segoe UI',9),anchor='w',justify='left',
                             wraplength=252).pack(fill='x',pady=(3,0))
        action = r.get('latest_action')
        tk.Label(content,text='KEPUTUSAN PETUGAS',bg=PANEL,fg=MUTED,
                 font=('Segoe UI',9,'bold')).pack(anchor='w',pady=(1,5))
        if action:
            action_title = f"{action['choice']} · {action['action_status']}"
            if r['stock'] == 0:
                action_title += ' (stok habis)'
            tk.Label(content,text=action_title,bg=PANEL,fg=FG,
                     font=('Segoe UI',10,'bold'),anchor='w',justify='left',
                     wraplength=270).pack(fill='x')
            if action.get('target_kind') and action.get('target_code'):
                target_type='Customer' if action['target_kind']=='customer' else 'Site'
                tk.Label(content,text=f"Tujuan keputusan: {target_type} {action['target_code']}",
                         bg=PANEL,fg='#83C5FF',font=('Segoe UI',10,'bold'),
                         anchor='w',justify='left',wraplength=270).pack(fill='x',pady=(4,0))
            tk.Label(content,text=f"Kondisi: {action['physical_condition']}\nAlasan: {action['reason']}",
                     bg=PANEL,fg=MUTED,font=('Segoe UI',9),anchor='w',justify='left',
                     wraplength=270).pack(fill='x',pady=(3,3))
            tk.Label(content,text=f"Diputuskan oleh {action['officer']} · {display_time(action['decided_at'])}",
                     bg=PANEL,fg=MUTED,font=('Segoe UI',9),anchor='w',justify='left',
                     wraplength=270).pack(fill='x',pady=(0,11))
            if action['completed_at']:
                tk.Label(content,text=f"Diselesaikan oleh {action['completed_by']} · {display_time(action['completed_at'])}\n{action['completion_note']}",
                         bg=PANEL,fg='#70E5B3',font=('Segoe UI',9),anchor='w',justify='left',
                         wraplength=270).pack(fill='x',pady=(0,11))
        else:
            tk.Label(content,text='Belum ada keputusan. Catat setelah pemeriksaan pada halaman Pengecekan.',
                     bg=PANEL,fg=MUTED,font=('Segoe UI',9),anchor='w',justify='left',
                     wraplength=270).pack(fill='x',pady=(0,11))
        actions=tk.Frame(content,bg=PANEL)
        actions.pack(fill='x')
        actions.columnconfigure((0,1),weight=1,uniform='detail-actions')
        self.action_button(actions,'Edit batch',lambda:self.edit_batch(r)).grid(row=0,column=0,sticky='ew',padx=(0,4))
        self.action_button(actions,'Lihat label QR',lambda:self.show_label(r['id'])).grid(row=0,column=1,sticky='ew',padx=(4,0))
        history=self.action_button(content,'Lihat riwayat keluar',lambda:self.show_stock_history(r['id']))
        history.configure(bg=PANEL,fg='#82C9FF',highlightbackground=PANEL,padx=0)
        history.pack(anchor='w',pady=(3,13))
        tk.Frame(content,bg=EDGE,height=1).pack(fill='x',pady=(0,10))
        tk.Label(content,text='INFORMASI BATCH',bg=PANEL,fg=MUTED,
                 font=('Segoe UI',9,'bold')).pack(anchor='w',pady=(0,8))
        details=(('ID batch',r['id']),('Lokasi',r['location_code']),
                 ('Kolom',f"{r['column']:02d}"),('Baris',f"{r['row']:02d}"),
                 ('Tingkat',f"{r['level']:02d}"),
                 ('Tanggal masuk',r['received_date']),('Umur',f"{r['age']} hari"),
                 ('Plant',r['plant']),('Storage Location',r['storage_location']))
        for name,value in details:
            field=tk.Frame(content,bg=PANEL)
            field.pack(fill='x',pady=(0,8))
            tk.Label(field,text=name,bg=PANEL,fg=MUTED,font=('Segoe UI',9),
                     anchor='w',width=16).pack(side='left',anchor='n')
            tk.Label(field,text=str(value),bg=PANEL,fg=FG,font=('Segoe UI',9,'bold'),
                     justify='left',anchor='w',wraplength=160).pack(side='left',fill='x',expand=True)
        def bind_wheel(widget):
            widget.bind('<MouseWheel>',lambda e:canvas.yview_scroll(-1 if e.delta>0 else 1,'units'))
            for child in widget.winfo_children():bind_wheel(child)
        bind_wheel(content)

    def show_locations(self):
        from .location_ui import LocationPage
        self.page="Lokasi"
        self.title.configure(text="Data Barang / Lokasi")
        for name,b in self.nav.items():
            selected=name=='Data Barang'
            b.configure(bg='#164F84' if selected else SIDEBAR)
            self.nav_markers[name].configure(bg='#69C3FF' if selected else SIDEBAR)
        for child in self.body.winfo_children():child.destroy()
        self.location_page=LocationPage(self)

    def check_day(self):
        self.header_time.configure(text=datetime.now().strftime('%d %b %Y  %H:%M'))
        if date.today()!=self.today:
            self.today=date.today()
            if self.page not in ("Lokasi","Pengecekan"):self.show(self.page)
        self.timer=self.root.after(30000,self.check_day)

    def close(self):
        self.closing = True
        self.stop_camera()
        self.live_monitor.stop()
        self.root.after_cancel(self.timer)
        self.root.after_cancel(self.live_timer)
        self.db.close()
        self.root.destroy()

    def stop_camera(self):
        camera=getattr(self,'camera_window',None)
        if camera is not None and camera.winfo_exists():camera.destroy()
        self.camera_window=None
