"""Desktop overview: live inventory, a schematic floorplan and inspection shortcuts."""
import tkinter as tk
from tkinter import ttk
from datetime import datetime
from pathlib import Path
from .dashboard import overview
from .recommendation_data import recommendation_context
from .recommendations import recommend_for
from .rack_map import RackMap, STATUS
from .visuals import icon
from .ui import BG, PANEL, FG, MUTED, BLUE, STATUS_BACKGROUNDS

EDGE = '#203D58'
INK = {name: colors[0] for name, colors in STATUS.items()}
FILL = dict(STATUS_BACKGROUNDS, **{'Tanpa stok': '#253447'})
RACK_ASSET = Path(__file__).resolve().parent.parent / 'assets' / 'warehouse' / 'rack_3x3_dark.png'
CARTON_ASSET = Path(__file__).resolve().parent.parent / 'assets' / 'warehouse' / 'carton_blank_label.png'
LABEL_COLORS = {
    'Normal': ('#EAFBF3', '#14734E'),
    'Warning': ('#FFF5D8', '#916006'),
    'Melewati batas': ('#FFE8E8', '#AF2637'),
    'Tanpa stok': ('#E6EDF3', '#526579'),
    'Data perlu diperbaiki': ('#F2EAFE', '#684A99'),
}


