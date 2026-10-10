"""The read-only Live monitoring page and its current-inventory projection."""

from datetime import date
import tkinter as tk
from tkinter import ttk

import cv2
from PIL import Image, ImageTk

from .domain import aging
from .labels import resolve
from .recommendations import RecommendationService, recommend_for
from .recommendation_data import recommendation_context
from .ui import BG, PANEL, FG, MUTED, BLUE, EDGE, STATUS_COLORS, STATUS_BACKGROUNDS, display_time
from .theme import (
    ACCENT_HOVER, FIELD_BORDER, FOCUS, NEUTRAL_BG, SURFACE_ALT,
    VIDEO_BG, VIDEO_FG, VIDEO_MUTED, VIDEO_STATUS_COLORS,
)


INK = dict(STATUS_COLORS, **{'Stok habis': MUTED, 'QR tidak dikenal': MUTED})
TINT = dict(STATUS_BACKGROUNDS, **{'Stok habis': NEUTRAL_BG, 'QR tidak dikenal': NEUTRAL_BG})
PRIORITY = {'Melewati batas': 0, 'Warning': 1, 'Normal': 2,
            'Stok habis': 3, 'Data perlu diperbaiki': 3, 'QR tidak dikenal': 4}


def recommendation_signature(advice):
    """Refresh a visible QR card when its simulated destination changes."""
    advice = advice or {}
    options = tuple((option.get('kind'), option.get('target'), option.get('title'),
                     option.get('reason'), option.get('next_action'),
                     option.get('suggested_units')) for option in advice.get('options', ()))
    return (advice.get('code'), advice.get('title'), advice.get('reason'),
            advice.get('next_action'), advice.get('source'), options)


def current_item(db, code, today=None):
    """Read a QR against current inventory; never create an inspection result."""
    try:
        item = resolve(db, code)
    except ValueError:
        return dict(code=code, material='QR tidak dikenal', description='Tidak ada di Data Barang',
                    location_code='—', age='—', stock='—', status='QR tidak dikenal',
                    recommendation=None, latest_action=None)
    try:
        age, status = aging(item['received_date'], today=today or date.today())
    except ValueError:
        age, status = '—', 'Data perlu diperbaiki'
    if item['stock'] <= 0:
        status = 'Stok habis'
    context = recommendation_context(db, item['material']) if item['stock'] > 0 else None
    if context and not context['sites'] and not context['customers']:
        context = None
    recommendation = (recommend_for(item, today=today or date.today(), context=context)
                      if item['stock'] > 0 else None)
    latest_action = RecommendationService(db).latest_action_for_batch(item['id'])
    return dict(code=code, material=item['material'], description=item['description'],
                location_code=item['location_code'], age=age, stock=item['stock'], status=status,
                recommendation=recommendation, latest_action=latest_action)


