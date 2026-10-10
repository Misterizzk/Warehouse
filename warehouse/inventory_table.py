"""Scrollable inventory rows with real per-cell status labels."""
import tkinter as tk
from tkinter import ttk
from .ui import display_time

from .theme import (
    PANEL as BG, FG, MUTED, ROW_ALT, ROW_SELECTED, HEADER, ON_DARK,
    EDGE, FOCUS, SUCCESS, WARNING, STATUS_COLORS, STATUS_BACKGROUNDS,
)

COLORS = {name: (STATUS_BACKGROUNDS[name], STATUS_COLORS[name]) for name in
          ('Normal', 'Warning', 'Melewati batas', 'Data perlu diperbaiki', 'Stok habis')}


def recommendation_caption(row):
    """Keep advice visible in the compact status cell until staff decides."""
    if row['stock'] == 0:
        return 'Tindak lanjut tidak aktif'
    action = row.get('latest_action')
    if action and action['action_status'] == 'Selesai':
        return 'Tindakan selesai'
    if action:
        return action['choice']
    advice = row.get('recommendation') or {}
    options = advice.get('options') or ()
    if options:
        return options[0].get('title') or advice.get('title', 'Belum ada saran')
    return advice.get('title', 'Belum ada saran')


class InventoryTable(tk.Frame):
    def __init__(self,parent,rows,on_select,inspection=False):
        super().__init__(parent,bg=BG)
        self.rows=rows
        self.on_select=on_select
        self.selected=None
        self.widgets={}
        self.row_backgrounds={}
        self.canvas=tk.Canvas(self,bg=BG,highlightthickness=1,highlightbackground=EDGE,highlightcolor=FOCUS,takefocus=True)
        sy=ttk.Scrollbar(self,orient='vertical',command=self.canvas.yview)
        self.header_canvas=tk.Canvas(self,bg=HEADER,height=45,highlightthickness=0)
        self.header_canvas.grid(row=0,column=0,sticky='ew')
        def horizontal(*args):
            self.canvas.xview(*args)
            self.header_canvas.xview(*args)
        sx=ttk.Scrollbar(self,orient='horizontal',command=horizontal)
        def sync_vertical(first,last):
            sy.set(first,last)
            if float(last)-float(first)>=0.999:sy.grid_remove()
            else:sy.grid(row=1,column=1,sticky='ns')
        def sync_header(first,last):
            sx.set(first,last)
            self.header_canvas.xview_moveto(first)
            if float(last)-float(first)>=0.999:sx.grid_remove()
            else:sx.grid(row=2,column=0,sticky='ew')
        self.canvas.configure(yscrollcommand=sync_vertical,xscrollcommand=sync_header)
        self.canvas.grid(row=1,column=0,sticky='nsew')
        sy.grid(row=1,column=1,sticky='ns')
        sx.grid(row=2,column=0,sticky='ew')
        self.columnconfigure(0,weight=1)
        self.rowconfigure(1,weight=1)
        self.content=tk.Frame(self.canvas,bg=BG)
        self.window=self.canvas.create_window(0,0,window=self.content,anchor='nw')
        widths=(295,155,80,100,180)
        advice_visible = not inspection and any('recommendation' in row for row in rows)
        headings=('Barang dan ID batch','Lokasi fisik','Stok','Umur saat ini',
                  'Status / saran' if advice_visible else 'Status umur')
        if inspection:
            widths += (220,280)
            headings += ('Waktu cek','Catatan')
        header=tk.Frame(self.header_canvas,bg=HEADER)
        header_window=self.header_canvas.create_window(0,0,window=header,anchor='nw')
        self.configure_columns(header,widths)
        for i,title in enumerate(headings):
            tk.Label(header,text=title,bg=HEADER,fg=ON_DARK,font=('Segoe UI',10,'bold'),anchor='w',padx=14,pady=12).grid(row=0,column=i,sticky='ew')
        for index,r in enumerate(rows):
            row_bg=BG if index%2==0 else ROW_ALT
            row=tk.Frame(self.content,bg=row_bg,height=82)
            row.pack(fill='x')
            self.configure_columns(row,widths)
            name=tk.Frame(row,bg=row_bg)
            name.grid(row=0,column=0,sticky='ew',padx=14,pady=8)
            tk.Label(name,text=r['material'],bg=row_bg,fg=FG,font=('Segoe UI',10,'bold'),anchor='w').pack(fill='x')
            description=r['description']
            if len(description)>39:description=description[:36]+'…'
            tk.Label(name,text=description,bg=row_bg,fg=MUTED,font=('Segoe UI',9),anchor='w').pack(fill='x',pady=(2,0))
            tk.Label(name,text='Batch '+r['id'],bg=row_bg,fg=MUTED,font=('Segoe UI',9),anchor='w').pack(fill='x',pady=(2,0))
            for i,value in enumerate((r['location_code'],str(r['stock']),f"{r['age']} hari"),1):
                tk.Label(row,text=value,bg=row_bg,fg=FG,font=('Segoe UI',10),anchor='w',padx=14).grid(row=0,column=i,sticky='ew')
            shown_status='Stok habis' if not inspection and r['stock']==0 else r['status']
            color,ink=COLORS[shown_status]
            status_cell=tk.Frame(row,bg=row_bg)
            status_cell.grid(row=0,column=4,sticky='w',padx=14,pady=7)
            badge=tk.Label(status_cell,text=shown_status,bg=color,fg=ink,
                           font=('Segoe UI',10,'bold'),padx=10,pady=5)
            badge.pack(anchor='w')
            if not inspection and 'recommendation' in r:
                action=r.get('latest_action')
                caption=recommendation_caption(r)
                if r['stock']==0:
                    caption_color=MUTED
                elif action and action['action_status']=='Selesai':
                    caption_color=SUCCESS
                elif action:
                    caption_color=WARNING
                else:
                    caption_color=ink
                tk.Label(status_cell,text=caption,bg=row_bg,fg=caption_color,
                         font=('Segoe UI',9),anchor='w',justify='left',
                         wraplength=widths[4]-28).pack(anchor='w',pady=(5,0))
            if inspection:
                for col,value in ((5,display_time(r['checked_at'])),(6,r['note'] or '—')):
                    shown=value if len(value)<=100 else value[:97]+'…'
                    tk.Label(row,text=shown,bg=row_bg,fg=MUTED,font=('Segoe UI',10),anchor='w',justify='left',wraplength=widths[col]-28).grid(row=0,column=col,sticky='ew',padx=14)
            tk.Frame(self.content,bg=EDGE,height=1).pack(fill='x')
            self.widgets[r['id']]=(row,badge)
            self.row_backgrounds[r['id']]=row_bg
            self.bind_children(row,r['id'])
        if not rows:
            tk.Label(self.content,text='Tidak ada barang yang sesuai. Ubah pencarian atau filter di atas.',
                     bg=BG,fg=MUTED,font=('Segoe UI',11),anchor='center',pady=36).pack(fill='x')
        self.content.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        def resize(event):
            width=max(sum(widths),event.width-2)
            self.canvas.itemconfigure(self.window,width=width)
            self.header_canvas.itemconfigure(header_window,width=width)
            self.header_canvas.configure(scrollregion=(0,0,width,45))
        self.canvas.bind('<Configure>',resize)
        self.canvas.bind('<MouseWheel>',self.wheel)
        for key,step in (('<Down>',1),('<Up>',-1)):
            self.canvas.bind(key,lambda e,d=step:self.move(d))
        self.canvas.bind('<Home>',lambda e:self.choose(self.rows[0]['id']) if self.rows else None)
        self.canvas.bind('<End>',lambda e:self.choose(self.rows[-1]['id']) if self.rows else None)

    def configure_columns(self,frame,widths):
        for i,w in enumerate(widths):frame.columnconfigure(i,minsize=w,weight=1 if i==0 else 0)

    def wheel(self,event):
        self.canvas.yview_scroll(-1 if event.delta>0 else 1,'units')
        return 'break'

    def bind_children(self,widget,key):
        widget.bind('<Button-1>',lambda e:self.choose(key))
        widget.bind('<MouseWheel>',self.wheel)
        widget.configure(cursor='hand2')
        for child in widget.winfo_children():self.bind_children(child,key)

    def paint(self,widget,color,badge):
        if widget is badge:return
        widget.configure(bg=color)
        for child in widget.winfo_children():self.paint(child,color,badge)

    def choose(self,key):
        if self.selected:
            row,badge=self.widgets[self.selected]
            self.paint(row,self.row_backgrounds[self.selected],badge)
        self.selected=key
        row,badge=self.widgets[key]
        self.paint(row,ROW_SELECTED,badge)
        self.canvas.focus_set()
        self.on_select(next(r for r in self.rows if r['id']==key))

    def move(self,step):
        if not self.rows:return 'break'
        current=next((i for i,r in enumerate(self.rows) if r['id']==self.selected),-1)
        i=max(0,min(len(self.rows)-1,current+step))
        self.choose(self.rows[i]['id'])
        # Selection can navigate to another page and close this table's dialog.
        if not self.winfo_exists():return 'break'
        row,_=self.widgets[self.selected]
        self.canvas.yview_moveto(max(0,row.winfo_y()-45)/max(1,self.content.winfo_height()))
        return 'break'
