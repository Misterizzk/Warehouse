"""Manual inspection sessions. Camera can reuse the same service in stage 8."""
import sqlite3
import tkinter as tk
from datetime import date
from tkinter import ttk, messagebox
from .sessions import Sessions
from .recommendations import RecommendationService, recommend_for
from .recommendation_data import recommendation_context
from .inventory_table import InventoryTable
from .ui import BG,PANEL,FG,MUTED,BLUE,display_time


def button(parent,text,command,primary=False):
    return tk.Button(parent,text=text,command=command,bg=BLUE if primary else PANEL,fg=FG,
                     activebackground='#1A6CD0' if primary else '#1B3A57',activeforeground=FG,
                     disabledforeground='#8FA6BB',font=('Segoe UI',10,'bold' if primary else 'normal'),
                     relief='flat',padx=14,pady=10,cursor='hand2',
                     highlightthickness=1,highlightbackground=BG,highlightcolor='#68B7FF')


def advice_for_result(db,session,item,decision=None):
    """Use today's inventory for a draft, or the frozen advice for history."""
    if decision and session['status'] != 'Draft':
        if decision.get('recommendation_snapshot'):
            return decision['recommendation_snapshot']
        return dict(code=decision['recommendation_code'],title=decision['recommendation_title'],
                    reason=decision['recommendation_reason'],next_action=decision['recommendation_next_action'])
    if session['status']=='Draft':
        current=db.execute('SELECT * FROM batches WHERE id=?',(item['id'],)).fetchone()
        if current:
            current=dict(current)
            context=recommendation_context(db,current['material'])
            if not context['sites'] and not context['customers']:
                context=None
            return recommend_for(current,normal_max=session['normal_max'],
                                 age_limit=session['age_limit'],today=date.today(),context=context)
    if item.get('recommendation_at_check'):
        return item['recommendation_at_check']
    checked_day=date.fromisoformat(item['checked_at'][:10])
    return recommend_for(item,normal_max=session['normal_max'],
                         age_limit=session['age_limit'],today=checked_day)


