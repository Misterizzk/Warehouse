"""Batch editor; persistence and validation are shared with future import workflows."""
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date
from .locations import Locations
from .inventory import BatchValidationError
from .ui import BG, PANEL, FG, MUTED, BLUE
from .theme import (
    ACCENT_HOVER, DANGER, EDGE, FIELD_BORDER, FOCUS,
    SUCCESS, SURFACE_ALT,
)


class BatchEditor(tk.Toplevel):
    def __init__(self, app, item=None):
        super().__init__(app.root)
        self.app, self.item = app, item
        self.title("Ubah data barang" if item else "Tambah barang baru")
        self.configure(bg=BG)
        self.geometry("760x650")
        self.minsize(660, 600)
        self.transient(app.root)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        tk.Label(self, text=self.title(), bg=BG, fg=FG, font=('Segoe UI', 20, 'bold')).grid(sticky='w', padx=24, pady=(16, 3))
        tk.Label(self, text="ID batch: " + item['id'] + "  •  Perbarui data di bawah." if item else "Isi data barang dan lokasi. ID batch akan dibuat otomatis setelah disimpan.",
                 bg=BG, fg=MUTED, font=('Segoe UI', 10), wraplength=700, anchor='w').grid(sticky='w', padx=24)
        form = tk.Frame(self, bg=PANEL, padx=18, pady=14, highlightbackground=EDGE, highlightthickness=1)
        form.grid(row=2, column=0, sticky='nsew', padx=24, pady=(14, 10))
        form.columnconfigure((0, 1), weight=1, uniform='fields')
        tk.Label(form, text='Informasi barang', bg=PANEL, fg=FG,
                 font=('Segoe UI', 12, 'bold')).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 7))
        defaults = dict(material='', description='', plant='', storage_location='', location_code='',
                        received_date=date.today().isoformat(), stock='0')
        self.values, self.inputs, self.errors = {}, {}, {}
        fields = [('material', 'Nomor material / part'), ('description', 'Nama atau deskripsi barang'),
                  ('plant', 'Plant'), ('storage_location', 'Storage Location'),
                  ('location_code', 'Lokasi fisik (area · rak · kolom · baris · tingkat)'), ('received_date', 'Tanggal masuk · YYYY-MM-DD'),
                  ('stock', 'Stok setelah koreksi (unit)' if item else 'Jumlah stok masuk (unit)')]
        for i, (key, label) in enumerate(fields):
            cell = tk.Frame(form, bg=PANEL)
            cell.grid(row=1+i//2, column=i%2, sticky='nsew', padx=(0, 14) if i%2==0 else (14, 0), pady=3)
            tk.Label(cell, text=label, bg=PANEL, fg=MUTED, font=('Segoe UI', 10)).pack(anchor='w', pady=(0, 3))
            var = tk.StringVar(value=str(item[key] if item else defaults[key]))
            self.values[key] = var
            if key == 'location_code':
                widget = ttk.Combobox(cell, textvariable=var, values=Locations(app.db).choices(), state='readonly',
                                      font=('Segoe UI', 11), style='Warehouse.TCombobox')
            else:
                widget = tk.Entry(cell, textvariable=var, bg=PANEL, fg=FG, insertbackground=FG,
                                  relief='flat', font=('Segoe UI', 11), highlightthickness=1,
                                  highlightbackground=FIELD_BORDER, highlightcolor=FOCUS)
            widget.pack(fill='x', ipady=5)
            self.inputs[key] = widget
            error = tk.Label(cell, text='', bg=PANEL, fg=DANGER, font=('Segoe UI', 9), wraplength=300, justify='left')
            self.errors[key] = error
        self.message = tk.Label(self, text='Koreksi stok di formulir ini tidak tercatat sebagai pengeluaran. Untuk barang yang keluar gudang, gunakan "Catat barang keluar".' if item else 'Lokasi belum ada? Tutup formulir, lalu pilih "Kelola Lokasi" pada halaman Data Barang.',
                                bg=BG, fg=MUTED, wraplength=700, justify='left', anchor='w', font=('Segoe UI', 9))
        self.message.grid(row=3, column=0, sticky='ew', padx=24)
        actions = tk.Frame(self, bg=BG)
        actions.grid(row=4, column=0, sticky='ew', padx=24, pady=16)
        self.save_button = tk.Button(actions, text='Simpan perubahan' if item else 'Simpan barang & lihat QR', command=self.save,
                                    bg=BLUE, fg=FG, activebackground=ACCENT_HOVER, activeforeground=FG,
                                    relief='flat', padx=18, pady=10, font=('Segoe UI', 11, 'bold'), cursor='hand2')
        self.save_button.pack(side='right')
        tk.Button(actions, text='Batal', command=self.cancel, bg=PANEL, fg=FG, activebackground=SURFACE_ALT,
                  activeforeground=FG, relief='flat', padx=18, pady=10, cursor='hand2').pack(side='right', padx=10)
        self.initial = self.snapshot()
        self.protocol('WM_DELETE_WINDOW', self.cancel)
        self.bind('<Escape>', lambda e: self.cancel())
        self.bind('<Control-Return>', lambda e: self.save())
        self.grab_set()
        self.inputs['material'].focus_set()

    def snapshot(self):
        return {key: var.get() for key, var in self.values.items()}

    def cancel(self):
        if self.snapshot() != self.initial and not messagebox.askyesno('Batalkan perubahan?', 'Perubahan belum disimpan. Tutup formulir?', parent=self):
            return
        self.destroy()

    def save(self):
        for error in self.errors.values():
            error.configure(text='')
            error.pack_forget()
        try:
            if self.item:
                key = self.app.inventory.update(self.item['id'], self.snapshot(),expected_stock=self.item['stock'])
            else:
                key = self.app.inventory.add(self.snapshot())
        except BatchValidationError as exc:
            self.errors[exc.field].configure(text=str(exc))
            self.errors[exc.field].pack(anchor='w',pady=(3,0))
            self.inputs[exc.field].focus_set()
            return
        except (ValueError, sqlite3.Error) as exc:
            self.message.configure(text=f'Belum tersimpan: {exc}', fg=DANGER)
            return
        self.app.show('Data Barang')
        self.app.inventory_notice.configure(text='Perubahan tersimpan.' if self.item else 'Barang berhasil ditambahkan.', fg=SUCCESS)
        self.app.table.choose(key)
        self.destroy()
        self.app.show_label(key)
