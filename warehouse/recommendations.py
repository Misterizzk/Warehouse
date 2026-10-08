"""Explainable aging advice and auditable staff decisions.

Advice is calculated for the current date. A decision retains the advice the
officer saw, while a separate immutable completion can be recorded later.
"""
import json
from datetime import datetime

from .domain import AGE_LIMIT, NORMAL_MAX, aging
from .recommendation_data import recommendation_context


CONDITIONS = ('Layak', 'Perlu evaluasi', 'Tidak layak')
CHOICES = ('Perlu dipindahkan', 'Prioritaskan pemakaian',
           'Tunda evaluasi', 'Tidak perlu tindakan',
           'Pindahkan ke site', 'Tawarkan ke customer')
TARGET_CHOICES = {'Pindahkan ke site': 'site', 'Tawarkan ke customer': 'customer'}


def _customer_options(customers, stock):
    options = []
    for customer in customers:
        name = customer.get('customer')
        unit_model = customer.get('unit_model')
        open_demand = customer.get('open_demand')
        if (not isinstance(name, str) or not name.strip() or
                not isinstance(unit_model, str) or not unit_model.strip() or
                type(open_demand) is not int or open_demand <= 0):
            continue
        units = min(stock, open_demand)
        target = name.strip()
        options.append(dict(kind='customer', target=target,
                            title=f'Tawarkan ke Customer {target} setelah cek fisik',
                            reason=(f'Customer {target} membutuhkan {open_demand} unit '
                                    f'untuk model {unit_model.strip()}.'),
                            next_action=(f'Cek fisik; jika layak, tawarkan {units} unit '
                                         f'ke Customer {target}.'),
                            suggested_units=units))
    options.sort(key=lambda option: (-option['suggested_units'], option['target']))
    return options


def _site_options(sites, stock, *, rising_only, after_check):
    options = []
    for site in sites:
        name = site.get('site')
        prev = site.get('demand_prev')
        now = site.get('demand_now')
        open_demand = site.get('open_demand')
        site_stock = site.get('site_stock')
        if (not isinstance(name, str) or not name.strip() or
                any(type(value) is not int or value < 0 for value in
                    (prev, now, open_demand, site_stock)) or
                now <= 0 or open_demand <= site_stock):
            continue
        if rising_only and (now - prev < 2 or now * 5 < prev * 6):
            continue
        shortage = open_demand - site_stock
        units = min(stock, shortage)
        target = name.strip()
        intro = 'Jika fisik layak, ajukan redistribusi' if after_check else 'Pertimbangkan relokasi'
        demand_note = (f'Demand naik dari {prev} ke {now} unit' if now > prev
                       else f'Demand saat ini {now} unit (sebelumnya {prev})')
        options.append(dict(kind='site', target=target,
                            title=f'Relokasi ke Site {target}',
                            reason=(f'{demand_note}; '
                                    f'Site {target} kekurangan {shortage} unit.'),
                            next_action=(f'{intro} {units} unit ke Site {target} '
                                         'setelah konfirmasi petugas.'),
                            suggested_units=units))
    options.sort(key=lambda option: (-option['suggested_units'], option['target']))
    return options


