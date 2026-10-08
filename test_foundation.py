import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from warehouse.database import SCHEMA_VERSION, connect, seed_demo
from warehouse.domain import aging, location_code
from warehouse.inventory import Inventory


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/"demo.db"
        self.db=connect(self.path)
        seed_demo(self.db,date(2026,9,16))

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_data_distribution_and_references(self):
        rows=Inventory(self.db).list_batches(date(2026,9,16))
        self.assertEqual(len(rows),50)
        self.assertEqual(len({r['id'] for r in rows}),50)
        self.assertEqual([sum(r['status']==s for r in rows) for s in ['Normal','Warning','Melewati batas']],[25,15,10])
        self.assertLess(len({r['material'] for r in rows}),50)
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(),[])
        self.assertEqual(self.db.execute('PRAGMA integrity_check').fetchone()[0],'ok')

    def test_restart_preserves_dates_and_edits(self):
        with self.db:self.db.execute("UPDATE batches SET stock=99 WHERE id='DEMO-0001'")
        before=[tuple(r) for r in self.db.execute('SELECT * FROM batches ORDER BY id')]
        self.db.close()
        self.db=connect(self.path)
        seed_demo(self.db,date(2027,1,1))
        self.assertEqual(before,[tuple(r) for r in self.db.execute('SELECT * FROM batches ORDER BY id')])

    def test_location_and_aging_validation(self):
        self.assertEqual(location_code('A','B03',2,3,1),'A-B03-K02-R03-T01')
        with self.assertRaises(ValueError):location_code('A','B03',0,2,2)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM locations').fetchone()[0], 162)
        with self.assertRaises(ValueError):aging('2027-01-01',date(2026,9,16))
        for value,status in [('2026-08-17','Normal'),('2026-08-16','Warning'),('2026-06-17','Melewati batas')]:
            self.assertEqual(aging(value,date(2026,9,16))[1],status)

    def test_reject_future_schema(self):
        self.db.execute('PRAGMA user_version=99')
        with self.assertRaises(ValueError):connect(self.path)

    def test_foreign_keys_and_stock(self):
        with self.assertRaises(sqlite3.IntegrityError):self.db.execute("UPDATE batches SET location_code='missing' WHERE id='DEMO-0001'")
        with self.assertRaises(sqlite3.IntegrityError):self.db.execute("UPDATE batches SET stock=-1 WHERE id='DEMO-0001'")