class DashboardPage:
    def __init__(self, app):
        self.app, self.body = app, app.body
        self.area = tk.StringVar(value='Semua area')
        self.selected_rack = self.highlight = self.selected_item = None
        self.images = {}
        self.wrap = tk.Frame(self.body, bg=BG)
        self.wrap.pack(fill='both', expand=True)
        self.wrap.columnconfigure(0, weight=1)
        self.wrap.rowconfigure(1, weight=1)
        self.metrics = tk.Frame(self.wrap, bg=BG)
        self.metrics.grid(row=0, column=0, sticky='ew', pady=(0, 12))
        self.viewport = tk.Frame(self.wrap, bg=BG)
        self.viewport.grid(row=1, column=0, sticky='nsew')
        self.viewport.columnconfigure(0, weight=1)
        self.viewport.rowconfigure(0, weight=1)
        self.scroll_canvas = tk.Canvas(self.viewport,bg=BG,highlightthickness=0)
        self.scroll_canvas.grid(row=0,column=0,sticky='nsew')
        self.vertical_scroll=ttk.Scrollbar(self.viewport,command=self.scroll_canvas.yview)
        self.horizontal_scroll=ttk.Scrollbar(self.viewport,orient='horizontal',command=self.scroll_canvas.xview)
        self.scroll_canvas.configure(yscrollcommand=self.vertical_scroll.set,xscrollcommand=self.horizontal_scroll.set)
        self.host = tk.Frame(self.scroll_canvas, bg=BG)
        self.host_window=self.scroll_canvas.create_window(0,0,window=self.host,anchor='nw')
        self.host.rowconfigure(0, weight=1)
        self.host.columnconfigure(0, weight=7, uniform='dashboard')
        self.host.columnconfigure(1, weight=3, uniform='dashboard')
        self.left = tk.Frame(self.host, bg=BG)
        self.left.grid(row=0, column=0, sticky='nsew', padx=(0, 12))
        self.left.columnconfigure(0, weight=1)
        self.left.rowconfigure(0, weight=3, minsize=220)
        self.left.rowconfigure(1, weight=1, minsize=186)
        self.right = tk.Frame(self.host, bg=BG)
        self.right.grid(row=0, column=1, sticky='nsew')
        self.right.columnconfigure(0, weight=1)
        self.right.rowconfigure(0, weight=1, minsize=190)
        self.right.rowconfigure(1, weight=0)
        self.right.rowconfigure(2, weight=0)
        self.build_map()
        self.build_priorities()
        self.build_camera()
        self.build_information()
        self.build_activity()
        self.viewport.bind('<Configure>',self.layout)
        self.camera_panel.bind('<Configure>',self.layout)
        self.info_panel.bind('<Configure>',self.layout)
        self.activity_panel.bind('<Configure>',self.layout)
        self.bind_scroll(self.host)
        self.reload(initial=True)

    def layout(self,event=None):
        """Keep text readable; expose overflow only when the window is too small."""
        width,height=self.viewport.winfo_width(),self.viewport.winfo_height()
        if width<2 or height<2:return
        camera_min=self.camera_panel.winfo_reqheight()-self.camera_canvas.winfo_reqheight()+48
        min_height=max(406,camera_min+self.info_panel.winfo_reqheight()+self.activity_panel.winfo_reqheight()+20)
        min_width=940
        vertical=height<min_height
        horizontal=width-(12 if vertical else 0)<min_width
        vertical=height-(12 if horizontal else 0)<min_height
        if vertical:self.vertical_scroll.grid(row=0,column=1,sticky='ns')
        else:self.vertical_scroll.grid_remove()
        if horizontal:self.horizontal_scroll.grid(row=1,column=0,sticky='ew')
        else:self.horizontal_scroll.grid_remove()
        available_width=max(1,width-(12 if vertical else 0))
        available_height=max(1,height-(12 if horizontal else 0))
        content_width=max(min_width,available_width)
        content_height=max(min_height,available_height)
        self.scroll_canvas.itemconfigure(self.host_window,width=content_width,height=content_height)
        self.scroll_canvas.configure(scrollregion=(0,0,content_width,content_height))
        if not vertical:self.scroll_canvas.yview_moveto(0)
        if not horizontal:self.scroll_canvas.xview_moveto(0)

    def bind_scroll(self,widget):
        if isinstance(widget,(ttk.Treeview,ttk.Scrollbar)):return
        widget.bind('<MouseWheel>',self.scroll_page,add='+')
        for child in widget.winfo_children():self.bind_scroll(child)

    def scroll_page(self,event):
        if self.vertical_scroll.winfo_ismapped():
            self.scroll_canvas.yview_scroll(-1 if event.delta>0 else 1,'units')
            return 'break'

    def panel(self, parent):
        return tk.Frame(parent, bg=PANEL, highlightbackground=EDGE, highlightthickness=1)

    def label(self, parent, text='', size=10, color=MUTED, bold=False, **kwargs):
        return tk.Label(parent, text=text, bg=PANEL, fg=color, anchor='w',
                        font=('Segoe UI', size, 'bold' if bold else 'normal'),
                        borderwidth=0, **dict({'padx':0,'pady':0}, **kwargs))

    def action(self, parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command, bg=BLUE if primary else PANEL,
                         fg=FG if primary else '#63B9FF', activebackground='#205588',
                         activeforeground=FG, relief='flat', borderwidth=0,
                         font=('Segoe UI', 10), padx=8, pady=5, cursor='hand2')

    def build_map(self):
        self.map_panel = self.panel(self.left)
        self.map_panel.grid(row=0, column=0, sticky='nsew', pady=(0, 10))
        header = tk.Frame(self.map_panel, bg=PANEL)
        header.pack(fill='x', padx=14, pady=(9, 4))
        self.action(header, 'Perbarui data', self.reload).pack(side='right', padx=(6, 0))
        self.area_box = ttk.Combobox(header, textvariable=self.area, state='readonly',
                                     width=14, style='Warehouse.TCombobox')
        self.area_box.pack(side='right', padx=(8, 0))
        self.area_box.bind('<<ComboboxSelected>>', lambda e: self.reload())
        self.label(header, 'Peta Status Lokasi', 14, FG, True).pack(anchor='w')
        self.label(header, 'Tampak atas · klik section untuk melihat baris dan tingkat', 10).pack(anchor='w')
        legend = tk.Frame(self.map_panel, bg=PANEL)
        legend.pack(side='bottom', fill='x', padx=12, pady=7)
        self.last_button = self.action(legend, 'Sorot scan terakhir', self.focus_last)
        self.last_button.pack(side='right')
        for name, title in [('Normal', 'Normal'), ('Warning', 'Warning'), ('Melewati batas', 'Lewat batas'), ('Tanpa stok', 'Kosong')]:
            self.label(legend, '●', 11, INK[name]).pack(side='left', padx=(0, 3))
            self.label(legend, title, 9).pack(side='left', padx=(0, 9))
        self.map_canvas = RackMap(self.map_panel, self.pick_section)
        self.map_canvas.pack(fill='both', expand=True, padx=12, pady=(3, 0))

    def build_priorities(self):
        self.priority_panel = self.panel(self.left)
        self.priority_panel.grid(row=1, column=0, sticky='nsew')
        header = tk.Frame(self.priority_panel, bg=PANEL)
        header.pack(fill='x', padx=14, pady=(7, 4))
        self.action(header, 'Lihat semua prioritas', self.all_priorities).pack(side='right')
        self.label(header, 'Prioritas Pemeriksaan', 13, FG, True).pack(side='left')
        host = tk.Frame(self.priority_panel, bg=PANEL)
        host.pack(fill='both', expand=True, padx=12, pady=(0, 9))
        host.columnconfigure(0, weight=1)
        host.rowconfigure(0, weight=1)
        self.priority_tree = ttk.Treeview(host, columns=('material', 'location', 'age', 'over'),
                                         show='headings', height=3, style='Dashboard.Treeview', selectmode='browse')
        for name, title, width in [('material', 'Material', 180), ('location', 'Bin', 175), ('age', 'Umur', 100), ('over', 'Lewat batas', 105)]:
            self.priority_tree.heading(name, text=title, anchor='w')
            self.priority_tree.column(name, width=width, minwidth=70, anchor='w')
        self.priority_tree.grid(row=0, column=0, sticky='nsew')
        # The compact table shows the first few rows; the named action opens
        # the full list. Keep mouse-wheel navigation without a permanent bar.
        self.priority_tree.bind('<<TreeviewSelect>>', self.select_priority)
        self.priority_tree.bind('<Double-1>', lambda e: self.open_priority())
        self.priority_tree.bind('<Return>', lambda e: self.open_priority())
        for name in INK:
            self.priority_tree.tag_configure(name, foreground=INK[name])
        self.priority_empty = self.label(self.priority_tree, 'Tidak ada barang yang perlu diprioritaskan.', 10)

    def build_camera(self):
        self.camera_panel = self.panel(self.right)
        self.camera_panel.grid(row=0, column=0, sticky='nsew', pady=(0, 10))
        self.label(self.camera_panel, 'Kamera Pengecekan', 13, FG, True).pack(fill='x', padx=12, pady=(8, 5))
        self.scan_button = self.action(self.camera_panel, '  Mulai Pengecekan', self.start_check, True)
        self.images['scan'] = icon('scan', 22, FG, master=self.app.root)
        self.scan_button.configure(image=self.images['scan'], compound='left', pady=7, font=('Segoe UI', 11, 'bold'))
        self.scan_button.pack(side='bottom', fill='x', padx=12, pady=(5, 10))
        self.camera_banner = self.label(self.camera_panel, '●  Kamera belum aktif', 9, '#A9C5DD', padx=8, pady=5)
        self.camera_banner.configure(bg='#1A334B')
        self.camera_banner.bind('<Configure>',lambda e:self.camera_banner.configure(wraplength=max(100,e.width-16)))
        self.camera_banner.pack(side='bottom', fill='x', padx=12)
        self.camera_canvas = tk.Canvas(self.camera_panel, bg='#081A2B', highlightthickness=0, height=120)
        self.camera_canvas.pack(fill='both', expand=True, padx=12, pady=(0, 5))
        self.camera_canvas.bind('<Configure>', lambda e: self.draw_camera())

    def draw_camera(self):
        canvas = self.camera_canvas
        canvas.delete('all')
        w, h = canvas.winfo_width(), canvas.winfo_height()
        frame = getattr(self.app, 'last_camera_frame', None)
        if frame is not None:
            from PIL import Image, ImageTk
            photo = Image.fromarray(frame[:, :, ::-1])
            photo.thumbnail((max(1, w), max(1, h)), Image.Resampling.LANCZOS)
            self.images['camera'] = ImageTk.PhotoImage(photo)
            canvas.create_image(w / 2, h / 2, image=self.images['camera'])
            self.camera_banner.configure(text='Hasil scan terakhir • kamera tidak aktif')
            return
        for x in range(0, w, 26):
            canvas.create_line(x, 0, x, h, fill='#102A40')
        for y in range(0, h, 26):
            canvas.create_line(0, y, w, y, fill='#102A40')
        if 'standby' not in self.images:
            self.images['standby'] = icon('scan', 28, '#79B3DB', master=self.app.root)
        if h<90:
            canvas.create_image(w/2-98,h/2,image=self.images['standby'])
            canvas.create_text(w/2+14,h/2,text='Siap memeriksa barang',fill='#97B6D2',font=('Segoe UI',9))
            return
        size = min(65, h * .46)
        x, y = w / 2, max(size / 2 + 5, h / 2 - 11)
        r = size / 2
        for dx, dy in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            canvas.create_line(x + dx * (r-10), y + dy*r, x + dx*r, y + dy*r,
                               x + dx*r, y + dy*(r-10), fill='#52AEF5', width=2)
        canvas.create_image(x, y, image=self.images['standby'])
        canvas.create_text(w / 2, min(h - 12, y + r + 19), text='Siap memeriksa barang',
                           fill='#97B6D2', font=('Segoe UI', 9))

    def build_information(self):
        self.info_panel = self.panel(self.right)
        self.info_panel.grid(row=1, column=0, sticky='nsew', pady=(0, 10))
        header = tk.Frame(self.info_panel, bg=PANEL)
        header.pack(fill='x', padx=12, pady=(7, 3))
        self.label(header, 'Informasi Barang', 12, FG, True).pack(side='left')
        self.info_detail = self.action(header, 'Detail ↗', lambda: self.open_item(self.selected_item['id']) if self.selected_item else None)
        self.info_detail.configure(font=('Segoe UI',9),pady=1)
        self.info_detail.pack(side='right')
        tk.Frame(self.info_panel, bg=EDGE, height=1).pack(fill='x', padx=12)
        grid = tk.Frame(self.info_panel, bg=PANEL)
        grid.pack(fill='x', padx=12, pady=4)
        grid.columnconfigure(1, weight=1)
        self.info_fields = {}
        for title, i, column in (('Material',0,0),('Bin',1,0),('Umur',2,0),('Batas',2,2),('Status',3,0)):
            self.label(grid, title, 9).grid(row=i, column=column, sticky='w', padx=(0, 10),pady=2)
            value = self.label(grid, '—', 9, FG, True)
            value.grid(row=i, column=column+1, columnspan=3 if title in ('Material','Bin','Status') else 1, sticky='w',pady=2)
            self.info_fields[title] = value
        self.info_caption = self.label(self.info_panel, 'Pilih barang dari peta atau tabel', 8)
        self.info_caption.configure(justify='left', anchor='w', wraplength=270)
        self.info_caption.pack(fill='x', padx=12, pady=(0, 5))

    def build_activity(self):
        self.activity_panel = self.panel(self.right)
        self.activity_panel.grid(row=2, column=0, sticky='nsew')
        self.label(self.activity_panel, 'Aktivitas Hari Ini', 12, FG, True).pack(fill='x', padx=12, pady=(6, 3))
        tk.Frame(self.activity_panel, bg=EDGE, height=1).pack(fill='x', padx=12)
        self.activity_checked = self.label(self.activity_panel, size=9, color=FG)
        self.activity_checked.pack(fill='x', padx=14, pady=(5, 1))
        self.activity_drafts = self.label(self.activity_panel, size=9, color=FG)
        self.activity_drafts.pack(fill='x', padx=14, pady=1)
        self.report_button=self.action(self.activity_panel, 'Lihat laporan →', lambda: self.app.show('Laporan'))
        self.report_button.configure(font=('Segoe UI',9),pady=2)
        self.report_button.pack(anchor='w', padx=5,pady=(1,4))

    def reload(self, initial=False):
        self.data = overview(self.app.db, '' if self.area.get() == 'Semua area' else self.area.get())
        self.area_box.configure(values=['Semua area', *self.data['areas']])
        last = self.data['last']
        if self.highlight is not None:
            self.highlight = self.data.get('last_current_location_code') if last else None
        if self.selected_rack not in self.data['racks']:
            self.selected_rack = None
        self.last_button.configure(state='normal' if last else 'disabled')
        for child in self.metrics.winfo_children():
            child.destroy()
        cards = [('Total item/batch', len(self.data['active']), FG, 'box'),
                 *[(s, self.data['counts'][s], INK[s], k) for s, k in [('Normal', 'check'), ('Warning', 'warning'), ('Melewati batas', 'alert')]]]
        for i, (title, count, color, kind) in enumerate(cards):
            self.metrics.columnconfigure(i, weight=1, uniform='cards')
            card = self.panel(self.metrics)
            card.grid(row=0, column=i, sticky='nsew', padx=(0, 10 if i < 3 else 0))
            self.images[kind] = icon(kind, 38, color if i else '#97BDE7', master=self.app.root)
            tk.Label(card, image=self.images[kind], bg=PANEL).pack(side='left', padx=(14, 12), pady=9)
            info = tk.Frame(card, bg=PANEL)
            info.pack(side='left', fill='both', expand=True, pady=6)
            self.label(info, title, 11).pack(anchor='w')
            self.label(info, str(count), 25, color, True).pack(anchor='w')
        self.map_canvas.set_data(self.data['racks'], self.highlight, self.selected_rack)
        self.priority_tree.delete(*self.priority_tree.get_children())
        self.priority_rows = {row['id']: row for row in self.data['priorities']}
        for row in self.data['priorities']:
            age = row['age']
            over = f"{age - self.data['age_limit']} hari" if isinstance(age, int) and age > self.data['age_limit'] else '—'
            self.priority_tree.insert('', 'end', iid=row['id'], values=(row['material'], row['location_code'], f'{age} hari' if isinstance(age, int) else 'Periksa tanggal', over), tags=(row['status'],))
        self.priority_empty.place_forget()
        if not self.priority_rows:
            self.priority_empty.place(relx=.5, rely=.6, anchor='center')
        previous = self.selected_item['id'] if self.selected_item else (last['batch_id'] if last else None)
        self.selected_item = next((r for r in self.data['rows'] if r['id'] == previous), None)
        self.update_info()
        activity = self.data['activity_today']
        self.activity_checked.configure(text=f"{activity['checked_batches']} batch diperiksa hari ini")
        self.activity_drafts.configure(text=f"{activity['draft_count']} draft laporan • semua area")
        self.app.footer.configure(text=f"Data simulasi • Status per {self.data['today']} • Normal ≤ {self.data['normal_max']} hari / Warning ≤ {self.data['age_limit']} hari • {self.data['counts']['Data perlu diperbaiki']} data perlu diperbaiki")
        self.layout()

    def update_info(self):
        row = self.selected_item
        values = {'Material': row['material'], 'Bin': row['location_code'],
                  'Umur': f"{row['age']} hari", 'Batas': f"{self.data['age_limit']} hari",
                  'Status': '●  ' + row['status']} if row else {}
        for title, label in self.info_fields.items():
            label.configure(text=values.get(title, '—'), fg=INK[row['status']] if row and title == 'Status' else FG)
        self.info_detail.configure(state='normal' if row else 'disabled')
        latest = self.data['latest_item']
        caption = 'Status inventory saat ini' if row else 'Pilih barang dari peta atau tabel'
        if row and latest and row['id'] == latest['batch_id']:
            when = datetime.fromisoformat(latest['last_seen_at']).astimezone().strftime('%d/%m/%y %H:%M')
            caption = 'Terakhir dicek: ' + when
        if row and row['stock'] > 0:
            context = recommendation_context(self.app.db, row['material'])
            if context['sites'] or context['customers']:
                advice = recommend_for(row, context=context)
                options = advice.get('options') or []
                if options:
                    caption = f"Simulasi • {options[0]['title']}\n{caption}"
        self.info_caption.configure(text=caption)

    def select_priority(self, event=None):
        chosen = self.priority_tree.selection()
        if not chosen or chosen[0] not in self.priority_rows:
            return
        self.selected_item = self.priority_rows[chosen[0]]
        self.selected_rack = tuple(self.selected_item['location_code'].split('-')[:2])
        self.map_canvas.set_data(self.data['racks'], self.highlight, self.selected_rack)
        self.update_info()

    def open_priority(self):
        chosen = self.priority_tree.selection()
        if chosen:
            self.open_item(chosen[0])

    def focus_last(self):
        last = self.data['last']
        if not last:
            return
        self.area.set('Semua area')
        self.highlight = self.data.get('last_current_location_code')
        self.selected_rack = tuple(self.highlight.split('-')[:2]) if self.highlight else None
        self.selected_item = next((r for r in self.app.inventory.list_batches() if r['id'] == last['batch_id']), None)
        self.reload()

    def start_check(self):
        self.app.show('Pengecekan')
        page = self.app.session_page
        page.start_form(on_started=page.open_camera)

    def pick_section(self, key, column, row):
        """Show one side elevation, using the clicked section to select its column."""
        self._hide_rack_tip()
        self.highlight = None
        self.selected_rack = key
        self.selected_column = column
        self.selected_row = row
        self.map_canvas.set_data(self.data['racks'], self.highlight, key)
        rack = self.data['racks'][key]
        screen_w = self.app.root.winfo_screenwidth()
        screen_h = self.app.root.winfo_screenheight()
        win = getattr(self, 'rack_window', None)
        if win is None or not win.winfo_exists():
            win = self.dialog(f'Rak {key[1]} · Kolom {column:02d}',
                              f'{min(940, screen_w - 80)}x{min(670, screen_h - 80)}')
        else:
            for child in win.winfo_children():
                child.destroy()
            win.title(f'Rak {key[1]} · Kolom {column:02d}')
        self.rack_window = win
        columns = sorted({c['column'] for c in rack['cells']})
        levels = sorted({c['level'] for c in rack['cells']}, reverse=True)
        rows = sorted({c['row'] for c in rack['cells']})
        column_cells = [cell for cell in rack['cells'] if cell['column'] == column]
        lookup = {(c['level'], c['row']): c for c in column_cells}
        header = tk.Frame(win, bg=BG)
        header.pack(fill='x', padx=20, pady=(15, 8))
        tk.Label(header, text=f'AREA {key[0]}   ›   RAK {key[1]}   ›   KOLOM {column:02d}', bg=BG, fg='#8FB9DC',
                 font=('Segoe UI', 9, 'bold'), anchor='w').pack(fill='x')
        heading = tk.Frame(header, bg=BG)
        heading.pack(fill='x', pady=(3, 0))
        tk.Label(heading, text=f'Rak {key[1]} — Tampak Samping Kolom {column:02d}', bg=BG, fg=FG,
                 font=('Segoe UI', 18, 'bold'), anchor='w').pack(side='left')
        column_summary = rack['columns'][column]
        status_ink = INK.get(column_summary['status'], MUTED)
        tk.Label(heading, text=column_summary['status'].upper(), bg=FILL.get(column_summary['status'], PANEL),
                 fg=status_ink, font=('Segoe UI', 9, 'bold'), padx=10, pady=5,
                 highlightbackground=status_ink, highlightthickness=1).pack(side='right')
        tk.Label(header, text=(f"Baris 01–03 dari kiri ke kanan · Tingkat 03–01 dari atas ke bawah  |  "
                               f"{column_summary['batches']} batch aktif di kolom"),
                 bg=BG, fg=MUTED, font=('Segoe UI', 10), anchor='w').pack(fill='x', pady=(4, 0))

        navigation = tk.Frame(win, bg=BG)
        navigation.pack(fill='x', padx=20, pady=(0, 8))
        index = columns.index(column)
        previous = columns[index - 1] if index > 0 else None
        following = columns[index + 1] if index + 1 < len(columns) else None
        self.previous_column_button = self.action(
            navigation, f'‹ Kolom {previous:02d}' if previous else '‹ Sebelumnya',
            lambda: self.pick_section(key, previous, row))
        self.previous_column_button.configure(state='normal' if previous else 'disabled')
        self.previous_column_button.pack(side='left')
        self.next_column_button = self.action(
            navigation, f'Kolom {following:02d} ›' if following else 'Berikutnya ›',
            lambda: self.pick_section(key, following, row))
        self.next_column_button.configure(state='normal' if following else 'disabled')
        self.next_column_button.pack(side='right')
        tk.Label(navigation, text=f'Kolom {column:02d} dari {len(columns)} · Baris {row:02d} dipilih',
                 bg=BG, fg='#8ED2FF', font=('Segoe UI', 10, 'bold')).pack(expand=True)

        stage = tk.Frame(win, bg='#0C2034', highlightbackground=EDGE, highlightthickness=1)
        stage.pack(fill='both', expand=True, padx=20, pady=(0, 8))
        canvas = tk.Canvas(stage, bg='#0C2034', highlightthickness=0)
        canvas.pack(fill='both', expand=True, padx=2, pady=2)
        self.rack_detail_canvas = canvas
        hint = tk.Frame(win, bg=BG)
        hint.pack(fill='x', padx=20, pady=(0, 13))
        tk.Label(hint, text='Baris terpilih disorot biru · Klik lokasi untuk melihat barang',
                 bg=BG, fg=MUTED, font=('Segoe UI', 10), anchor='w').pack(side='left')
        for state in ('Normal', 'Warning', 'Melewati batas', 'Tanpa stok'):
            tk.Label(hint, text='●', bg=BG, fg=INK[state], font=('Segoe UI', 11)).pack(side='left', padx=(12, 2))
            tk.Label(hint, text='Kosong' if state == 'Tanpa stok' else state,
                     bg=BG, fg=MUTED, font=('Segoe UI', 9)).pack(side='left')

        from PIL import Image, ImageTk
        rack_source = Image.open(RACK_ASSET).convert('RGBA') if RACK_ASSET.exists() else None
        carton_source = Image.open(CARTON_ASSET).convert('RGBA') if CARTON_ASSET.exists() else None
        if carton_source is not None:
            # Generated artwork has transparent padding. Crop it before
            # scaling so the carton remains legible at desktop modal sizes.
            carton_source = carton_source.crop(carton_source.getbbox())
        self.cell_buttons = {}
        windows = {}
        for cell in column_cells:
            state = cell['status']
            light, dark = LABEL_COLORS.get(state, LABEL_COLORS['Data perlu diperbaiki'])
            caption = f"● R{cell['row']:02d} · T{cell['level']:02d}\n{state}"
            if cell['stock'] > 0:
                caption += f"\n{cell['batches']} batch · {cell['stock']} unit"
            button = tk.Button(canvas, text=caption,
                               command=lambda c=cell: self._open_rack_cell(c),
                               bg=light, fg=dark, activebackground='#D3EAFC', activeforeground='#0A3F69',
                               relief='flat', borderwidth=0, font=('Segoe UI', 9, 'bold'),
                               cursor='hand2', takefocus=True,
                               highlightthickness=2,
                               highlightbackground='#6DC6FF' if cell['row'] == row or cell['code'] == self.highlight else light,
                               highlightcolor='#6DC6FF')
            button.bind('<Enter>', lambda e, c=cell: self._show_rack_tip(e, c))
            button.bind('<Leave>', lambda e: self._hide_rack_tip())
            button.bind('<FocusIn>', lambda e, c=cell: self._show_rack_tip(e, c))
            button.bind('<FocusOut>', lambda e: self._hide_rack_tip())
            windows[cell['code']] = canvas.create_window(0, 0, window=button, width=1, height=1)
            self.cell_buttons[cell['code']] = button

        def draw(event=None):
            if not canvas.winfo_exists():
                return
            w, h = canvas.winfo_width(), canvas.winfo_height()
            if w < 100 or h < 100:
                return
            canvas.delete('rack_art')
            # Keep Tk images alive while Canvas displays them.
            photos = []
            canvas.create_rectangle(0, 0, w, h, fill='#0C2034', outline='', tags='rack_art')
            canvas.create_rectangle(10, h - 23, w - 10, h - 11,
                                    fill='#162C3C', outline='', tags='rack_art')
            use_asset = rack_source is not None and len(levels) == len(rows) == 3
            if use_asset:
                art_h = max(100, h - 49)
                art_w = min(w - 140, art_h * 1.48)
                art_h = art_w / 1.48
                left, top = (w - art_w) / 2 + 15, 32 + max(0, (h - art_h - 45) / 2)
                x_centers = [left + art_w * f for f in (.222, .501, .779)]
                y_centers = [top + art_h * f for f in (.274, .585, .850)]
                carton_w, carton_h = art_w * .238, art_h * .222
            else:
                cols, tier_count = max(1, len(rows)), max(1, len(levels))
                cell_w = min(184, (w - 126) / cols)
                cell_h = min(145, (h - 72) / tier_count)
                art_w, art_h = cols * cell_w, tier_count * cell_h
                left, top = (w - art_w) / 2 + 13, 37 + max(0, (h - art_h - 49) / 2)
                x_centers = [left + cell_w * (i + .5) for i in range(cols)]
                y_centers = [top + cell_h * (i + .5) for i in range(tier_count)]
                carton_w, carton_h = cell_w * .82, cell_h * .68
                canvas.create_rectangle(left - 5, top - 4, left + art_w + 5, top + art_h + 5,
                                        fill='#16283A', outline='#607F98', width=3, tags='rack_art')
                for i in range(cols + 1):
                    xx = left + i * cell_w
                    canvas.create_rectangle(xx - 5, top - 4, xx + 5, top + art_h + 5,
                                            fill='#355674', outline='#7192AB', tags='rack_art')
                for i in range(tier_count + 1):
                    yy = top + i * cell_h
                    canvas.create_rectangle(left - 5, yy - 4, left + art_w + 5, yy + 5,
                                            fill='#355674', outline='#7192AB', tags='rack_art')

            for j, baris in enumerate(rows):
                canvas.create_text(x_centers[j], top - 16, text=f'BARIS {baris:02d}',
                                   fill='#8ED2FF' if baris == row else '#C8DBEC',
                                   font=('Segoe UI', 10, 'bold'), tags='rack_art')
            for i, level in enumerate(levels):
                canvas.create_text(left - 18, y_centers[i], text=f'TINGKAT\n{level:02d}',
                                   anchor='e', justify='right', fill='#C8DBEC',
                                   font=('Segoe UI', 9, 'bold'), tags='rack_art')

            if carton_source is not None:
                carton_photo = ImageTk.PhotoImage(carton_source.resize(
                    (max(1, int(carton_w)), max(1, int(carton_h))), Image.Resampling.LANCZOS))
                photos.append(carton_photo)
            else:
                carton_photo = None
            for i, level in enumerate(levels):
                for j, baris in enumerate(rows):
                    cell = lookup.get((level, baris))
                    x, y = x_centers[j], y_centers[i]
                    if cell and cell['stock'] > 0:
                        if carton_photo:
                            canvas.create_image(x, y, image=carton_photo, tags='rack_art')
                        else:
                            canvas.create_rectangle(x - carton_w / 2, y - carton_h / 2,
                                                    x + carton_w / 2, y + carton_h / 2,
                                                    fill='#B99467', outline='#D6B78B', tags='rack_art')
                    elif not cell or not cell['batches']:
                        canvas.create_rectangle(x - carton_w / 2, y - carton_h / 2,
                                                x + carton_w / 2, y + carton_h / 2,
                                                fill='#142C3C', outline='#47647B', dash=(4, 3),
                                                tags='rack_art')
                        if not cell:
                            canvas.create_text(x, y, text='LOKASI BELUM\nTERDAFTAR',
                                               fill='#9BB1C3', font=('Segoe UI', 8),
                                               justify='center', tags='rack_art')
                    if cell:
                        win_id = windows[cell['code']]
                        label_width = int(carton_w * (.98 if cell['stock'] > 0 else .95))
                        # Three lines need extra breathing room at 120% display scaling.
                        label_height = int(max(44, min(68, carton_h * (.74 if cell['stock'] > 0 else .46))))
                        canvas.coords(win_id, x, y - (carton_h * .075 if cell['stock'] > 0 else 0))
                        canvas.itemconfigure(win_id, width=label_width, height=label_height)
            if use_asset:
                rack_photo = ImageTk.PhotoImage(rack_source.resize(
                    (max(1, int(art_w)), max(1, int(art_h))), Image.Resampling.LANCZOS))
                photos.append(rack_photo)
                canvas.create_image(left, top, image=rack_photo, anchor='nw', tags='rack_art')
            if row in rows:
                selected_x = x_centers[rows.index(row)]
                selected_half_width = art_w * (.139 if use_asset else .5 / len(rows))
                canvas.create_rectangle(selected_x - selected_half_width, top + 2,
                                        selected_x + selected_half_width, top + art_h - 2,
                                        outline='#64C5FF', width=3, tags='rack_art')
            canvas.tag_lower('rack_art')
            canvas._rack_detail_photos = photos

        canvas.bind('<Configure>', draw)
        win.update_idletasks()
        draw()

    def _open_rack_cell(self, cell):
        self._hide_rack_tip()
        self.location_detail(cell)

    def _show_rack_tip(self, event, cell):
        self._hide_rack_tip()
        tip = tk.Toplevel(self.rack_window)
        tip.overrideredirect(True)
        tk.Label(tip, text=f"{cell['code']}\n{cell['status']} · {cell['batches']} batch · {cell['stock']} unit",
                 bg='#0A1D2D', fg='#E5F0F9', font=('Segoe UI', 10),
                 justify='left', padx=10, pady=7, relief='solid', borderwidth=1).pack()
        tip.update_idletasks()
        x = min(event.x_root + 10, tip.winfo_screenwidth() - tip.winfo_reqwidth() - 8)
        y = min(event.y_root + 12, tip.winfo_screenheight() - tip.winfo_reqheight() - 8)
        tip.geometry(f'+{max(0, x)}+{max(0, y)}')
        self._rack_tip = tip

    def _hide_rack_tip(self):
        tip = getattr(self, '_rack_tip', None)
        if tip is not None and tip.winfo_exists():
            tip.destroy()
        self._rack_tip = None

    def dialog(self, title, geometry):
        win = tk.Toplevel(self.app.root)
        win.title(title)
        win.geometry(geometry)
        win.configure(bg=BG)
        win.transient(self.app.root)
        win.bind('<Escape>', lambda e: win.destroy())
        return win

    def dialog_text(self, parent, text, size=10, color=MUTED):
        tk.Label(parent, text=text, bg=BG, fg=color, font=('Segoe UI', size), anchor='w', justify='left').pack(fill='x', padx=16, pady=(10, 0))

    def location_detail(self, cell):
        win = self.dialog('Lokasi ' + cell['code'], '920x560')
        self.location_window = win
        self.dialog_text(win, cell['code'] + ' • ' + cell['status'], 16, FG)
        self.dialog_text(win, f"Area {cell['area']} / Rak {cell['rack']} / Kolom {cell['column']:02d} / Baris {cell['row']:02d} / Tingkat {cell['level']:02d}")
        self.dialog_text(win, f"{cell['batches']} batch aktif • {cell['stock']} unit. Stok nol tidak menentukan warna peta.")
        from .inventory_table import InventoryTable
        table = InventoryTable(win, cell['rows'], lambda r: self.open_item(r['id']))
        table.pack(fill='both', expand=True, padx=12, pady=12)
        if cell['rows']:
            self.selected_item = cell['rows'][0]
            self.update_info()
        else:
            self.dialog_text(win, 'Lokasi ini belum memiliki batch.')

    def all_priorities(self):
        win = self.dialog('Prioritas Pemeriksaan', '1020x580')
        self.priority_window = win
        self.dialog_text(win, 'Prioritas Pemeriksaan • ' + self.area.get(), 16, FG)
        self.dialog_text(win, 'Urutan: melewati batas, warning, data perlu diperbaiki. Pilih barang untuk membuka detail.')
        from .inventory_table import InventoryTable
        InventoryTable(win, self.data['priorities'], lambda r: self.open_item(r['id'])).pack(fill='both', expand=True, padx=12, pady=12)

    def open_item(self, key):
        for name in ('location_window', 'rack_window', 'priority_window'):
            win = getattr(self, name, None)
            if win is not None and win.winfo_exists():
                win.destroy()
        self.app.show('Data Barang')
        self.app.search.set(key)
        if key in self.app.table.widgets:
            self.app.table.choose(key)

    def open_report(self, key):
        self.app.show('Laporan')
        self.app.report_page.detail(key)