def recommend_for(item, *, normal_max=NORMAL_MAX, age_limit=AGE_LIMIT, today=None,
                  context=None):
    """Return current advice from known facts; never infer another site's need."""
    try:
        stock = item['stock']
        if type(stock) is not int or stock < 0:
            raise ValueError('Stok tidak valid.')
        age, status = aging(item['received_date'], today=today,
                            normal_max=normal_max, age_limit=age_limit)
    except (KeyError, TypeError, ValueError):
        advice = dict(code='DATA_PERLU_DIPERBAIKI', title='Perbaiki data barang',
                      reason='Tanggal masuk atau stok tidak valid untuk menghitung rekomendasi.',
                      next_action='Perbaiki data barang sebelum menentukan tindak lanjut.', priority=3)
        if context is not None:
            advice.update(source=context.get('source', 'Simulasi'), options=[])
        return advice

    if stock == 0:
        advice = dict(code='STOK_HABIS', title='Tidak ada stok aktif',
                      reason='Stok batch ini 0 unit; tidak ada barang fisik yang perlu ditindaklanjuti.',
                      next_action='Lihat riwayat barang keluar jika diperlukan.', priority=0)
        if context is not None:
            advice.update(source=context.get('source', 'Simulasi'), options=[])
        return advice
    if status == 'Melewati batas':
        advice = dict(code='MELEWATI_BATAS', title='Periksa barang segera',
                      reason=f'Umur {age} hari; {age-age_limit} hari melewati batas {age_limit} hari.',
                      next_action=('Prioritaskan pemeriksaan fisik. Jika barang masih layak dan ada '
                                   'kebutuhan di site lain, pertimbangkan transfer.'), priority=3)
        if context is None:
            return advice
        options = (_customer_options(context.get('customers', ()), stock) +
                   _site_options(context.get('sites', ()), stock,
                                 rising_only=False, after_check=True))
        advice.update(source=context.get('source', 'Simulasi'), options=options)
        if options:
            destinations = '; alternatif '.join(
                (f"penawaran kepada Customer {option['target']}" if option['kind'] == 'customer'
                 else f"redistribusi ke Site {option['target']}") for option in options)
            advice['next_action'] = ('Cek fisik segera. Jika layak, pertimbangkan '
                                     f'{destinations}. Pilihan akhir oleh petugas.')
            advice['reason'] += ' ' + ' '.join(option['reason'] for option in options)
        else:
            advice['next_action'] = ('Prioritaskan pemeriksaan fisik. Tujuan belum dapat ditentukan '
                                     'karena tidak ada kebutuhan site atau customer yang cocok '
                                     'dalam data simulasi.')
        return advice
    if status == 'Warning':
        advice = dict(code='WARNING', title='Jadwalkan pemeriksaan',
                      reason=f'Umur {age} hari; {age_limit+1-age} hari menuju status Melewati batas.',
                      next_action=('Periksa kondisi fisik dan prioritaskan penggunaan batch yang '
                                   'lebih tua jika masih layak.'), priority=2)
        if context is None:
            return advice
        options = _customer_options(context.get('customers', ()), stock)
        advice.update(source=context.get('source', 'Simulasi'), options=options)
        if options:
            advice.update(title=options[0]['title'], next_action=options[0]['next_action'],
                          reason=f"{advice['reason']} {options[0]['reason']}")
        return advice
    if normal_max+1-age <= 7:
        advice = dict(code='NORMAL_DEKAT_WARNING', title='Mendekati Warning',
                      reason=f'Umur {age} hari; {normal_max+1-age} hari menuju status Warning.',
                      next_action=('Pantau barang. Jika ada batch material yang sama dan lebih tua, '
                                   'dahulukan batch yang lebih tua saat pengambilan.'), priority=1)
    else:
        advice = dict(code='NORMAL', title='Pantau barang',
                      reason=f'Umur {age} hari; masih dalam batas Normal hingga {normal_max} hari.',
                      next_action='Belum ada tindakan khusus berdasarkan umur barang.', priority=0)
    if context is None:
        return advice
    options = _site_options(context.get('sites', ()), stock,
                            rising_only=True, after_check=False)
    advice.update(source=context.get('source', 'Simulasi'), options=options)
    if options:
        advice.update(title=options[0]['title'],
                      next_action=options[0]['next_action'],
                      reason=f"{advice['reason']} {options[0]['reason']}")
    elif advice['code'] == 'NORMAL' and context.get('sites'):
        advice.update(title='Aman, belum perlu tindakan',
                      next_action=('Belum perlu tindakan berdasarkan kriteria relokasi saat ini. '
                                   'Pantau kebutuhan site dan perubahan demand.'))
    return advice


def _required(value, label, maximum=2000):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
        raise ValueError(f'{label} wajib diisi, maksimal {maximum} karakter.')
    return value.strip()