class MigrationV4Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'v3.db'
        old = sqlite3.connect(self.path)
        old.executescript('''
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE locations (code TEXT PRIMARY KEY, area TEXT NOT NULL, rack TEXT NOT NULL,
                level INTEGER NOT NULL, position INTEGER NOT NULL);
            CREATE TABLE batches (id TEXT PRIMARY KEY, material TEXT NOT NULL, description TEXT NOT NULL,
                plant TEXT NOT NULL, storage_location TEXT NOT NULL,
                location_code TEXT NOT NULL REFERENCES locations(code), received_date TEXT NOT NULL,
                stock INTEGER NOT NULL);
            CREATE TABLE check_sessions (id INTEGER PRIMARY KEY, officer TEXT NOT NULL,
                area TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
                status TEXT NOT NULL, normal_max INTEGER NOT NULL, age_limit INTEGER NOT NULL,
                note TEXT NOT NULL);
            CREATE TABLE check_results (session_id INTEGER NOT NULL REFERENCES check_sessions(id),
                batch_id TEXT NOT NULL REFERENCES batches(id), checked_at TEXT NOT NULL,
                snapshot TEXT NOT NULL, age INTEGER NOT NULL, status TEXT NOT NULL, note TEXT NOT NULL,
                PRIMARY KEY(session_id,batch_id));
            CREATE TABLE stock_movements (id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES batches(id),
                occurred_on TEXT NOT NULL, recorded_at TEXT NOT NULL, quantity INTEGER NOT NULL,
                stock_before INTEGER NOT NULL, stock_after INTEGER NOT NULL, officer TEXT NOT NULL,
                note TEXT NOT NULL, snapshot TEXT NOT NULL);
            INSERT INTO metadata VALUES ('mode','demo');
            INSERT INTO metadata VALUES ('seed_date','2026-09-16');
            PRAGMA user_version=3;
        ''')
        for level in range(1, 4):
            for position in range(1, 4):
                code = f'A-B01-{level:02d}-{position:02d}'
                old.execute('INSERT INTO locations VALUES(?,?,?,?,?)',
                            (code,'A','B01',level,position))
        old.execute('INSERT INTO locations VALUES(?,?,?,?,?)', ('C-C01-01-01','C','C01',1,1))
        for index in range(10):
            old.execute('INSERT INTO batches VALUES(?,?,?,?,?,?,?,?)',
                        (f'BATCH-{index:02d}','MAT','Sample','BHT','PBHT',
                         f'A-B01-{index%3+1:02d}-{index%3+1:02d}','2026-01-01',index+1))
        old.execute('INSERT INTO batches VALUES(?,?,?,?,?,?,?,?)',
                    ('BATCH-C','MAT','Extra','BHT','PBHT','C-C01-01-01','2026-01-01',5))
        old.execute('INSERT INTO check_sessions VALUES(?,?,?,?,?,?,?,?,?)',
                    (7,'Faiz','A','2026-09-16T10:00:00','2026-09-16T11:00:00','Selesai',30,90,'Selesai'))
        self.old_snapshot = '{"location_code":"A-B01-01-01","stock":5}'
        old.execute('INSERT INTO check_results VALUES(?,?,?,?,?,?,?)',
                    (7,'BATCH-00','2026-09-16T10:03:00',self.old_snapshot,258,'Melewati batas','Catatan'))
        old.execute('INSERT INTO stock_movements VALUES(?,?,?,?,?,?,?,?,?,?)',
                    ('OUT-1','BATCH-00','2026-09-16','2026-09-16T11:00:00',1,5,4,
                     'Faiz','Keluar',self.old_snapshot))
        old.commit()
        old.close()

    def tearDown(self):
        self.temp.cleanup()

    def test_migrates_same_rack_and_keeps_history(self):
        db = connect(self.path)
        try:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
            self.assertEqual(db.execute('SELECT count(*) FROM locations').fetchone()[0], 54)
            self.assertEqual(db.execute('SELECT count(*) FROM batches').fetchone()[0], 11)
            self.assertEqual(db.execute('SELECT count(*) FROM batch_location_migration').fetchone()[0], 11)
            self.assertEqual(db.execute('SELECT snapshot FROM check_results').fetchone()[0], self.old_snapshot)
            self.assertEqual(db.execute('SELECT snapshot FROM stock_movements').fetchone()[0], self.old_snapshot)
            self.assertEqual(db.execute('SELECT stock FROM batches WHERE id=?', ('BATCH-C',)).fetchone()[0], 5)
            rows = db.execute('SELECT old_location_code,new_location_code FROM batch_location_migration').fetchall()
            self.assertTrue(all(tuple(row[0].split('-')[:2]) == tuple(row[1].split('-')[:2]) for row in rows))
            self.assertEqual(db.execute('''SELECT count(DISTINCT "column" || '-' || "row")
                FROM locations l JOIN batches b ON b.location_code=l.code
                WHERE l.area='A' AND l.rack='B01' ''').fetchone()[0], 9)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        finally:
            db.close()
        self.assertEqual(len(list(self.path.parent.glob('v3.db.pre-v3-*.bak'))), 1)
        db = connect(self.path)
        try:
            self.assertEqual(db.execute('SELECT count(*) FROM batch_location_migration').fetchone()[0], 11)
        finally:
            db.close()
        self.assertEqual(len(list(self.path.parent.glob('v3.db.pre-v3-*.bak'))), 1)

    def test_invalid_old_level_rolls_back_and_retains_backup(self):
        old = sqlite3.connect(self.path)
        old.execute('INSERT INTO locations VALUES(?,?,?,?,?)', ('C-C01-04-01','C','C01',4,1))
        old.commit()
        old.close()
        with self.assertRaisesRegex(ValueError, 'di luar 01–03'):
            connect(self.path)
        old = sqlite3.connect(self.path)
        try:
            self.assertEqual(old.execute('PRAGMA user_version').fetchone()[0], 3)
            self.assertEqual(old.execute('SELECT count(*) FROM locations').fetchone()[0], 11)
            self.assertFalse(old.execute("SELECT 1 FROM sqlite_master WHERE name='locations_v4'").fetchone())
        finally:
            old.close()
        self.assertEqual(len(list(self.path.parent.glob('v3.db.pre-v3-*.bak'))), 1)

    def test_genuine_v1_database_upgrades_through_v4(self):
        path = self.path.parent / 'v1.db'
        old = sqlite3.connect(path)
        old.executescript('''
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE locations (code TEXT PRIMARY KEY, area TEXT NOT NULL, rack TEXT NOT NULL,
                level INTEGER NOT NULL, position INTEGER NOT NULL);
            CREATE TABLE batches (id TEXT PRIMARY KEY, material TEXT NOT NULL, description TEXT NOT NULL,
                plant TEXT NOT NULL, storage_location TEXT NOT NULL,
                location_code TEXT NOT NULL REFERENCES locations(code), received_date TEXT NOT NULL,
                stock INTEGER NOT NULL);
            INSERT INTO metadata VALUES ('mode','demo');
            INSERT INTO locations VALUES ('A-B01-01-01','A','B01',1,1);
            INSERT INTO batches VALUES ('LEGACY-1','MAT','Sample','BHT','PBHT','A-B01-01-01','2026-01-01',7);
            PRAGMA user_version=1;
        ''')
        old.close()
        db = connect(path)
        try:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
            self.assertEqual(db.execute('SELECT count(*) FROM locations').fetchone()[0], 27)
            self.assertEqual(db.execute('SELECT stock FROM batches WHERE id=?', ('LEGACY-1',)).fetchone()[0], 7)
            self.assertIsNotNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='check_sessions'").fetchone())
            self.assertIsNotNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='stock_movements'").fetchone())
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        finally:
            db.close()
        self.assertEqual(len(list(self.path.parent.glob('v1.db.pre-v1-*.bak'))), 1)


if __name__=='__main__':unittest.main()