class SessionPage:
    def __init__(self,app):
        self.app=app
        self.service=Sessions(app.db)
        self.recommendations=RecommendationService(app.db)
        self.body=app.body
        self.session_id=None
        self.list_page()

    def clear(self):
        for child in self.body.winfo_children():child.destroy()

    def notice(self,text):
        self.info.configure(text=text)

    def list_page(self):
        self.clear()
        self.session_id=None
        tk.Label(self.body,text='Sesi pengecekan',bg=BG,fg=FG,
                 font=('Segoe UI',19,'bold'),anchor='w').pack(fill='x',pady=(0,3))
        tk.Label(self.body,text='Mulai pengecekan baru atau lanjutkan sesi yang masih berstatus Draft.',
                 bg=BG,fg=MUTED,font=('Segoe UI',10),anchor='w').pack(fill='x',pady=(0,14))
        toolbar=tk.Frame(self.body,bg=BG)
        toolbar.pack(fill='x',pady=(0,12))
        button(toolbar,'Mulai pengecekan baru',self.start_form,True).pack(side='left')
        self.open_button=button(toolbar,'Buka sesi yang dipilih',self.open_selected)
        self.open_button.pack(side='right')
        host=tk.Frame(self.body,bg=BG)
        host.pack(fill='both',expand=True)
        host.columnconfigure(0,weight=1)
        host.rowconfigure(0,weight=1)
        self.list_table=ttk.Treeview(host,columns=('id','officer','area','time','status','count'),show='headings',selectmode='browse')
        for key,title,width in [('id','Nomor sesi',130),('officer','Petugas',170),('area','Area',130),('time','Waktu mulai',210),('status','Status sesi',110),('count','Hasil',70)]:
            self.list_table.heading(key,text=title)
            self.list_table.column(key,width=width,minwidth=width)
        self.list_table.tag_configure('even',background=PANEL,foreground=FG)
        self.list_table.tag_configure('odd',background='#152E47',foreground=FG)
        self.list_table.grid(row=0,column=0,sticky='nsew')
        sy=ttk.Scrollbar(host,command=self.list_table.yview)
        sy.grid(row=0,column=1,sticky='ns')
        sx=ttk.Scrollbar(host,orient='horizontal',command=self.list_table.xview)
        sx.grid(row=1,column=0,sticky='ew')
        self.list_table.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
        for index,row in enumerate(self.service.list()):
            self.list_table.insert('','end',iid=str(row['id']),tags=('even' if index%2==0 else 'odd',),
                                   values=(f"CHK-{row['id']:06d}",row['officer'],row['area'],display_time(row['started_at']),row['status'],row['total']))
        self.list_table.bind('<Double-1>',lambda e:self.open_selected())
        self.list_table.bind('<Return>',lambda e:self.open_selected())
        self.info=self.app.label(self.body,'Belum ada sesi. Pilih Mulai pengecekan baru untuk memulai.' if not self.list_table.get_children() else 'Klik dua kali sesi untuk membuka. Sesi selesai hanya dapat dilihat.',10)

    def open_selected(self):
        selected=self.list_table.selection()
        if selected:self.open_session(int(selected[0]))
        else:self.notice('Pilih satu sesi terlebih dahulu.')

    def start_form(self,on_started=None):
        win=tk.Toplevel(self.app.root)
        self.start_window=win
        win.title('Mulai pengecekan baru')
        win.configure(bg=BG)
        win.geometry('620x460')
        win.minsize(580,430)
        win.transient(self.app.root)
        win.grab_set()
        win.columnconfigure(1,weight=1)
        self.start_vars={}
        tk.Label(win,text='Pengecekan baru',bg=BG,fg=FG,font=('Segoe UI',19,'bold'),anchor='w').grid(
            row=0,column=0,columnspan=2,sticky='ew',padx=20,pady=(16,4))
        for i,(key,label,value) in enumerate((('officer','Nama atau NIK petugas',''),('area','Area gudang',''),('normal','Normal hingga (hari)','30'),('limit','Batas umur (hari)','90')),start=1):
            tk.Label(win,text=label,bg=BG,fg=MUTED,font=('Segoe UI',11)).grid(row=i,column=0,sticky='w',padx=20,pady=14)
            var=tk.StringVar(value=value)
            self.start_vars[key]=var
            tk.Entry(win,textvariable=var,bg=PANEL,fg=FG,insertbackground=FG,font=('Segoe UI',11),
                     relief='flat',highlightthickness=1,highlightbackground='#355470',highlightcolor=BLUE).grid(row=i,column=1,sticky='ew',padx=20,ipady=6)
        error=tk.Label(win,text='Status dihitung dari umur barang saat dicek. Status tidak menilai kondisi fisiknya.',
                       bg=BG,fg=MUTED,wraplength=540,justify='left')
        error.grid(row=5,column=0,columnspan=2,sticky='w',padx=20,pady=12)
        def save():
            try:
                values={k:v.get() for k,v in self.start_vars.items()}
                key=self.service.start(values['officer'],values['area'],values['normal'],values['limit'])
            except (ValueError,sqlite3.Error) as exc:
                error.configure(text=str(exc),fg='#FFA3AA')
                return
            win.destroy()
            self.open_session(key)
            if on_started:on_started()
        self.start_save=button(win,'Mulai pengecekan',save,True)
        self.start_save.grid(row=6,column=1,sticky='e',padx=20,pady=12)
        button(win,'Batal',win.destroy).grid(row=6,column=0,sticky='w',padx=20,pady=12)
        win.bind('<Escape>',lambda e:win.destroy())

    def open_session(self,key):
        session=self.service.get(key)
        self.clear()
        self.session_id=key
        self.selected=None
        draft=session['status']=='Draft'
        toolbar=tk.Frame(self.body,bg=BG)
        toolbar.pack(fill='x')
        button(toolbar,'Kembali ke daftar sesi',self.list_page).pack(side='left')
        self.finish_button=button(toolbar,'Selesaikan sesi',self.finish,True)
        self.finish_button.pack(side='right')
        self.finish_button.configure(state='normal' if draft else 'disabled')
        self.app.label(self.body,f"Sesi CHK-{key:06d}  •  {session['status']}",18,FG,True)
        self.app.label(self.body,f"Petugas: {session['officer']}   •   Area: {session['area']}   •   Mulai: {display_time(session['started_at'])}\nNormal ≤ {session['normal_max']} hari   •   Peringatan ≤ {session['age_limit']} hari   •   Melewati batas > {session['age_limit']} hari",10)
        codes=tk.Frame(self.body,bg=BG)
        codes.pack(fill='x',pady=(8,4))
        codes.columnconfigure(0,weight=1)
        tk.Label(codes,text='Kode batch atau isi QR',bg=BG,fg=MUTED,font=('Segoe UI',10),anchor='w').grid(
            row=0,column=0,columnspan=3,sticky='w',pady=(0,5))
        self.code=tk.StringVar()
        self.code_entry=tk.Entry(codes,textvariable=self.code,bg=PANEL,fg=FG,insertbackground=FG,font=('Segoe UI',11),
                                 relief='flat',highlightthickness=1,highlightbackground='#355470',highlightcolor=BLUE)
        self.code_entry.grid(row=1,column=0,sticky='ew',ipady=8,padx=(0,8))
        self.add_button=button(codes,'Tambahkan ke hasil',self.add,True)
        self.add_button.grid(row=1,column=1)
        self.camera_button=button(codes,'Scan dengan kamera',self.open_camera)
        self.camera_button.grid(row=1,column=2,padx=(8,0))
        self.camera_button.configure(state='normal' if draft else 'disabled')
        self.code_entry.configure(state='normal' if draft else 'disabled')
        self.add_button.configure(state='normal' if draft else 'disabled')
        self.code_entry.bind('<Return>',lambda e:self.add())
        self.info=self.app.label(self.body,'Ketik ID batch atau pindai QR. Contoh: ID:DEMO-0001. Batch yang sama hanya tercatat sekali.' if draft else f"Sesi dikunci pada {display_time(session['finished_at'])}. Hasil menunjukkan data saat pengecekan.",10)
        self.host=tk.Frame(self.body,bg=BG)
        self.host.pack(fill='both',expand=True)
        self.table=InventoryTable(self.host,self.service.results(key),self.select,inspection=True)
        self.table.pack(fill='both',expand=True)
        bottom=tk.Frame(self.body,bg=BG)
        self.host.pack_forget()
        bottom.pack(side='bottom',fill='x',pady=8)
        button(bottom,'Catatan sesi',lambda:self.note_dialog()).pack(side='left')
        self.item_note_button=button(bottom,'Detail & catatan hasil',self.item_detail)
        self.item_note_button.pack(side='left',padx=8)
        self.item_note_button.configure(state='disabled')
        self.action_button=button(bottom,'Saran & keputusan',self.action_dialog)
        self.action_button.pack(side='left')
        self.action_button.configure(state='disabled')
        self.summary=tk.Label(bottom,bg=BG,fg=MUTED,font=('Segoe UI',10))
        self.summary.pack(side='right')
        self.host.pack(fill='both',expand=True)
        self.update_summary()

    def update_summary(self):
        rows=self.table.rows
        counts=[sum(r['status']==s for r in rows) for s in ('Normal','Warning','Melewati batas')]
        self.summary.configure(text=f'{len(rows)} hasil   •   Normal {counts[0]}   •   Peringatan {counts[1]}   •   Melewati batas {counts[2]}')

    def select(self,row):
        self.selected=row
        self.item_note_button.configure(state='normal')
        self.action_button.configure(state='normal')

    def add(self):
        try:key,added=self.service.add_code(self.session_id,self.code.get())
        except (ValueError,sqlite3.Error) as exc:
            self.notice(str(exc))
            return
        self.refresh_results(key)
        self.notice('Hasil tersimpan.' if added else 'Batch sudah ada. Waktu dan hasil pengecekan pertama dipertahankan.')
        self.code.set('')
        self.code_entry.focus_set()

    def refresh_results(self,key):
        self.table.destroy()
        self.table=InventoryTable(self.host,self.service.results(self.session_id),self.select,inspection=True)
        self.table.pack(fill='both',expand=True)
        self.table.choose(key)
        self.update_summary()

    def open_camera(self):
        from .camera_ui import CameraWindow
        self.app.stop_camera()
        self.app.pause_live_for_scan()
        try:
            self.app.camera_window=CameraWindow(self.app,self.session_id,self.refresh_results)
        except (ValueError,sqlite3.Error) as exc:
            self.app.resume_live_after_scan(None)
            self.notice(str(exc))
        except Exception:
            self.app.resume_live_after_scan(None)
            raise

    def item_detail(self):
        if self.selected:self.note_dialog(self.selected)

    def action_dialog(self):
        """Show aging advice separately from the officer's physical assessment."""
        if not self.selected:return
        item=self.selected
        session=self.service.get(self.session_id)
        decision=self.recommendations.for_result(self.session_id,item['id'])
        advice=advice_for_result(self.app.db,session,item,decision)
        win=tk.Toplevel(self.app.root)
        self.action_window=win
        win.title('Saran aging dan keputusan petugas')
        win.geometry(f"720x{min(640,self.app.root.winfo_screenheight()-90)}")
        win.minsize(640,500)
        win.configure(bg=BG)
        win.transient(self.app.root)
        win.grab_set()

        # Reserve the action footer before allowing long advice to scroll.
        footer=tk.Frame(win,bg=BG,padx=22,pady=12)
        footer.pack(side='bottom',fill='x')
        host=tk.Frame(win,bg=BG)
        host.pack(fill='both',expand=True)
        canvas=tk.Canvas(host,bg=BG,highlightthickness=0)
        scrollbar=ttk.Scrollbar(host,orient='vertical',command=canvas.yview)
        scrollbar.pack(side='right',fill='y')
        canvas.pack(fill='both',expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        content=tk.Frame(canvas,bg=BG,padx=22,pady=16)
        window=canvas.create_window(0,0,window=content,anchor='nw')
        content.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        def fit_content(event):
            canvas.itemconfigure(window,width=event.width)
            for label in wrapping_labels:
                label.configure(wraplength=max(200,event.width-74))
        wrapping_labels=[]
        canvas.bind('<Configure>',fit_content)
        tk.Label(content,text=f"{item['material']}  •  {item['id']}",bg=BG,fg=FG,
                 font=('Segoe UI',17,'bold'),anchor='w').pack(fill='x')
        tk.Label(content,text=f"{item['location_code']}  •  {item['age']} hari pada {display_time(item['checked_at'])}  •  {item['status']}",
                 bg=BG,fg=MUTED,font=('Segoe UI',10),anchor='w').pack(fill='x',pady=(3,12))
        card=tk.Frame(content,bg=PANEL,padx=15,pady=12)
        card.pack(fill='x')
        context=('TERKINI' if session['status']=='Draft' else
                 'SAAT KEPUTUSAN' if decision else 'DARI DATA SAAT CEK')
        source=' · Simulasi' if advice.get('source')=='Simulasi' else ''
        tk.Label(card,text=f"SARAN APLIKASI {context}{source}  •  {advice['title']}",bg=PANEL,fg='#83C5FF',
                 font=('Segoe UI',11,'bold'),anchor='w').pack(fill='x')
        for value,color in ((advice['reason'],MUTED),(advice['next_action'],FG)):
            tk.Label(card,text=value,bg=PANEL,fg=color,font=('Segoe UI',10),
                     justify='left',anchor='w',wraplength=630).pack(fill='x',pady=(5,0))
        for number, option in enumerate(advice.get('options') or (), start=1):
            tk.Label(card,text=f"Opsi {number}: {option['title']}",bg=PANEL,fg='#B7DCFF',
                     font=('Segoe UI',10,'bold'),justify='left',anchor='w',
                     wraplength=630).pack(fill='x',pady=(5,0))
        tk.Label(content,text='Saran ini mempertimbangkan umur dan kebutuhan simulasi. Keputusan dibuat setelah pemeriksaan fisik oleh petugas.' if source else
                 'Saran ini berdasarkan umur barang. Keputusan dibuat setelah pemeriksaan fisik oleh petugas.',
                 bg=BG,fg=MUTED,font=('Segoe UI',9),anchor='w',wraplength=650,justify='left').pack(fill='x',pady=(9,12))
        feedback=tk.Label(footer,text='',bg=BG,fg='#FFA3AA',font=('Segoe UI',10),anchor='w',
                          wraplength=650,justify='left')

        if session['status']=='Draft':
            tk.Label(content,text='Kondisi fisik setelah diperiksa',bg=BG,fg=FG,font=('Segoe UI',10,'bold'),
                     anchor='w').pack(fill='x',pady=(0,4))
            self.condition_var=tk.StringVar(value=decision['physical_condition'] if decision else '')
            condition=ttk.Combobox(content,textvariable=self.condition_var,
                                   values=('Layak','Perlu evaluasi','Tidak layak'),state='readonly',
                                   style='Warehouse.TCombobox')
            condition.pack(fill='x')
            tk.Label(content,text='Keputusan tindak lanjut',bg=BG,fg=FG,font=('Segoe UI',10,'bold'),
                     anchor='w').pack(fill='x',pady=(11,4))
            self.choice_var=tk.StringVar(value=decision['choice'] if decision else '')
            choice_row=tk.Frame(content,bg=BG)
            choice_row.pack(fill='x')
            choice_row.columnconfigure(0,weight=1)
            choice_row.columnconfigure(1,weight=1)
            target_kind_for_choice={'Pindahkan ke site':'site','Tawarkan ke customer':'customer'}
            options=advice.get('options') or ()
            available_target_choices=tuple(choice for choice,kind in target_kind_for_choice.items()
                                           if any(option['kind']==kind for option in options) or
                                           (decision and decision['choice']==choice))
            self.choice_values=available_target_choices+(
                'Perlu dipindahkan','Prioritaskan pemakaian','Tunda evaluasi','Tidak perlu tindakan')
            choice=ttk.Combobox(choice_row,textvariable=self.choice_var,
                                values=self.choice_values,state='readonly',
                                style='Warehouse.TCombobox')
            choice.grid(row=0,column=0,sticky='ew',padx=(0,8))
            def target_label(option):
                prefix='Customer' if option['kind']=='customer' else 'Site'
                return f"{prefix} {option['target']}"
            target_choices=tuple(target_label(option) for option in options)
            saved_target=(f"{'Customer' if decision['target_kind']=='customer' else 'Site'} "
                          f"{decision['target_code']}" if decision and decision.get('target_kind') and
                          decision.get('target_code') else '')
            self.target_var=tk.StringVar(value=saved_target)
            self.target_combo=ttk.Combobox(choice_row,textvariable=self.target_var,
                                           values=target_choices,state='disabled',
                                           style='Warehouse.TCombobox')
            self.target_combo.grid(row=0,column=1,sticky='ew')
            tk.Label(choice_row,text='Tujuan rekomendasi (untuk penawaran / relokasi)',
                     bg=BG,fg=MUTED,font=('Segoe UI',9),anchor='w').grid(
                         row=1,column=1,sticky='w',pady=(3,0))
            def update_target_choices(*_):
                kind=target_kind_for_choice.get(self.choice_var.get())
                matching=tuple(target_label(option) for option in options
                               if option['kind']==kind)
                self.target_combo.configure(values=matching,
                                            state='readonly' if kind and matching else 'disabled')
                if self.target_var.get() not in matching:
                    self.target_var.set('')
            self.choice_var.trace_add('write',update_target_choices)
            update_target_choices()
            if saved_target and self.target_var.get() != saved_target:
                feedback.configure(text=f'Tujuan sebelumnya ({saved_target}) tidak ada pada saran terkini. '
                                        'Pilih ulang tindak lanjut dan tujuannya.')
            tk.Label(content,text='Alasan / hasil pemeriksaan',bg=BG,fg=FG,font=('Segoe UI',10,'bold'),
                     anchor='w').pack(fill='x',pady=(11,4))
            self.reason_text=tk.Text(content,bg=PANEL,fg=FG,insertbackground=FG,font=('Segoe UI',10),
                                     wrap='word',height=4,relief='flat',padx=10,pady=8,
                                     highlightthickness=1,highlightbackground='#355470',highlightcolor=BLUE)
            self.reason_text.pack(fill='both',expand=True)
            if decision:self.reason_text.insert('1.0',decision['reason'])
            feedback.pack(fill='x',pady=(8,0))
            def save_decision():
                try:
                    kind=target_kind_for_choice.get(self.choice_var.get())
                    selected_option=next((option for option in options
                                          if option['kind']==kind and
                                          target_label(option)==self.target_var.get()),None)
                    self.recommendations.save_decision(self.session_id,item['id'],
                        self.condition_var.get(),self.choice_var.get(),self.reason_text.get('1.0','end-1c'),
                        target_kind=kind,target_code=selected_option['target'] if selected_option else None)
                except (ValueError,sqlite3.Error) as exc:
                    feedback.configure(text=str(exc))
                    return
                win.destroy()
                self.refresh_results(item['id'])
                self.notice('Keputusan petugas tersimpan. Saran aplikasi dan keputusan dicatat terpisah.')
            actions=tk.Frame(footer,bg=BG)
            actions.pack(fill='x',pady=(7,0))
            self.action_save=button(actions,'Perbarui keputusan' if decision else 'Simpan keputusan',save_decision,True)
            self.action_save.pack(side='right')
            button(actions,'Batal',win.destroy).pack(side='right',padx=8)
        else:
            tk.Label(content,text='KEPUTUSAN PETUGAS',bg=BG,fg='#83C5FF',
                     font=('Segoe UI',11,'bold'),anchor='w').pack(fill='x')
            if decision:
                target=(f"Tujuan keputusan: {'Customer' if decision['target_kind']=='customer' else 'Site'} "
                        f"{decision['target_code']}\n" if decision.get('target_kind') and
                        decision.get('target_code') else '')
                summary=(f"Kondisi: {decision['physical_condition']}  •  Keputusan: {decision['choice']}\n"
                         f"{target}"
                         f"Alasan: {decision['reason'] or '—'}\n"
                         f"Dicatat oleh {decision['officer']} pada {display_time(decision['decided_at'])}")
            else:
                summary='Belum ada keputusan pada hasil ini. Sesi telah selesai dan hasilnya terkunci.'
            tk.Label(content,text=summary,bg=BG,fg=FG,font=('Segoe UI',10),justify='left',
                     anchor='w',wraplength=650).pack(fill='x',pady=(7,10))
            self.action_save=button(content,'Simpan keputusan',lambda:None)
            self.action_save.configure(state='disabled')
            if decision and decision['action_status']=='Belum selesai':
                tk.Label(content,text='Penyelesaian tindak lanjut',bg=BG,fg='#83C5FF',
                         font=('Segoe UI',11,'bold'),anchor='w').pack(fill='x',pady=(4,5))
                tk.Label(content,text='Nama petugas yang menyelesaikan',bg=BG,fg=MUTED,
                         font=('Segoe UI',10),anchor='w').pack(fill='x')
                self.completion_actor=tk.Entry(content,bg=PANEL,fg=FG,insertbackground=FG,
                                               font=('Segoe UI',10),relief='flat')
                self.completion_actor.pack(fill='x',ipady=7,pady=(3,8))
                tk.Label(content,text='Catatan penyelesaian',bg=BG,fg=MUTED,
                         font=('Segoe UI',10),anchor='w').pack(fill='x')
                self.completion_note=tk.Text(content,bg=PANEL,fg=FG,insertbackground=FG,
                                             font=('Segoe UI',10),wrap='word',height=3,
                                             relief='flat',padx=10,pady=8)
                self.completion_note.pack(fill='both',expand=True,pady=(3,0))
                feedback.pack(fill='x',pady=(8,0))
                def complete():
                    try:self.recommendations.complete(decision['id'],self.completion_actor.get(),
                        self.completion_note.get('1.0','end-1c'))
                    except (ValueError,sqlite3.Error) as exc:
                        feedback.configure(text=str(exc))
                        return
                    win.destroy()
                    self.notice('Tindak lanjut ditandai selesai. Stok barang tidak berubah otomatis.')
                self.completion_save=button(footer,'Tandai tindak lanjut selesai',complete,True)
                self.completion_save.pack(side='right',pady=(8,0))
            elif decision and decision['action_status']=='Selesai':
                tk.Label(content,text=f"Selesai oleh {decision['completed_by']} pada {display_time(decision['completed_at'])}\n"
                         f"Catatan: {decision['completion_note'] or '—'}",bg=BG,fg='#58DCA5',
                         font=('Segoe UI',10),justify='left',anchor='w',wraplength=650).pack(fill='x')
            button(footer,'Tutup',win.destroy).pack(side='right',padx=8,pady=(8,0))
        def reveal(widget):
            canvas.update_idletasks()
            top=widget.winfo_rooty()-content.winfo_rooty()
            bottom=top+widget.winfo_height()
            view_top=canvas.canvasy(0)
            height=canvas.winfo_height()
            if top < view_top:
                canvas.yview_moveto(max(0,top-8)/max(1,content.winfo_height()))
            elif bottom > view_top+height:
                canvas.yview_moveto(max(0,min(top,bottom-height+8))/max(1,content.winfo_height()))
        def wheel(event):
            canvas.yview_scroll(-1 if event.delta>0 else 1,'units')
            return 'break'
        def bind_content(widget):
            if isinstance(widget,tk.Label) and int(widget.cget('wraplength')):
                wrapping_labels.append(widget)
            if isinstance(widget,(tk.Entry,ttk.Combobox,tk.Text)):
                widget.bind('<FocusIn>',lambda event:reveal(event.widget),add='+')
            if not isinstance(widget,(tk.Text,ttk.Combobox)):
                widget.bind('<MouseWheel>',wheel,add='+')
            for child in widget.winfo_children():bind_content(child)
        bind_content(content)
        canvas.bind('<MouseWheel>',wheel)
        win.bind('<Escape>',lambda e:win.destroy())

    def note_dialog(self,item=None):
        session=self.service.get(self.session_id)
        win=tk.Toplevel(self.app.root)
        self.note_window=win
        win.title('Detail hasil dan catatan' if item else 'Catatan sesi')
        win.geometry('680x570')
        win.minsize(600,500)
        win.configure(bg=BG)
        win.transient(self.app.root)
        win.grab_set()
        win.columnconfigure(0,weight=1)
        win.rowconfigure(1,weight=1)
        if item:
            text=f"{item['id']}\n{item['material']} — {item['description']}\nLokasi: {item['location_code']} | Tanggal masuk (GR): {item['received_date']}\nPlant: {item['plant']} | Storage Location: {item['storage_location']}\nStok: {item['stock']} | Umur: {item['age']} hari | {item['status']}\nWaktu pengecekan: {display_time(item['checked_at'])}"
        else:
            text=f"CHK-{self.session_id:06d} • {session['officer']}\nArea: {session['area']} • {session['status']}\nCatatan sesi (maksimal 2000 karakter)"
        header=tk.Label(win,text=text,bg=BG,fg=FG,font=('Segoe UI',11),wraplength=620,justify='left')
        header.grid(row=0,column=0,sticky='w',padx=20,pady=16)
        self.note_text=tk.Text(win,bg=PANEL,fg=FG,insertbackground=FG,font=('Segoe UI',11),
                               wrap='word',height=6,relief='flat',padx=12,pady=10,
                               highlightthickness=1,highlightbackground='#355470',highlightcolor=BLUE)
        self.note_text.grid(row=1,column=0,sticky='nsew',padx=20)
        initial=item['note'] if item else session['note']
        self.note_text.insert('1.0',initial)
        error=tk.Label(win,text='Simpan catatan sebelum menutup. Catatan tidak mengubah status aging.',bg=BG,fg=MUTED,wraplength=620)
        error.grid(row=2,column=0,sticky='w',padx=20,pady=10)
        def save():
            try:self.service.save_note(session['id'],self.note_text.get('1.0','end-1c'),item['id'] if item else None)
            except (ValueError,sqlite3.Error) as exc:
                error.configure(text=str(exc),fg='#FFA3AA')
                return
            win.destroy()
            self.open_session(session['id'])
            self.notice('Catatan tersimpan.')
        self.note_save=button(win,'Simpan catatan',save,True)
        self.note_save.grid(row=3,column=0,sticky='e',padx=20,pady=12)
        if session['status']!='Draft':
            self.note_text.configure(state='disabled')
            self.note_save.configure(state='disabled')
            error.configure(text='Sesi selesai: catatan dan hasil terkunci.')
        def close():
            if session['status']=='Draft' and self.note_text.get('1.0','end-1c')!=initial:
                if not messagebox.askyesno('Tutup tanpa menyimpan?','Perubahan catatan belum disimpan.',parent=win):return
            win.destroy()
        button(win,'Tutup',close).grid(row=3,column=0,sticky='w',padx=20,pady=12)
        win.protocol('WM_DELETE_WINDOW',close)
        win.bind('<Escape>',lambda e:close())

    def finish(self):
        if not self.table.rows:
            self.notice('Tambahkan setidaknya satu hasil sebelum menyelesaikan sesi.')
            return
        if not messagebox.askyesno('Selesaikan sesi?',f'{len(self.table.rows)} hasil akan dikunci. Kode dan catatan tidak dapat ditambahkan atau diubah setelah selesai.',parent=self.app.root):return
        try:self.service.finish(self.session_id)
        except (ValueError,sqlite3.Error) as exc:
            self.notice(str(exc))
            return
        self.open_session(self.session_id)