class RecommendationService:
    def __init__(self, db):
        self.db = db

    def _decision(self, where, params):
        row = self.db.execute('''SELECT d.*,c.officer AS completed_by,
                    c.completed_at,c.note AS completion_note
                FROM recommendation_decisions d
                LEFT JOIN recommendation_completions c ON c.decision_id=d.id
                WHERE ''' + where, params).fetchone()
        if row is None:
            return None
        rec = json.loads(row['recommendation_snapshot'])
        choice = row['choice']
        status = ('Selesai' if row['completed_at'] else
                  'Tidak perlu tindakan' if choice == 'Tidak perlu tindakan' else 'Belum selesai')
        return dict(id=row['id'], session_id=row['session_id'], batch_id=row['batch_id'],
                    physical_condition=row['physical_condition'], choice=choice,
                    target_kind=row['target_kind'], target_code=row['target_code'],
                    reason=row['reason'], officer=row['officer'], decided_at=row['decided_at'],
                    age_at_decision=row['age_at_decision'], aging_status=row['aging_status'],
                    recommendation_code=rec['code'], recommendation_title=rec['title'],
                    recommendation_reason=rec['reason'],
                    recommendation_next_action=rec['next_action'],
                    recommendation_priority=rec['priority'],
                    recommendation_snapshot=rec, action_status=status,
                    completed_at=row['completed_at'], completed_by=row['completed_by'],
                    completion_note=row['completion_note'])

    def for_result(self, session_id, batch_id):
        """Decision for one scan, or None when the officer has not decided."""
        return self._decision('d.session_id=? AND d.batch_id=?', (session_id, batch_id))

    def latest_action_for_batch(self, batch_id):
        """Most recent staff decision for Data Barang and Live."""
        return self._decision('d.batch_id=? ORDER BY d.decided_at DESC,d.id DESC LIMIT 1',
                              (batch_id,))

    def save_decision(self, session_id, batch_id, physical_condition, choice, reason,
                      *, target_kind=None, target_code=None):
        if physical_condition not in CONDITIONS:
            raise ValueError('Kondisi fisik harus Layak, Perlu evaluasi, atau Tidak layak.')
        if choice not in CHOICES:
            raise ValueError('Pilihan tindak lanjut tidak valid.')
        reason = _required(reason, 'Alasan keputusan')
        if choice in ('Perlu dipindahkan', 'Prioritaskan pemakaian',
                      'Pindahkan ke site', 'Tawarkan ke customer') and physical_condition != 'Layak':
            raise ValueError('Barang harus dinyatakan Layak sebelum dipindahkan atau diprioritaskan.')
        required_kind = TARGET_CHOICES.get(choice)
        if required_kind:
            if target_kind != required_kind or not isinstance(target_code, str) or not target_code:
                raise ValueError('Pilih tujuan rekomendasi yang sesuai dengan tindakan.')
        elif target_kind is not None or target_code is not None:
            raise ValueError('Tujuan hanya dapat dipilih untuk relokasi atau penawaran.')
        if self.db.in_transaction:
            raise ValueError('Transaksi data lain masih berjalan. Selesaikan lalu coba lagi.')

        self.db.execute('BEGIN IMMEDIATE')
        try:
            session = self.db.execute('SELECT * FROM check_sessions WHERE id=?',
                                      (session_id,)).fetchone()
            if session is None:
                raise ValueError('Sesi pengecekan tidak ditemukan.')
            if session['status'] != 'Draft':
                raise ValueError('Keputusan hanya dapat dicatat pada sesi Draft.')
            result = self.db.execute('''SELECT 1 FROM check_results
                WHERE session_id=? AND batch_id=?''', (session_id, batch_id)).fetchone()
            if result is None:
                raise ValueError('Scan barang ke sesi ini sebelum mencatat keputusan.')
            existing = self.for_result(session_id, batch_id)
            if existing and existing['completed_at'] is not None:
                raise ValueError('Tindakan ini sudah selesai dan keputusannya tidak dapat diubah.')
            prior_open = self.db.execute('''SELECT d.id FROM recommendation_decisions d
                LEFT JOIN recommendation_completions c ON c.decision_id=d.id
                WHERE d.batch_id=? AND d.choice!='Tidak perlu tindakan'
                  AND c.decision_id IS NULL AND d.id!=? LIMIT 1''',
                (batch_id, existing['id'] if existing else -1)).fetchone()
            if prior_open:
                raise ValueError('Batch ini masih memiliki tindak lanjut yang belum selesai.')

            row = self.db.execute('SELECT * FROM batches WHERE id=?', (batch_id,)).fetchone()
            if row is None:
                raise ValueError('Batch tidak ditemukan di Data Barang.')
            item = dict(row)
            if item['stock'] <= 0:
                raise ValueError('Stok batch sudah habis; tidak ada barang fisik untuk ditindaklanjuti.')
            now = datetime.now().astimezone()
            age, status = aging(item['received_date'], today=now.date(),
                                normal_max=session['normal_max'], age_limit=session['age_limit'])
            context = recommendation_context(self.db, item['material'])
            if not context['sites'] and not context['customers']:
                context = None
            advice = recommend_for(item, normal_max=session['normal_max'],
                                   age_limit=session['age_limit'], today=now.date(),
                                   context=context)
            if required_kind and not any(
                    option['kind'] == target_kind and option['target'] == target_code
                    for option in advice.get('options', ())):
                raise ValueError('Tujuan tidak tersedia dalam rekomendasi barang saat ini.')
            if choice == 'Perlu dipindahkan' and status != 'Melewati batas':
                raise ValueError('Pilihan Perlu dipindahkan hanya untuk barang Melewati batas.')
            values = (physical_condition,choice,target_kind,target_code,reason,session['officer'],
                      now.isoformat(timespec='seconds'),age,status,
                      json.dumps(advice,ensure_ascii=False))
            if existing:
                decision_id = existing['id']
                self.db.execute('''UPDATE recommendation_decisions SET
                    physical_condition=?,choice=?,target_kind=?,target_code=?,reason=?,officer=?,decided_at=?,
                    age_at_decision=?,aging_status=?,recommendation_snapshot=? WHERE id=?''',
                    (*values,decision_id))
            else:
                cursor = self.db.execute('''INSERT INTO recommendation_decisions
                    (session_id,batch_id,physical_condition,choice,target_kind,target_code,reason,officer,decided_at,
                     age_at_decision,aging_status,recommendation_snapshot)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''', (session_id,batch_id,*values))
                decision_id = cursor.lastrowid
            self.db.commit()
            return self._decision('d.id=?', (decision_id,))
        except Exception:
            self.db.rollback()
            raise

    def complete(self, decision_id, officer, note):
        officer = _required(officer, 'Nama / NIK petugas', 100)
        note = _required(note, 'Catatan penyelesaian')
        if type(decision_id) is not int or decision_id <= 0:
            raise ValueError('Keputusan tidak valid.')
        if self.db.in_transaction:
            raise ValueError('Transaksi data lain masih berjalan. Selesaikan lalu coba lagi.')

        self.db.execute('BEGIN IMMEDIATE')
        try:
            action = self._decision('d.id=?', (decision_id,))
            if action is None:
                raise ValueError('Keputusan tidak ditemukan.')
            if action['choice'] == 'Tidak perlu tindakan':
                raise ValueError('Keputusan ini tidak memerlukan penyelesaian.')
            if action['completed_at'] is not None:
                raise ValueError('Tindakan ini sudah diselesaikan.')
            self.db.execute('''INSERT INTO recommendation_completions
                (decision_id,officer,completed_at,note) VALUES(?,?,?,?)''',
                (decision_id,officer,datetime.now().astimezone().isoformat(timespec='seconds'),note))
            self.db.commit()
            return self._decision('d.id=?', (decision_id,))
        except Exception:
            self.db.rollback()
            raise
