import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from warehouse.database import SCHEMA_VERSION, connect, seed_demo
from warehouse.dashboard import overview
from warehouse.inventory import Inventory
from warehouse.sessions import Sessions
from warehouse.stock_movements import StockMovements


class StockMovementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'demo.db'
        self.db = connect(self.path)
        seed_demo(self.db)
        self.service = StockMovements(self.db)
        self.batch = 'DEMO-0002'  # Four units, received yesterday.
        self.today = date.today().isoformat()

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def balance(self):
        return self.db.execute('SELECT stock FROM batches WHERE id=?', (self.batch,)).fetchone()[0]

    def issue(self, quantity=1, **kwargs):
        return self.service.issue(self.batch, quantity, kwargs.pop('occurred_on', self.today),
                                  kwargs.pop('officer', 'Faiz'), **kwargs)

    def test_partial_and_full_issue_keep_batch_and_update_dashboard(self):
        before = overview(self.db)
        partial = self.issue('2', note='Pindah ke produksi')
        self.assertEqual((partial['quantity'], partial['stock_before'], partial['stock_after']), (2, 4, 2))
        self.assertIsNotNone(datetime.fromisoformat(partial['recorded_at']).tzinfo)
        self.assertEqual(self.balance(), 2)
        after_partial = overview(self.db)
        self.assertEqual(len(before['active']), len(after_partial['active']))
        full = self.issue(2)
        self.assertEqual(self.balance(), 0)
        after = overview(self.db)
        self.assertEqual(after['total_stock'], before['total_stock'] - 4)
        self.assertEqual(len(after['active']), len(before['active']) - 1)
        self.assertEqual(after['counts']['Normal'], before['counts']['Normal'] - 1)
        self.assertEqual(after['zero_stock'], before['zero_stock'] + 1)
        self.assertEqual(len(Inventory(self.db).list_batches()), 50)
        self.assertEqual([r['id'] for r in self.service.list(self.batch)], [full['id'], partial['id']])

    def test_invalid_fields_cannot_write_stock_or_history(self):
        for quantity in (True, False, 1.0, 1.5, None, 0, -1, 5, 1000000000, '1.0', '1e0', 'abc'):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                self.issue(quantity)
        for values in ({'officer': ''}, {'officer': None}, {'officer': 'a'*101},
                       {'note': 'a'*2001}, {'note': None}, {'occurred_on': '2026-02-30'},
                       {'occurred_on': '20260922'}, {'occurred_on': None},
                       {'occurred_on': (date.today()+timedelta(days=1)).isoformat()},
                       {'occurred_on': (date.today()-timedelta(days=2)).isoformat()},
                       {'operation_id': 'OUT-bad'}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.issue(**values)
        with self.assertRaisesRegex(ValueError, 'Batch tidak ditemukan'):
            self.service.issue('missing', 1, self.today, 'Faiz')
        self.assertEqual(self.balance(), 4)
        self.assertEqual(self.service.list(), [])

    def test_malformed_master_date_and_insert_failure_roll_back(self):
        with self.db:
            self.db.execute('UPDATE batches SET received_date=? WHERE id=?', ('bad', self.batch))
        with self.assertRaisesRegex(ValueError, 'Tanggal masuk barang'):
            self.issue()
        self.assertEqual(self.balance(), 4)
        with self.db:
            self.db.execute('UPDATE batches SET received_date=? WHERE id=?', (self.today, self.batch))
            self.db.execute("""CREATE TRIGGER reject_test_movement BEFORE INSERT ON stock_movements
                BEGIN SELECT RAISE(ABORT,'simulated write failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.issue()
        self.assertEqual(self.balance(), 4)
        self.assertEqual(self.service.list(), [])

    def test_immutable_history_and_reports_after_master_edit(self):
        sessions = Sessions(self.db)
        session = sessions.start('Petugas', 'A')
        sessions.add_code(session, self.batch)
        sessions.finish(session)
        report = sessions.results(session)
        movement = self.issue(2)
        original = Inventory(self.db).list_batches(query=self.batch)[0]
        Inventory(self.db).update(self.batch, dict(original, material='NEW-MATERIAL',
            description='Deskripsi baru', location_code='B-B03-K03-R01-T03', stock='99'))
        self.assertEqual(self.service.get(movement['id']), movement)
        self.assertEqual(self.service.list(query=movement['material'])[0], movement)
        self.assertEqual(self.service.list(query='NEW-MATERIAL'), [])
        self.assertEqual(sessions.results(session), report)
        for sql in ('UPDATE stock_movements SET note=? WHERE id=?',
                    'DELETE FROM stock_movements WHERE note=? AND id=?'):
            with self.assertRaises(sqlite3.IntegrityError), self.db:
                self.db.execute(sql, ('', movement['id']))
        self.assertEqual(self.service.get(movement['id']), movement)

    def test_retry_same_normalized_payload_is_idempotent_even_after_master_change(self):
        operation = 'OUT-' + uuid4().hex
        first = self.issue('4', operation_id=operation, officer=' Faiz ', note=' produksi ')
        self.assertEqual(self.issue(4, operation_id=operation.upper(), note='produksi'), first)
        with self.db:
            self.db.execute('UPDATE batches SET received_date=? WHERE id=?', ('bad', self.batch))
        self.assertEqual(self.issue(4, operation_id=operation, note='produksi'), first)
        for changes in ({'quantity': 3}, {'officer': 'Other'}, {'note': 'new'}):
            payload = dict(quantity=4, note='produksi', operation_id=operation)
            payload.update(changes)
            with self.assertRaisesRegex(ValueError, 'data yang berbeda'):
                self.issue(**payload)
        self.assertEqual(self.balance(), 0)
        self.assertEqual(len(self.service.list()), 1)

    def test_reopen_and_v2_migration_preserve_inventory_and_reports(self):
        # Build an actual v2 file: old four-part location columns, inventory,
        # and a completed report, but no stock movement table yet.
        self.db.close()
        self.path = Path(self.temp.name) / 'legacy-v2.db'
        legacy = sqlite3.connect(self.path)
        legacy.row_factory = sqlite3.Row
        try:
            legacy.executescript('''
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE locations (
                    code TEXT PRIMARY KEY, area TEXT NOT NULL, rack TEXT NOT NULL,
                    level INTEGER NOT NULL CHECK(level BETWEEN 1 AND 99),
                    position INTEGER NOT NULL CHECK(position BETWEEN 1 AND 99),
                    UNIQUE(area,rack,level,position));
                CREATE TABLE batches (
                    id TEXT PRIMARY KEY, material TEXT NOT NULL CHECK(length(trim(material))>0),
                    description TEXT NOT NULL, plant TEXT NOT NULL, storage_location TEXT NOT NULL,
                    location_code TEXT NOT NULL REFERENCES locations(code),
                    received_date TEXT NOT NULL, stock INTEGER NOT NULL CHECK(stock>=0));
                CREATE INDEX batches_location ON batches(location_code);
                CREATE TABLE check_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    officer TEXT NOT NULL CHECK(length(trim(officer)) BETWEEN 1 AND 100),
                    area TEXT NOT NULL CHECK(length(trim(area)) BETWEEN 1 AND 100),
                    started_at TEXT NOT NULL, finished_at TEXT,
                    status TEXT NOT NULL DEFAULT 'Draft' CHECK(status IN ('Draft','Selesai')),
                    normal_max INTEGER NOT NULL CHECK(normal_max>=0),
                    age_limit INTEGER NOT NULL CHECK(age_limit>normal_max),
                    note TEXT NOT NULL DEFAULT '',
                    CHECK((status='Draft' AND finished_at IS NULL) OR
                          (status='Selesai' AND finished_at IS NOT NULL)));
                CREATE TABLE check_results (
                    session_id INTEGER NOT NULL REFERENCES check_sessions(id),
                    batch_id TEXT NOT NULL REFERENCES batches(id),
                    checked_at TEXT NOT NULL, snapshot TEXT NOT NULL,
                    age INTEGER NOT NULL CHECK(age>=0),
                    status TEXT NOT NULL CHECK(status IN ('Normal','Warning','Melewati batas')),
                    note TEXT NOT NULL DEFAULT '', PRIMARY KEY(session_id,batch_id));
                CREATE TRIGGER locked_session_update BEFORE UPDATE ON check_sessions
                    WHEN OLD.status='Selesai' BEGIN SELECT RAISE(ABORT,'Sesi sudah terkunci'); END;
                CREATE TRIGGER locked_session_delete BEFORE DELETE ON check_sessions
                    WHEN OLD.status='Selesai' BEGIN SELECT RAISE(ABORT,'Sesi sudah terkunci'); END;
                CREATE TRIGGER locked_result_insert BEFORE INSERT ON check_results
                    WHEN (SELECT status FROM check_sessions WHERE id=NEW.session_id)='Selesai'
                    BEGIN SELECT RAISE(ABORT,'Sesi sudah terkunci'); END;
                CREATE TRIGGER locked_result_update BEFORE UPDATE ON check_results
                    WHEN (SELECT status FROM check_sessions WHERE id=OLD.session_id)='Selesai'
                      OR (SELECT status FROM check_sessions WHERE id=NEW.session_id)='Selesai'
                    BEGIN SELECT RAISE(ABORT,'Sesi sudah terkunci'); END;
                CREATE TRIGGER locked_result_delete BEFORE DELETE ON check_results
                    WHEN (SELECT status FROM check_sessions WHERE id=OLD.session_id)='Selesai'
                    BEGIN SELECT RAISE(ABORT,'Sesi sudah terkunci'); END;
                CREATE TRIGGER finish_requires_results BEFORE UPDATE OF status ON check_sessions
                    WHEN NEW.status='Selesai' AND NOT EXISTS(
                        SELECT 1 FROM check_results WHERE session_id=OLD.id)
                    BEGIN SELECT RAISE(ABORT,'Sesi kosong belum dapat diselesaikan'); END;
                INSERT INTO metadata VALUES ('mode','demo');
                INSERT INTO locations VALUES ('A-B01-01-01','A','B01',1,1);
                PRAGMA user_version=2;
            ''')
            received = (date.today() - timedelta(days=1)).isoformat()
            legacy.execute('INSERT INTO batches VALUES(?,?,?,?,?,?,?,?)',
                           (self.batch, 'MAT-002', 'Lamp Assy', 'BHT', 'PBHT',
                            'A-B01-01-01', received, 4))
            session = legacy.execute('''INSERT INTO check_sessions
                (officer,area,started_at,normal_max,age_limit) VALUES(?,?,?,?,?)''',
                ('Faiz', 'A', f'{self.today}T09:00:00', 30, 90)).lastrowid
            snapshot = json.dumps(dict(id=self.batch, material='MAT-002',
                description='Lamp Assy', plant='BHT', storage_location='PBHT',
                location_code='A-B01-01-01', received_date=received, stock=4))
            legacy.execute('''INSERT INTO check_results
                (session_id,batch_id,checked_at,snapshot,age,status,note)
                VALUES(?,?,?,?,?,?,?)''',
                (session, self.batch, f'{self.today}T09:01:00', snapshot, 1, 'Normal', 'Checked'))
            legacy.execute('''UPDATE check_sessions SET status='Selesai',finished_at=? WHERE id=?''',
                           (f'{self.today}T09:02:00', session))
            legacy.commit()
            before_inventory = [tuple(row) for row in legacy.execute('''SELECT id,material,description,
                plant,storage_location,received_date,stock FROM batches ORDER BY id''')]
            before_report = Sessions(legacy).results(session)
        finally:
            legacy.close()
        self.db = connect(self.path)
        self.service = StockMovements(self.db)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
        self.assertEqual(before_inventory, [tuple(row) for row in self.db.execute('''SELECT id,material,
            description,plant,storage_location,received_date,stock FROM batches ORDER BY id''')])
        self.assertEqual(before_report, Sessions(self.db).results(session))
        mapped = self.db.execute('''SELECT old_location_code,new_location_code
            FROM batch_location_migration WHERE batch_id=?''', (self.batch,)).fetchone()
        self.assertEqual(mapped['old_location_code'], 'A-B01-01-01')
        self.assertTrue(mapped['new_location_code'].startswith('A-B01-K'))
        movement = self.issue()
        self.db.close()
        self.db = connect(self.path)
        self.service = StockMovements(self.db)
        self.assertEqual(self.service.get(movement['id']), movement)
        self.assertEqual(self.balance(), 3)
        with self.assertRaises(sqlite3.IntegrityError), self.db:
            self.db.execute('UPDATE check_results SET note=? WHERE session_id=?', ('changed', session))
        self.assertEqual(self.db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(len(list(self.path.parent.glob('legacy-v2.db.pre-v2-*.bak'))), 1)

    def test_concurrent_connections_cannot_overdraw(self):
        barrier = threading.Barrier(2)
        def attempt():
            db = connect(self.path)
            try:
                barrier.wait(timeout=5)
                return StockMovements(db).issue(self.batch, 3, self.today, 'Faiz')
            except ValueError as exc:
                return str(exc)
            finally:
                db.close()
        with ThreadPoolExecutor(max_workers=2) as executor:
            tasks = [executor.submit(attempt) for _ in range(2)]
            results = [task.result(timeout=10) for task in tasks]
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertEqual(self.balance(), 1)
        self.assertEqual(len(self.service.list()), 1)

    def test_concurrent_same_operation_records_only_once(self):
        barrier = threading.Barrier(2)
        operation = 'OUT-' + uuid4().hex.upper()
        def attempt():
            db = connect(self.path)
            try:
                barrier.wait(timeout=5)
                return StockMovements(db).issue(self.batch, 4, self.today, 'Faiz', operation_id=operation)
            finally:
                db.close()
        with ThreadPoolExecutor(max_workers=2) as executor:
            tasks = [executor.submit(attempt) for _ in range(2)]
            results = [task.result(timeout=10) for task in tasks]
        self.assertEqual(results[0], results[1])
        self.assertEqual(self.balance(), 0)
        self.assertEqual(len(self.service.list()), 1)

    def test_database_constraints_and_callers_transaction_are_preserved(self):
        good = self.issue()
        raw = dict(good, id='OUT-' + uuid4().hex.upper(), snapshot=json.dumps(good['snapshot']))
        for changes in ({'quantity': 0}, {'quantity': 0.5}, {'stock_after': -1},
                        {'stock_before': 99}, {'officer': ''}, {'note': 'x'*2001},
                        {'snapshot': 'invalid'}):
            values = dict(raw, **changes)
            with self.assertRaises(sqlite3.IntegrityError), self.db:
                self.db.execute('''INSERT INTO stock_movements
                    (id,batch_id,occurred_on,recorded_at,quantity,stock_before,stock_after,officer,note,snapshot)
                    VALUES (:id,:batch_id,:occurred_on,:recorded_at,:quantity,:stock_before,:stock_after,:officer,:note,:snapshot)''', values)
        self.db.execute('UPDATE batches SET description=? WHERE id=?', ('pending edit', self.batch))
        with self.assertRaisesRegex(ValueError, 'Transaksi data lain'):
            self.issue()
        self.assertTrue(self.db.in_transaction)
        self.assertEqual(self.db.execute('SELECT description FROM batches WHERE id=?', (self.batch,)).fetchone()[0], 'pending edit')
        self.db.rollback()
        self.assertEqual(self.balance(), 3)


if __name__ == '__main__':
    unittest.main()