class LivePage:
    def __init__(self, app):
        self.app = app
        self.frame = tk.Frame(app.body, bg=BG)
        self.frame.pack(fill='both', expand=True)
        self.frame.columnconfigure(0, weight=7, minsize=420, uniform='live-panes')
        self.frame.columnconfigure(1, weight=4, minsize=315, uniform='live-panes')
        self.frame.rowconfigure(1, weight=1)
        self._frame = None
        self._detections = ()
        self._items = {}
        self._list_signature = None
        self._codes = ()
        self._rows = {}
        self._photo = None
        self._build_heading()
        self._build_camera()
        self._build_list()
        self.update(app.live_snapshot, app.live_details, app.live_error)

    def _label(self, parent, text, size=10, color=MUTED, bold=False, bg=PANEL, **kwargs):
        options = dict(text=text, bg=bg, fg=color,
                       font=('Segoe UI', size, 'bold' if bold else 'normal'), anchor='w')
        options.update(kwargs)
        return tk.Label(parent, **options)

    def _button(self, parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command,
                         bg=BLUE if primary else PANEL, fg=FG,
                         activebackground=ACCENT_HOVER if primary else SURFACE_ALT,
                         activeforeground=FG, font=('Segoe UI', 10, 'bold'),
                         relief='flat', borderwidth=0, padx=12, pady=9, cursor='hand2',
                         highlightthickness=1, highlightbackground=FIELD_BORDER,
                         highlightcolor=FOCUS)

    def _panel(self, parent):
        return tk.Frame(parent, bg=PANEL, highlightbackground=EDGE, highlightthickness=1)

    def _build_heading(self):
        head = tk.Frame(self.frame, bg=BG)
        head.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 10))
        self._label(head, 'Pemantauan Live', 20, FG, True, BG).pack(anchor='w')
        self._label(head, 'Lihat status barang yang QR-nya sedang terbaca kamera. Tidak masuk laporan pengecekan.',
                    10, MUTED, bg=BG).pack(anchor='w', pady=(1, 0))

    def _build_camera(self):
        pane = self._panel(self.frame)
        pane.grid(row=1, column=0, sticky='nsew', padx=(0, 10))
        pane.rowconfigure(1, weight=1)
        pane.columnconfigure(0, weight=1)
        top = tk.Frame(pane, bg=PANEL, padx=14, pady=11)
        top.grid(row=0, column=0, sticky='ew')
        self._label(top, 'Kamera langsung', 13, FG, True).pack(side='left')
        self.visible_count = self._label(top, '0 QR terlihat', 10, MUTED)
        self.visible_count.pack(side='right')
        self.video = tk.Canvas(pane, bg=VIDEO_BG, highlightthickness=0)
        self.video.grid(row=1, column=0, sticky='nsew', padx=12)
        self.video.bind('<Configure>', lambda _event: self._draw_video())
        self._draw_placeholder()
        controls = tk.Frame(pane, bg=PANEL, padx=12, pady=11)
        controls.grid(row=2, column=0, sticky='ew')
        controls.columnconfigure(0, weight=1)
        top_controls = tk.Frame(controls, bg=PANEL)
        top_controls.grid(row=0, column=0, sticky='ew')
        self._label(top_controls, 'Sumber kamera', 9, MUTED).pack(side='left', padx=(0, 8))
        self.device = ttk.Combobox(top_controls, state='readonly', width=25,
                                   values=[f'Kamera {n+1} (perangkat {n})' for n in range(5)],
                                   style='Warehouse.TCombobox')
        self.device.current(max(0, min(4, app_device(self.app))))
        self.device.pack(side='left')
        self.status = self._label(controls, 'Kamera belum aktif. Biasanya kamera laptop adalah Kamera 1.',
                                  10, MUTED, bg=PANEL, wraplength=650)
        self.status.grid(row=1, column=0, sticky='ew', pady=(9, 8))
        actions = tk.Frame(controls, bg=PANEL)
        actions.grid(row=2, column=0, sticky='ew')
        self.start_button = self._button(actions, 'Aktifkan kamera',
                                         lambda: self.app.start_live(self.device.current()), True)
        self.start_button.pack(side='left')
        self.stop_button = self._button(actions, 'Matikan kamera', self.app.stop_live)
        self.stop_button.pack(side='left', padx=(8, 0))

    def _build_list(self):
        pane = self._panel(self.frame)
        pane.grid(row=1, column=1, sticky='nsew')
        pane.rowconfigure(2, weight=1)
        pane.columnconfigure(0, weight=1)
        head = tk.Frame(pane, bg=PANEL, padx=12, pady=11)
        head.grid(row=0, column=0, sticky='ew')
        self._label(head, 'Barang terdeteksi saat ini', 13, FG, True).pack(anchor='w')
        self._label(head, 'Daftar mengikuti kamera; gulir untuk melihat semuanya.', 9).pack(anchor='w', pady=(3, 0))
        counters = tk.Frame(pane, bg=PANEL, padx=12, pady=5)
        counters.grid(row=1, column=0, sticky='ew')
        for col, (key, caption) in enumerate((('Melewati batas', 'Lewat batas'),
                                               ('Warning', 'Warning'), ('Normal', 'Normal'))):
            counters.columnconfigure(col, weight=1, uniform='live-count')
            tile = tk.Frame(counters, bg=TINT[key], highlightbackground=INK[key], highlightthickness=1)
            tile.grid(row=0, column=col, sticky='ew', padx=(0 if col == 0 else 3, 0 if col == 2 else 3))
            number = self._label(tile, '0', 17, INK[key], True, TINT[key], anchor='center')
            number.pack(fill='x', pady=(4, 0))
            self._label(tile, caption, 8, INK[key], bg=TINT[key], anchor='center').pack(fill='x', pady=(0, 5))
            if not hasattr(self, 'counter_labels'):
                self.counter_labels = {}
            self.counter_labels[key] = number
        list_host = tk.Frame(pane, bg=PANEL)
        list_host.grid(row=2, column=0, sticky='nsew', padx=(12, 8), pady=(10, 6))
        list_host.rowconfigure(0, weight=1)
        list_host.columnconfigure(0, weight=1)
        self.list_canvas = tk.Canvas(list_host, bg=PANEL, highlightthickness=0)
        self.list_canvas.grid(row=0, column=0, sticky='nsew')
        self.list_bar = ttk.Scrollbar(list_host, orient='vertical', command=self.list_canvas.yview)
        self.list_bar.grid(row=0, column=1, sticky='ns', padx=(5, 0))
        self.list_canvas.configure(yscrollcommand=self.list_bar.set)
        self.list_body = tk.Frame(self.list_canvas, bg=PANEL)
        self.list_window = self.list_canvas.create_window((0, 0), window=self.list_body, anchor='nw')
        self.list_canvas.bind('<Configure>', self._resize_list)
        self.list_body.bind('<Configure>', lambda _event: self.list_canvas.configure(
            scrollregion=self.list_canvas.bbox('all')))
        self._bind_wheel(self.list_canvas)
        self._bind_wheel(self.list_body)
        self.empty = self._label(self.list_body,
                                  'Belum ada QR terbaca. Arahkan label ke kamera untuk melihat statusnya.',
                                  10, MUTED, bg=PANEL, justify='left', wraplength=280)
        self.empty.pack(fill='x', padx=8, pady=16)
        self._label(pane, 'Daftar stabil: QR yang sesaat tidak terbaca tetap tampil ±2 detik.',
                    9, MUTED, bg=PANEL, wraplength=360).grid(row=3, column=0, sticky='ew', padx=12, pady=(0, 10))

    def _resize_list(self, event):
        self.list_canvas.itemconfigure(self.list_window, width=max(1, event.width))

    def _bind_wheel(self, widget):
        widget.bind('<MouseWheel>', lambda event: (self.list_canvas.yview_scroll(
            -1 if event.delta > 0 else 1, 'units'), 'break')[1])

    def _draw_placeholder(self):
        self.video.delete('all')
        width = max(280, self.video.winfo_width())
        height = max(200, self.video.winfo_height())
        x, y = width / 2, height / 2
        for dx, dy, sx, sy in ((-65, -47, 1, 1), (65, -47, -1, 1),
                               (-65, 47, 1, -1), (65, 47, -1, -1)):
            self.video.create_line(x+dx, y+dy, x+dx+sx*20, y+dy,
                                   fill=VIDEO_MUTED, width=3)
            self.video.create_line(x+dx, y+dy, x+dx, y+dy+sy*20,
                                   fill=VIDEO_MUTED, width=3)
        self.video.create_text(x, y, text='Kamera belum aktif', fill=VIDEO_FG,
                               font=('Segoe UI', 12, 'bold'))

    def _draw_video(self):
        frame = self._frame
        if frame is None:
            self._draw_placeholder()
            return
        width, height = max(1, self.video.winfo_width()), max(1, self.video.winfo_height())
        source_h, source_w = frame.shape[:2]
        scale = min(width/source_w, height/source_h, 1.0)
        target = (max(1, round(source_w*scale)), max(1, round(source_h*scale)))
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)
        if target != (source_w, source_h):
            image = image.resize(target, Image.Resampling.BILINEAR)
        self._photo = ImageTk.PhotoImage(image, master=self.app.root)
        self.video.delete('all')
        offset_x, offset_y = (width-target[0])/2, (height-target[1])/2
        self.video.create_image(width/2, height/2, image=self._photo)
        for number, detection in enumerate(self._detections, start=1):
            if not detection.visible:
                continue
            item = self._items.get(detection.code, {})
            color = VIDEO_STATUS_COLORS.get(item.get('status'), VIDEO_MUTED)
            coords = [coordinate for px, py in detection.points
                      for coordinate in (offset_x+px*scale, offset_y+py*scale)]
            if len(coords) != 8:
                continue
            self.video.create_polygon(*coords, fill='', outline=color, width=3)
            bx, by = coords[0], coords[1]
            self.video.create_oval(bx-15, by-24, bx+15, by+6, fill=color,
                                   outline=VIDEO_BG, width=2)
            self.video.create_text(bx, by-9, text=f'{number:02d}',
                                   fill=VIDEO_BG, font=('Segoe UI', 9, 'bold'))

    def _row(self, code):
        shell = tk.Frame(self.list_body, bg=SURFACE_ALT, highlightbackground=EDGE,
                         highlightthickness=1)
        shell.pack(fill='x', padx=(1, 4), pady=(0, 8))
        stripe = tk.Frame(shell, bg=FIELD_BORDER, width=4)
        stripe.pack(side='left', fill='y')
        stripe.pack_propagate(False)
        content = tk.Frame(shell, bg=SURFACE_ALT, padx=10, pady=8)
        content.pack(fill='both', expand=True)
        line = tk.Frame(content, bg=SURFACE_ALT)
        line.pack(fill='x')
        badge = self._label(line, '01', 9, FG, True, NEUTRAL_BG, anchor='center', width=3)
        badge.pack(side='left', padx=(0, 9))
        material = self._label(line, '', 11, FG, True, SURFACE_ALT)
        material.pack(side='left', fill='x', expand=True)
        age = self._label(line, '', 9, MUTED, True, SURFACE_ALT)
        age.pack(side='right')
        location = self._label(content, '', 9, MUTED, bg=SURFACE_ALT)
        location.pack(fill='x', pady=(5, 4))
        status = self._label(content, '', 9, MUTED, True, SURFACE_ALT)
        status.pack(fill='x')
        advice = self._label(content, '', 9, FG, bg=SURFACE_ALT,
                             justify='left', wraplength=300)
        advice.pack(fill='x', pady=(5, 0))
        decision = self._label(content, '', 9, MUTED, bg=SURFACE_ALT,
                               justify='left', wraplength=300)
        decision.pack(fill='x', pady=(4, 0))
        widgets = (shell, stripe, content, line, badge, material, age, location, status,
                   advice, decision)
        for widget in widgets:
            self._bind_wheel(widget)
        self._rows[code] = dict(shell=shell, stripe=stripe, badge=badge,
                                material=material, age=age, location=location, status=status,
                                advice=advice, decision=decision)

    def _update_list(self, detections, items):
        by_code = {d.code: d for d in detections}
        surviving = tuple(code for code in self._codes if code in by_code)
        arriving = sorted((d for d in detections if d.code not in surviving),
                          key=lambda d: (PRIORITY.get(items.get(d.code, {}).get('status'), 5),
                                         d.first_seen, d.code))
        codes = surviving + tuple(d.code for d in arriving)
        ordered = tuple(by_code[code] for code in codes)
        if codes != self._codes:
            position = self.list_canvas.yview()[0]
            for code in tuple(self._rows):
                if code not in codes:
                    self._rows.pop(code)['shell'].destroy()
            for code in codes:
                if code not in self._rows:
                    self._row(code)
            for code in codes:
                self._rows[code]['shell'].pack_forget()
                self._rows[code]['shell'].pack(fill='x', padx=(1, 4), pady=(0, 8))
            self.list_canvas.update_idletasks()
            self.list_canvas.yview_moveto(position)
            self._codes = codes
        if self.empty.winfo_manager():
            self.empty.pack_forget()
        if not codes:
            self.empty.pack(fill='x', padx=8, pady=16)
        for number, code in enumerate(codes, start=1):
            item = items.get(code, {})
            row = self._rows[code]
            status = item.get('status', 'QR tidak dikenal')
            color = INK.get(status, MUTED)
            row['stripe'].configure(bg=color)
            row['badge'].configure(text=f'{number:02d}', bg=TINT.get(status, PANEL), fg=color)
            row['material'].configure(text=item.get('material', 'QR tidak dikenal'))
            age = item.get('age', '—')
            row['age'].configure(text=f'{age} hari' if isinstance(age, int) else '—')
            row['location'].configure(text=item.get('location_code', '—'))
            row['status'].configure(text=status, fg=color)
            recommendation = item.get('recommendation')
            action = item.get('latest_action')
            if status == 'Stok habis':
                advice_text = 'Saran tidak aktif: stok habis.'
            elif recommendation:
                source = ' · Simulasi' if recommendation.get('source') == 'Simulasi' else ''
                options = recommendation.get('options') or ()
                if options:
                    choices = '\n'.join(f"{number}. {option['title']}"
                                        for number, option in enumerate(options, start=1))
                    advice_text = (f"Saran{source}: {recommendation['title']}\n"
                                   f"{choices}\n{recommendation['next_action']}")
                else:
                    advice_text = f"Saran{source}: {recommendation['title']}. {recommendation['next_action']}"
            else:
                advice_text = 'Tidak ada saran untuk QR ini.'
            row['advice'].configure(text=advice_text)
            if action:
                target=(f" · {'Customer' if action['target_kind']=='customer' else 'Site'} "
                        f"{action['target_code']}" if action.get('target_kind') and
                        action.get('target_code') else '')
                decision_text = (f"Keputusan terakhir: {action['choice']} · {action['action_status']}\n"
                                 f"{action['officer']} · {display_time(action['decided_at'])}{target}")
            else:
                decision_text = 'Keputusan petugas: belum ada.' if recommendation else ''
            row['decision'].configure(text=decision_text)
        self._detections = ordered

    def update(self, snapshot, items, error=''):
        if not self.frame.winfo_exists():
            return
        old_detections = self._detections
        signature = tuple(sorted((code, item.get('material'), item.get('location_code'),
                                  item.get('age'), item.get('stock'), item.get('status'),
                                  recommendation_signature(item.get('recommendation')),
                                  (item.get('latest_action') or {}).get('id'),
                                  (item.get('latest_action') or {}).get('choice'),
                                  (item.get('latest_action') or {}).get('target_kind'),
                                  (item.get('latest_action') or {}).get('target_code'),
                                  (item.get('latest_action') or {}).get('reason'),
                                  (item.get('latest_action') or {}).get('decided_at'),
                                  (item.get('latest_action') or {}).get('action_status'))
                                 for code, item in items.items()))
        list_changed = signature != self._list_signature
        self._items = items
        if list_changed:
            self._update_list(snapshot.detections, items)
            self._list_signature = signature
            self.visible_count.configure(text=f'{len(snapshot.detections)} QR terdeteksi')
            for status, label in self.counter_labels.items():
                label.configure(text=str(sum(items.get(d.code, {}).get('status') == status
                                             for d in snapshot.detections)))
        else:
            by_code = {d.code: d for d in snapshot.detections}
            self._detections = tuple(by_code[code] for code in self._codes if code in by_code)
        running = self.app.live_monitor.is_running
        stopping = getattr(self.app, 'live_stopping', False)
        paused = getattr(self.app, 'live_paused_for_scan', False)
        self.start_button.configure(state='disabled' if running else 'normal')
        self.stop_button.configure(state='normal' if running and not stopping else 'disabled')
        self.device.configure(state='disabled' if running else 'readonly')
        if error:
            self.status.configure(text=error, fg=INK['Melewati batas'])
        elif paused:
            self.status.configure(text='Live jeda sementara: kamera sedang dipakai untuk Pengecekan.',
                                  fg=INK['Warning'])
        elif stopping:
            self.status.configure(text='Sedang melepas kamera…', fg=MUTED)
        elif running and snapshot.frame is None:
            self.status.configure(text='Membuka kamera…', fg=MUTED)
        elif running:
            self.status.configure(text='Kamera aktif. Status mengikuti data barang hari ini; hasil Live tidak disimpan.',
                                  fg=INK['Normal'])
        else:
            self.status.configure(text='Kamera belum aktif. Biasanya kamera laptop adalah Kamera 1.', fg=MUTED)
        if snapshot.frame is not self._frame:
            self._frame = snapshot.frame
            self._draw_video()
        elif old_detections != self._detections or list_changed:
            self._draw_video()


def app_device(app):
    return getattr(app, 'live_device_index', 0)
