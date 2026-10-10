"""Stable camera viewport with native-resolution text and explicit scan confirmation."""
import queue
import sqlite3
import tkinter as tk
from tkinter import ttk
import cv2
from PIL import Image,ImageTk
from .camera import CameraWorker
from .labels import resolve
from .domain import aging
from .sessions import Sessions
from .ui import BG,PANEL,FG,MUTED,BLUE,STATUS_COLORS,STATUS_BACKGROUNDS
from .theme import (
    ACCENT_HOVER, DANGER, DANGER_BG, FIELD_BORDER, SUCCESS,
    SUCCESS_BG, SURFACE_ALT, VIDEO_BG, VIDEO_FG, VIDEO_STATUS_COLORS,
)


class CameraWindow(tk.Toplevel):
    def __init__(self,app,session_id,on_saved):
        self.service=Sessions(app.db)
        self.session=self.service.require_draft(session_id)
        super().__init__(app.root)
        self.app,self.session_id,self.on_saved=app,session_id,on_saved
        self.worker=CameraWorker()
        self.pending=None
        self.candidate=None
        self.frozen=False
        self.running=False
        self._pending_start=None
        self._pending_start_index=None
        self._destroyed=False
        self.title('Pengecekan barang dengan kamera')
        self.configure(bg=BG)
        width=min(1080,app.root.winfo_screenwidth()-60)
        height=min(700,app.root.winfo_screenheight()-100)
        self.geometry(f'{width}x{height}')
        self.resizable(True,True)
        self.minsize(min(900,width),min(540,height))
        self.transient(app.root)
        self.grab_set()
        self.columnconfigure(0,weight=1)
        self.rowconfigure(3,weight=1)
        tk.Label(self,text='Scan QR barang',bg=BG,fg=FG,font=('Segoe UI',19,'bold'),
                 anchor='w').grid(row=0,column=0,sticky='ew',padx=16,pady=(12,2))
        toolbar=tk.Frame(self,bg=BG)
        toolbar.grid(row=1,column=0,sticky='ew',padx=16,pady=(6,8))
        tk.Label(toolbar,text='Pilih kamera',bg=BG,fg=MUTED,font=('Segoe UI',10)).pack(side='left',padx=(0,8))
        self.device=tk.StringVar(value='Kamera 1 — perangkat 0')
        self.devices=ttk.Combobox(toolbar,textvariable=self.device,state='readonly',width=24,
                                  style='Warehouse.TCombobox',values=[f'Kamera {i+1} — perangkat {i}' for i in range(5)])
        self.devices.pack(side='left')
        self.scan_devices=tk.Button(toolbar,text='Deteksi kamera',command=self.discover,bg=PANEL,fg=FG,
                                    activebackground=SURFACE_ALT,activeforeground=FG,relief='flat',padx=12,pady=9,cursor='hand2')
        self.scan_devices.pack(side='left',padx=8)
        self.start_button=tk.Button(toolbar,text='Aktifkan kamera',command=self.start,bg=BLUE,fg=FG,
                                    activebackground=ACCENT_HOVER,activeforeground=FG,relief='flat',padx=12,pady=9,cursor='hand2')
        self.start_button.pack(side='left')
        self.stop_button=tk.Button(toolbar,text='Hentikan kamera',command=self.stop,bg=PANEL,fg=FG,
                                   activebackground=SURFACE_ALT,activeforeground=FG,relief='flat',padx=12,pady=9,
                                   cursor='hand2',state='disabled')
        self.stop_button.pack(side='left',padx=8)
        tk.Label(self,text='1. Deteksi dan pilih kamera.  2. Aktifkan kamera.  3. Arahkan satu QR, periksa hasil, lalu simpan.',
                 bg=BG,fg=MUTED,font=('Segoe UI',10),wraplength=width-40,anchor='w',justify='left').grid(
            row=2,column=0,sticky='w',padx=16,pady=(0,8))
        self.canvas=tk.Canvas(self,bg=VIDEO_BG,highlightthickness=1,highlightbackground=FIELD_BORDER)
        self.canvas.grid(row=3,column=0,sticky='nsew',padx=16)
        self.banner=tk.Label(self,text='Kamera belum aktif. Pilih perangkat lalu klik Aktifkan kamera.',
                             bg=PANEL,fg=FG,anchor='w',justify='left',font=('Segoe UI',11,'bold'),
                             wraplength=width-60,padx=14,pady=10)
        self.banner.grid(row=4,column=0,sticky='ew',padx=16,pady=8)
        actions=tk.Frame(self,bg=BG)
        actions.grid(row=5,column=0,sticky='ew',padx=16,pady=(0,12))
        self.confirm_button=tk.Button(actions,text='Simpan hasil scan',state='disabled',command=self.confirm,bg=BLUE,fg=FG,
                                      activebackground=ACCENT_HOVER,activeforeground=FG,relief='flat',
                                      font=('Segoe UI',11,'bold'),padx=16,pady=10,cursor='hand2')
        self.confirm_button.pack(side='left')
        self.next_button=tk.Button(actions,text='Scan barang berikutnya',command=self.next_scan,bg=PANEL,fg=FG,
                                   activebackground=SURFACE_ALT,activeforeground=FG,relief='flat',padx=16,pady=10,
                                   cursor='hand2',state='disabled')
        self.next_button.pack(side='left',padx=8)
        self.map_button=tk.Button(actions,text='Lihat lokasi barang',command=lambda:app.show('Dashboard'),state='disabled',
                                  bg=PANEL,fg=FG,activebackground=SURFACE_ALT,activeforeground=FG,
                                  relief='flat',padx=12,pady=10,cursor='hand2')
        self.map_button.pack(side='left',padx=4)
        tk.Button(actions,text='Tutup',command=self.destroy,bg=PANEL,fg=FG,
                  activebackground=SURFACE_ALT,activeforeground=FG,relief='flat',padx=16,pady=10,cursor='hand2').pack(side='right')
        self.protocol('WM_DELETE_WINDOW',self.destroy)
        self.bind('<Escape>',lambda e:self.destroy())
        self.bind('<Configure>',lambda e:self.banner.configure(wraplength=max(400,e.width-60)) if e.widget is self else None)
        self.pending=self.after(80,self.poll)

    def controls(self,busy):
        self.running=busy
        for widget in (self.start_button,self.scan_devices):widget.configure(state='disabled' if busy else 'normal')
        self.devices.configure(state='disabled' if busy else 'readonly')
        self.stop_button.configure(state='normal' if busy else 'disabled')
        self.next_button.configure(state='normal' if busy else 'disabled')

    def start(self):
        if self.running or self._pending_start is not None:return
        try:
            self.service.require_draft(self.session_id)
            index=int(self.device.get().rsplit(' ',1)[-1])
            if self._live_releasing():
                self._pending_start_index=index
                self.controls(True)
                self.next_scan()
                self.banner.configure(text='Menunggu kamera Live selesai melepas perangkat…',bg=PANEL,fg=FG)
                self._pending_start=self.after(120,self._retry_start)
                return
            self._start_worker(index)
        except (ValueError,sqlite3.Error) as exc:self.banner.configure(text=str(exc))

    def _live_releasing(self):
        monitor=getattr(self.app,'live_monitor',None)
        return bool(monitor is not None and monitor.is_running)

    def _start_worker(self,index):
        self.worker.start(index)
        self.controls(True)
        self.next_scan()
        self.banner.configure(text='Membuka kamera…',bg=PANEL,fg=FG)

    def _retry_start(self):
        self._pending_start=None
        if self._destroyed:return
        if self._live_releasing():
            self._pending_start=self.after(120,self._retry_start)
            return
        index=self._pending_start_index
        self._pending_start_index=None
        try:self._start_worker(index)
        except (ValueError,sqlite3.Error) as exc:
            self.controls(False)
            self.banner.configure(text=str(exc),bg=DANGER_BG,fg=DANGER)

    def discover(self):
        if self.running or self._pending_start is not None:return
        if self._live_releasing():
            self.banner.configure(text='Menunggu kamera Live dilepas untuk mencari perangkat…',bg=PANEL,fg=FG)
            self._pending_start=self.after(120,self._retry_discover)
            return
        self._start_discovery()

    def _retry_discover(self):
        self._pending_start=None
        if self._destroyed:return
        if self._live_releasing():
            self._pending_start=self.after(120,self._retry_discover)
            return
        self._start_discovery()

    def _start_discovery(self):
        try:
            self.worker.start(discover=True)
            self.controls(True)
            self.next_scan()
        except ValueError as exc:self.banner.configure(text=str(exc))

    def stop(self):
        if self._pending_start is not None:
            self.after_cancel(self._pending_start)
            self._pending_start=None
            self._pending_start_index=None
            self.controls(False)
        else:self.worker.stop()
        self.candidate=None
        self.frozen=False
        self.confirm_button.configure(state='disabled')
        self.next_button.configure(text='Scan barang berikutnya',state='disabled')
        self.banner.configure(text='Kamera dihentikan. Hasil yang tersimpan tetap ada di sesi.',bg=PANEL,fg=FG)

    def next_scan(self):
        self.candidate=None
        self.frozen=False
        self.confirm_button.configure(state='disabled')
        self.next_button.configure(text='Scan barang berikutnya')
        self.canvas.delete('overlay')
        self.banner.configure(text='Arahkan satu QR ke kamera. Detail akan tampil sebelum disimpan.',bg=PANEL,fg=FG)

    def process_frame(self,frame,found):
        if self.frozen:return
        width=max(1,self.canvas.winfo_width())
        height=max(1,self.canvas.winfo_height())
        h,w=frame.shape[:2]
        ratio=min(width/w,height/h,1.0)
        size=(max(1,round(w*ratio)),max(1,round(h*ratio)))
        photo=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
        if size!=(w,h):photo=photo.resize(size,Image.Resampling.LANCZOS)
        self.photo=ImageTk.PhotoImage(photo)
        self.canvas.delete('all')
        x,y=(width-size[0])/2,(height-size[1])/2
        self.canvas.create_image(width/2,height/2,image=self.photo)
        if not found:return
        codes={c for c,_ in found}
        if len(codes)>1:
            self.banner.configure(text='Lebih dari satu QR terlihat. Dekatkan kamera ke satu label.',bg=PANEL,fg=FG)
            return
        code,points=found[0]
        self.frozen=True
        self.candidate_frame=frame.copy()
        try:
            session=self.service.require_draft(self.session_id)
            old=next((r for r in self.service.results(self.session_id) if 'ID:'+r['id']==code),None)
            item=old or resolve(self.app.db,code)
            if not old:item['age'],item['status']=aging(item['received_date'],normal_max=session['normal_max'],age_limit=session['age_limit'])
            self.candidate=code
            self.next_button.configure(text='Lewati hasil ini',state='normal')
            color=VIDEO_STATUS_COLORS[item['status']]
            coords=[coordinate for px,py in points for coordinate in (x+px*ratio,y+py*ratio)]
            self.canvas.create_polygon(*coords,outline=color,fill='',width=3,tags='overlay')
            card_width=min(355,width-32)
            left=width-card_width-12
            text=f"{item['status'].upper()}  •  {item['age']} hari\nMaterial: {item['material']}\n{item['description']}\nLokasi: {item['location_code']}\nTanggal masuk (GR): {item['received_date']}\nStok: {item['stock']}"
            card=self.canvas.create_text(left+14,24,text=text,anchor='nw',width=card_width-28,fill=VIDEO_FG,font=('Segoe UI',11,'bold'),tags='overlay')
            bounds=self.canvas.bbox(card)
            rect=self.canvas.create_rectangle(left,12,width-12,bounds[3]+12,fill=VIDEO_BG,outline=color,width=3,tags='overlay')
            self.canvas.tag_lower(rect,card)
            prefix='Sudah ada di sesi; hasil pertama dipertahankan.' if old else 'QR terbaca — belum disimpan. Klik Simpan hasil scan untuk memasukkannya ke sesi.'
            self.banner.configure(text=f"{item['status']} • {item['age']} hari. {prefix}",bg=STATUS_BACKGROUNDS[item['status']],fg=STATUS_COLORS[item['status']])
            self.confirm_button.configure(state='normal')
        except (ValueError,sqlite3.Error) as exc:
            self.candidate=None
            self.banner.configure(text='QR belum dapat diproses: '+str(exc),bg=DANGER_BG,fg=DANGER)

    def confirm(self):
        if self.candidate is None:return
        try:
            key,added=self.service.add_code(self.session_id,self.candidate)
            self.app.last_camera_frame=self.candidate_frame.copy()
            self.confirm_button.configure(state='disabled')
            self.candidate=None
            self.next_button.configure(text='Scan barang berikutnya',state='normal')
            self.banner.configure(text='Hasil tersimpan. Klik Scan berikutnya untuk barang lain.' if added else 'Batch sudah tercatat; tidak ada baris tambahan. Klik Scan berikutnya.',bg=SUCCESS_BG,fg=SUCCESS)
            self.on_saved(key)
            self.map_button.configure(state='normal')
        except (ValueError,sqlite3.Error) as exc:self.banner.configure(text='Belum tersimpan: '+str(exc),bg=DANGER_BG,fg=DANGER)

    def poll(self):
        self.pending=None
        try:
            while True:
                kind,value=self.worker.messages.get_nowait()
                if kind=='stopped':self.controls(False)
                elif kind=='devices':
                    choices=[f'Kamera {i+1} — perangkat {i}' for i in value]
                    self.devices.configure(values=choices or [f'Kamera {i+1} — perangkat {i}' for i in range(5)])
                    if choices:self.device.set(choices[0])
                    self.banner.configure(text=f'{len(choices)} kamera ditemukan. Pilih lalu klik Aktifkan kamera.' if choices else 'Tidak ada kamera terbaca. Periksa sambungan dan izin kamera desktop Windows.')
                elif kind=='error':
                    self.candidate=None
                    self.confirm_button.configure(state='disabled')
                    self.banner.configure(text=value,bg=DANGER_BG,fg=DANGER)
                else:self.banner.configure(text=value)
        except queue.Empty:pass
        try:
            frame,found=self.worker.frames.get_nowait()
            if not self.worker.stop_event.is_set():self.process_frame(frame,found)
        except queue.Empty:pass
        self.pending=self.after(80,self.poll)

    def destroy(self):
        if self._destroyed:return
        self._destroyed=True
        if self._pending_start is not None:
            self.after_cancel(self._pending_start)
            self._pending_start=None
        self.worker.stop()
        if self.pending is not None:self.after_cancel(self.pending)
        try:super().destroy()
        finally:self.app.resume_live_after_scan(self.worker)
