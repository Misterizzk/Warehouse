"""Atomic stock issues with immutable inventory snapshots and safe retries."""
import json
import re
from datetime import date, datetime
from uuid import UUID, uuid4


def _iso_date(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value.strip()):
        raise ValueError(f'{label} harus tanggal valid YYYY-MM-DD.')
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f'{label} harus tanggal valid YYYY-MM-DD.') from exc


def _operation_id(value):
    if value is None:
        return 'OUT-' + uuid4().hex.upper()
    if not isinstance(value, str) or not value.upper().startswith('OUT-'):
        raise ValueError('ID transaksi barang keluar tidak valid.')
    try:
        parsed = UUID(value[4:])
    except (ValueError, AttributeError) as exc:
        raise ValueError('ID transaksi barang keluar tidak valid.') from exc
    return 'OUT-' + parsed.hex.upper()


class StockMovements:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def _record(row):
        record = dict(row)
        snapshot = json.loads(record['snapshot'])
        record.update(material=snapshot['material'], description=snapshot['description'],
                      location_code=snapshot['location_code'])
        record['snapshot'] = snapshot
        return record

    def get(self, movement_id):
        row = self.db.execute('SELECT * FROM stock_movements WHERE id=?',
                              (_operation_id(movement_id),)).fetchone()
        if row is None:
            raise ValueError('Riwayat barang keluar tidak ditemukan.')
        return self._record(row)

    def list(self, batch_id=None, query=''):
        sql = 'SELECT * FROM stock_movements'
        params = ()
        if batch_id is not None:
            sql += ' WHERE batch_id=?'
            params = (batch_id,)
        rows = self.db.execute(sql + ' ORDER BY recorded_at DESC,rowid DESC', params)
        search = str(query).strip().casefold()
        records = []
        for row in rows:
            record = self._record(row)
            haystack = ' '.join(str(record[key]) for key in
                               ('id', 'batch_id', 'material', 'description', 'location_code',
                                'officer', 'note', 'occurred_on'))
            if search in haystack.casefold():
                records.append(record)
        return records

    def issue(self, batch_id, quantity, occurred_on, officer, note='', operation_id=None):
        if not isinstance(batch_id, str) or not batch_id.strip():
            raise ValueError('Pilih batch barang yang akan dikeluarkan.')
        batch_id = batch_id.strip()
        if isinstance(quantity, str) and re.fullmatch(r'[0-9]{1,9}', quantity.strip()):
            quantity = int(quantity.strip())
        if type(quantity) is not int or not 1 <= quantity <= 999999999:
            raise ValueError('Jumlah keluar harus bilangan bulat 1–999999999.')
        occurred = _iso_date(occurred_on, 'Tanggal keluar')
        if occurred > date.today():
            raise ValueError('Tanggal keluar tidak boleh setelah hari ini.')
        if not isinstance(officer, str) or not 1 <= len(officer.strip()) <= 100:
            raise ValueError('Nama / NIK petugas wajib diisi, maksimal 100 karakter.')
        if not isinstance(note, str) or len(note.strip()) > 2000:
            raise ValueError('Catatan maksimal 2000 karakter.')
        payload = dict(batch_id=batch_id, quantity=quantity, occurred_on=occurred.isoformat(),
                       officer=officer.strip(), note=note.strip())
        movement_id = _operation_id(operation_id)
        if self.db.in_transaction:
            raise ValueError('Transaksi data lain masih berjalan. Selesaikan lalu coba lagi.')

        # Acquire the write lock before reading stock, so a second connection cannot
        # authorize an issue using the same stale stock balance.
        self.db.execute('BEGIN IMMEDIATE')
        try:
            prior = self.db.execute('SELECT * FROM stock_movements WHERE id=?',
                                    (movement_id,)).fetchone()
            if prior is not None:
                if any(prior[key] != value for key, value in payload.items()):
                    raise ValueError('ID transaksi sudah dipakai untuk data yang berbeda. Muat ulang formulir.')
                result = self._record(prior)
                self.db.commit()
                return result
            row = self.db.execute('SELECT * FROM batches WHERE id=?', (batch_id,)).fetchone()
            if row is None:
                raise ValueError('Batch tidak ditemukan. Muat ulang Data Barang.')
            item = dict(row)
            received = _iso_date(item['received_date'], 'Tanggal masuk barang')
            if occurred < received:
                raise ValueError('Tanggal keluar tidak boleh sebelum tanggal masuk barang.')
            stock = item['stock']
            if type(stock) is not int or stock < 0:
                raise ValueError('Stok barang tidak valid. Perbaiki data barang terlebih dahulu.')
            if quantity > stock:
                raise ValueError(f'Jumlah keluar melebihi stok tersedia ({stock}). Muat ulang data barang.')
            after = stock - quantity
            record = dict(payload, id=movement_id, stock_before=stock, stock_after=after,
                          recorded_at=datetime.now().astimezone().isoformat(timespec='microseconds'),
                          snapshot=json.dumps(item, ensure_ascii=False))
            self.db.execute('UPDATE batches SET stock=? WHERE id=?', (after, batch_id))
            self.db.execute('''INSERT INTO stock_movements
                (id,batch_id,occurred_on,recorded_at,quantity,stock_before,stock_after,officer,note,snapshot)
                VALUES (:id,:batch_id,:occurred_on,:recorded_at,:quantity,:stock_before,:stock_after,:officer,:note,:snapshot)''',
                record)
            self.db.commit()
            return self._record(record)
        except Exception:
            self.db.rollback()
            raise
