import sqlite3
import tempfile
import unittest
from datetime import date,timedelta
from pathlib import Path
from warehouse.database import connect,seed_demo,SCHEMA_VERSION
from warehouse.sessions import Sessions
from warehouse.inventory import Inventory


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'demo.db'
        self.db=connect(self.path)
        seed_demo(self.db)
        self.service=Sessions(self.db)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_draft_restart_notes_duplicate_and_lock(self):
        key=self.service.start('Faiz','Area A',30,90)
        self.assertTrue(self.service.add_code(key,'ID:DEMO-0001')[1])
        original=self.service.results(key)[0]
        self.service.save_note(key,'Cek label rak')
        self.service.save_note(key,'Kemasan perlu diperiksa','DEMO-0001')
        self.db.close()
        self.db=connect(self.path)
        self.service=Sessions(self.db)
        self.assertEqual(self.service.get(key)['note'],'Cek label rak')
        self.assertFalse(self.service.add_code(key,'DEMO-0001')[1])
        self.assertEqual(self.service.results(key)[0]['checked_at'],original['checked_at'])
        self.assertEqual(self.service.results(key)[0]['note'],'Kemasan perlu diperiksa')
        self.service.finish(key)
        for operation in [lambda:self.service.add_code(key,'DEMO-0002'),lambda:self.service.save_note(key,'x'),
                          lambda:self.service.save_note(key,'x','DEMO-0001'),lambda:self.service.finish(key)]:
            with self.assertRaises(ValueError):operation()
        with self.assertRaises(sqlite3.IntegrityError),self.db:
            self.db.execute("UPDATE check_results SET note='changed' WHERE session_id=?",(key,))
        with self.assertRaises(sqlite3.IntegrityError),self.db:
            self.db.execute("UPDATE check_sessions SET status='Draft',finished_at=NULL WHERE id=?",(key,))

    def test_snapshots_and_custom_thresholds(self):
        item=Inventory(self.db).list_batches()[0]
        Inventory(self.db).update(item['id'],dict(item,received_date=(date.today()-timedelta(days=10)).isoformat()))
        key=self.service.start('Petugas','A',3,7)
        self.service.add_code(key,item['id'])
        before=self.service.results(key)
        self.assertEqual(before[0]['status'],'Melewati batas')
        Inventory(self.db).update(item['id'],dict(item,description='Changed',stock='99',location_code='B-B03-K03-R01-T03'))
        self.assertEqual(before,self.service.results(key))
        self.service.finish(key)
        self.assertEqual(before,self.service.results(key))

    def test_invalid_and_empty_finish(self):
        for args in [('', 'A'),('Faiz',''),('Faiz','A',90,30),('Faiz','A','1.5',90)]:
            with self.assertRaises(ValueError):self.service.start(*args)
        key=self.service.start('Faiz','A')
        with self.assertRaises(ValueError):self.service.finish(key)
        for code in ('','missing','MAT-001','ID:missing'):
            with self.assertRaises(ValueError):self.service.add_code(key,code)
        self.assertEqual(self.service.results(key),[])
        with self.assertRaises(ValueError):self.service.save_note(key,'a'*2001)

    def test_v1_migration_preserves_inventory(self):
        # A real v1 fixture has the four-part location schema. Merely changing
        # user_version on a v4 file cannot exercise the migration path.
        self.db.close()
        self.path=Path(self.temp.name)/'legacy-v1.db'
        legacy=sqlite3.connect(self.path)
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
                INSERT INTO metadata VALUES ('mode','demo');
                INSERT INTO locations VALUES ('A-B01-01-01','A','B01',1,1);
                INSERT INTO locations VALUES ('A-B01-03-02','A','B01',3,2);
                INSERT INTO locations VALUES ('B-B02-01-01','B','B02',1,1);
                INSERT INTO batches VALUES
                    ('LEGACY-1','MAT-001','Lamp Assy','BHT','PBHT','A-B01-01-01','2026-01-01',7);
                INSERT INTO batches VALUES
                    ('LEGACY-2','MAT-002','Valve Body','BHT','PBHT','A-B01-03-02','2026-02-01',3);
                PRAGMA user_version=1;
            ''')
            before=[tuple(row) for row in legacy.execute('''SELECT id,material,description,plant,
                storage_location,received_date,stock FROM batches ORDER BY id''')]
        finally:
            legacy.close()
        self.db=connect(self.path)
        self.service=Sessions(self.db)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],SCHEMA_VERSION)
        self.assertEqual(before,[tuple(row) for row in self.db.execute('''SELECT id,material,description,plant,
            storage_location,received_date,stock FROM batches ORDER BY id''')])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM locations').fetchone()[0],54)
        mapping=[tuple(row) for row in self.db.execute('''SELECT batch_id,old_location_code,new_location_code
            FROM batch_location_migration ORDER BY batch_id''')]
        self.assertEqual([row[:2] for row in mapping],
                         [('LEGACY-1','A-B01-01-01'),('LEGACY-2','A-B01-03-02')])
        self.assertTrue(all(row[2].startswith('A-B01-K') for row in mapping))
        session=self.service.start('Faiz','A')
        self.assertEqual(self.service.add_code(session,'ID:LEGACY-1')[0],'LEGACY-1')
        self.service.finish(session)
        self.assertEqual(self.service.results(session)[0]['id'],'LEGACY-1')
        self.assertEqual(self.db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(),[])
        self.assertEqual(len(list(self.path.parent.glob('legacy-v1.db.pre-v1-*.bak'))),1)


if __name__=='__main__':unittest.main()
