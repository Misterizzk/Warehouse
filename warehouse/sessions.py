"""Session workflow independent of camera and UI; snapshots are historical facts."""
import json
from datetime import datetime
from .domain import aging, NORMAL_MAX, AGE_LIMIT
from .labels import resolve
from .recommendation_data import recommendation_context
from .recommendations import recommend_for


def required(value,label):
    value=str(value).strip()
    if not 1 <= len(value) <= 100:
        raise ValueError(f'{label} wajib diisi, maksimal 100 karakter.')
    return value


class Sessions:
    def __init__(self,db):
        self.db=db

    def start(self,officer,area,normal_max=NORMAL_MAX,age_limit=AGE_LIMIT):
        officer,area=required(officer,'Nama / NIK petugas'),required(area,'Area pengecekan')
        try:
            normal_max,age_limit=int(str(normal_max)),int(str(age_limit))
            if not 0<=normal_max<age_limit<=365000:raise ValueError()
        except ValueError as exc:
            raise ValueError('Batas umur harus bilangan bulat: 0 ≤ normal < batas umur ≤ 365000.') from exc
        with self.db:
            result=self.db.execute('''INSERT INTO check_sessions
                (officer,area,started_at,normal_max,age_limit) VALUES(?,?,?,?,?)''',
                (officer,area,datetime.now().astimezone().isoformat(timespec='seconds'),normal_max,age_limit))
        return result.lastrowid

    def get(self,key):
        row=self.db.execute('SELECT * FROM check_sessions WHERE id=?',(key,)).fetchone()
        if row is None:raise ValueError('Sesi tidak ditemukan.')
        return dict(row)

    def require_draft(self,key):
        session=self.get(key)
        if session['status']!='Draft':raise ValueError('Sesi sudah selesai dan terkunci.')
        return session

    def list(self):
        return [dict(r) for r in self.db.execute('''SELECT s.*,count(r.batch_id) AS total
            FROM check_sessions s LEFT JOIN check_results r ON r.session_id=s.id
            GROUP BY s.id ORDER BY s.id DESC''')]

    def results(self,key):
        self.get(key)
        result=[]
        for row in self.db.execute('SELECT * FROM check_results WHERE session_id=? ORDER BY checked_at,batch_id',(key,)):
            item=json.loads(row['snapshot'])
            item.update(checked_at=row['checked_at'],age=row['age'],status=row['status'],note=row['note'])
            result.append(item)
        return result

    def add_code(self,key,code):
        code=str(code).strip()
        code=code if code.startswith('ID:') else 'ID:'+code
        with self.db:
            session=self.require_draft(key)
            # Repeat scans preserve the original time and snapshot.
            batch=code[3:]
            exists=self.db.execute('SELECT 1 FROM check_results WHERE session_id=? AND batch_id=?',(key,batch)).fetchone()
            if exists:
                snapshot=self.db.execute('SELECT snapshot FROM check_results WHERE session_id=? AND batch_id=?',(key,batch)).fetchone()[0]
                self.mark_check(key,batch,json.loads(snapshot)['location_code'])
                return batch,False
            item=resolve(self.db,code)
            moment=datetime.now().astimezone()
            age,status=aging(item['received_date'],today=moment.date(),normal_max=session['normal_max'],age_limit=session['age_limit'])
            context=recommendation_context(self.db,item['material'])
            if not context['sites'] and not context['customers']:
                context=None
            advice=recommend_for(item,normal_max=session['normal_max'],
                                 age_limit=session['age_limit'],today=moment.date(),context=context)
            snapshot=dict(item,recommendation_at_check=advice)
            self.db.execute('''INSERT INTO check_results
                (session_id,batch_id,checked_at,snapshot,age,status) VALUES(?,?,?,?,?,?)''',
                (key,item['id'],moment.isoformat(timespec='seconds'),json.dumps(snapshot,ensure_ascii=False),age,status))
            self.mark_check(key,item['id'],item['location_code'])
        return item['id'],True

    def mark_check(self,key,batch,location):
        value=json.dumps(dict(session_id=key,batch_id=batch,location_code=location,
                             time=datetime.now().astimezone().isoformat(timespec='seconds')))
        self.db.execute("INSERT INTO metadata(key,value) VALUES('last_check',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(value,))

    def save_note(self,key,note,batch_id=None):
        note=str(note).strip()
        if len(note)>2000:raise ValueError('Catatan maksimal 2000 karakter.')
        with self.db:
            self.require_draft(key)
            if batch_id is None:
                self.db.execute('UPDATE check_sessions SET note=? WHERE id=?',(note,key))
            else:
                result=self.db.execute('UPDATE check_results SET note=? WHERE session_id=? AND batch_id=?',(note,key,batch_id))
                if result.rowcount!=1:raise ValueError('Barang belum ada di sesi ini.')

    def finish(self,key):
        with self.db:
            self.require_draft(key)
            if not self.db.execute('SELECT 1 FROM check_results WHERE session_id=?',(key,)).fetchone():
                raise ValueError('Tambahkan setidaknya satu hasil sebelum menyelesaikan sesi.')
            self.db.execute("UPDATE check_sessions SET status='Selesai',finished_at=? WHERE id=?",
                (datetime.now().astimezone().isoformat(timespec='seconds'),key))
