"""Recommendation context is explicit demo data and survives release packaging."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.build_windows import create_clean_install_database
from warehouse.database import connect
from warehouse.recommendation_data import recommendation_context


class RecommendationDataTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='warehouse-recommendation-data-')
        self.path = Path(self.folder.name) / 'demo.db'
        self.db = connect(self.path)

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    def test_material_context_joins_only_compatible_customer_units(self):
        # This catches a missing material/unit join and accidental cross-material advice.
        with self.db:
            self.db.executemany('''INSERT INTO site_demand
                (material,site,demand_prev,demand_now,open_demand,site_stock)
                VALUES(?,?,?,?,?,?)''', [
                    ('M-01','C',2,9,7,1), ('M-01','A',4,8,5,2),
                    ('OTHER','B',0,100,100,0),
                ])
            self.db.executemany('INSERT INTO material_unit_compatibility VALUES(?,?)', [
                ('M-01','UNIT-TRUCK'), ('OTHER','UNIT-EXCAVATOR'),
            ])
            self.db.executemany('INSERT INTO customer_demand VALUES(?,?,?)', [
                ('B','UNIT-TRUCK',3), ('A','UNIT-TRUCK',6),
                ('C','UNIT-EXCAVATOR',99),
            ])
        self.assertEqual(recommendation_context(self.db, 'M-01'), {
            'sites': [
                {'site':'A','demand_prev':4,'demand_now':8,'open_demand':5,'site_stock':2},
                {'site':'C','demand_prev':2,'demand_now':9,'open_demand':7,'site_stock':1},
            ],
            'customers': [
                {'customer':'A','unit_model':'UNIT-TRUCK','open_demand':6},
                {'customer':'B','unit_model':'UNIT-TRUCK','open_demand':3},
            ],
            'source':'Simulasi',
        })

    def test_unmapped_material_gets_no_fabricated_destination(self):
        # A newly imported material must not inherit unrelated demo demand.
        with self.db:
            self.db.execute('INSERT INTO site_demand VALUES(?,?,?,?,?,?)', ('M-01','A',2,8,6,1))
        self.assertEqual(recommendation_context(self.db, 'NEW-MATERIAL'),
                         {'sites': [], 'customers': [], 'source':'Simulasi'})

    def test_version_five_migration_preserves_existing_batch_and_decision(self):
        # A schema upgrade must keep staff history and existing inventory intact.
        with self.db:
            self.db.execute('INSERT INTO locations VALUES(?,?,?,?,?,?)',
                            ('A-B01-K01-R01-T01','A','B01',1,1,1))
            self.db.execute('INSERT INTO batches VALUES(?,?,?,?,?,?,?,?)',
                            ('BAT-OLD','M-OLD','Sample','BHT','PBHT','A-B01-K01-R01-T01','2026-01-01',7))
            self.db.execute('''INSERT INTO check_sessions
                (id,officer,area,started_at,status,normal_max,age_limit,note)
                VALUES(1,'Petugas lama','A','2026-02-01T10:00:00','Draft',30,90,'Tetap')''')
            self.db.execute('''INSERT INTO check_results
                (session_id,batch_id,checked_at,snapshot,age,status,note)
                VALUES(1,'BAT-OLD','2026-02-01T10:01:00','{}',31,'Warning','Tercatat')''')
            for table in ('site_demand','material_unit_compatibility','customer_demand'):
                self.db.execute(f'DROP TABLE IF EXISTS {table}')
            self.db.execute('PRAGMA user_version=5')
        self.db.close()
        self.db = connect(self.path)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0], 7)
        self.assertEqual(self.db.execute('SELECT stock FROM batches WHERE id=?', ('BAT-OLD',)).fetchone()[0], 7)
        self.assertEqual(self.db.execute('SELECT note FROM check_results').fetchone()[0], 'Tercatat')
        self.assertEqual(recommendation_context(self.db, 'M-OLD'),
                         {'sites': [], 'customers': [], 'source':'Simulasi'})
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(len(list(self.path.parent.glob('demo.db.pre-v5-*.bak'))), 1)

    def test_clean_package_keeps_scenarios_without_staff_history(self):
        # This catches a release that silently drops the recommendations' evidence.
        with self.db:
            self.db.execute('INSERT INTO site_demand VALUES(?,?,?,?,?,?)', ('M-01','B',3,12,9,1))
            self.db.execute('INSERT INTO material_unit_compatibility VALUES(?,?)', ('M-01','UNIT-X'))
            self.db.execute('INSERT INTO customer_demand VALUES(?,?,?)', ('C','UNIT-X',4))
            self.db.execute('''INSERT INTO check_sessions
                (id,officer,area,started_at,status,normal_max,age_limit,note)
                VALUES(1,'Petugas demo','A','2026-02-01T10:00:00','Draft',30,90,'Pribadi')''')
        target = self.path.parent / 'clean.db'
        create_clean_install_database(self.path, target)
        copied = connect(target)
        try:
            self.assertEqual(recommendation_context(copied, 'M-01'), {
                'sites':[{'site':'B','demand_prev':3,'demand_now':12,'open_demand':9,'site_stock':1}],
                'customers':[{'customer':'C','unit_model':'UNIT-X','open_demand':4}],
                'source':'Simulasi',
            })
            self.assertEqual(copied.execute('SELECT COUNT(*) FROM check_sessions').fetchone()[0], 0)
        finally:
            copied.close()

    def test_v6_decisions_migrate_with_completions_and_new_target_choices(self):
        # Rebuilding the CHECK-constrained table must retain old IDs and FK history.
        legacy_path = self.path.parent / 'legacy-v6.db'
        old = sqlite3.connect(legacy_path)
        old.executescript('''
            PRAGMA foreign_keys=ON;
            CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            INSERT INTO metadata VALUES('mode','demo');
            CREATE TABLE check_sessions(id INTEGER PRIMARY KEY,status TEXT NOT NULL);
            CREATE TABLE batches(id TEXT PRIMARY KEY);
            CREATE TABLE check_results(session_id INTEGER NOT NULL REFERENCES check_sessions(id),
                batch_id TEXT NOT NULL REFERENCES batches(id),PRIMARY KEY(session_id,batch_id));
            CREATE TABLE recommendation_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,batch_id TEXT NOT NULL,
                physical_condition TEXT NOT NULL CHECK(physical_condition IN
                    ('Layak','Perlu evaluasi','Tidak layak')),
                choice TEXT NOT NULL CHECK(choice IN
                    ('Perlu dipindahkan','Prioritaskan pemakaian','Tunda evaluasi','Tidak perlu tindakan')),
                reason TEXT NOT NULL,officer TEXT NOT NULL,decided_at TEXT NOT NULL,
                age_at_decision INTEGER NOT NULL,aging_status TEXT NOT NULL,
                recommendation_snapshot TEXT NOT NULL,
                UNIQUE(session_id,batch_id),
                FOREIGN KEY(session_id,batch_id) REFERENCES check_results(session_id,batch_id));
            CREATE INDEX recommendation_decisions_batch
                ON recommendation_decisions(batch_id,decided_at DESC,id DESC);
            CREATE TABLE recommendation_completions (
                decision_id INTEGER PRIMARY KEY REFERENCES recommendation_decisions(id),
                officer TEXT NOT NULL,completed_at TEXT NOT NULL,note TEXT NOT NULL);
            CREATE TRIGGER recommendation_draft_insert BEFORE INSERT ON recommendation_decisions
                WHEN (SELECT status FROM check_sessions WHERE id=NEW.session_id)!='Draft'
                BEGIN SELECT RAISE(ABORT,'Keputusan hanya dapat dibuat pada sesi Draft'); END;
            CREATE TRIGGER locked_recommendation_decision_update BEFORE UPDATE ON recommendation_decisions
                WHEN (SELECT status FROM check_sessions WHERE id=OLD.session_id)!='Draft'
                  OR NEW.id!=OLD.id OR NEW.session_id!=OLD.session_id OR NEW.batch_id!=OLD.batch_id
                  OR EXISTS(SELECT 1 FROM recommendation_completions WHERE decision_id=OLD.id)
                BEGIN SELECT RAISE(ABORT,'Keputusan sesi selesai atau tindakan tuntas tidak dapat diubah'); END;
            CREATE TRIGGER locked_recommendation_decision_delete BEFORE DELETE ON recommendation_decisions
                BEGIN SELECT RAISE(ABORT,'Keputusan tidak dapat dihapus'); END;
            INSERT INTO check_sessions VALUES(1,'Draft');
            INSERT INTO batches VALUES('BAT-OLD');
            INSERT INTO batches VALUES('BAT-NEW');
            INSERT INTO check_results VALUES(1,'BAT-OLD');
            INSERT INTO check_results VALUES(1,'BAT-NEW');
            INSERT INTO recommendation_decisions
                (id,session_id,batch_id,physical_condition,choice,reason,officer,
                 decided_at,age_at_decision,aging_status,recommendation_snapshot)
                VALUES(42,1,'BAT-OLD','Layak','Perlu dipindahkan','Keputusan lama','Petugas lama',
                       '2026-09-01T10:00:00',120,'Melewati batas','{}');
            INSERT INTO recommendation_completions VALUES
                (42,'Petugas lama','2026-09-02T10:00:00','Selesai lama');
            PRAGMA user_version=6;
        ''')
        old.close()

        upgraded = connect(legacy_path)
        try:
            self.assertEqual(upgraded.execute('PRAGMA user_version').fetchone()[0], 7)
            previous = upgraded.execute('''SELECT id,choice,target_kind,target_code
                FROM recommendation_decisions WHERE id=42''').fetchone()
            self.assertEqual(tuple(previous), (42,'Perlu dipindahkan',None,None))
            completion = upgraded.execute('''SELECT officer,note
                FROM recommendation_completions WHERE decision_id=42''').fetchone()
            self.assertEqual(tuple(completion), ('Petugas lama','Selesai lama'))
            upgraded.execute('''INSERT INTO recommendation_decisions
                (session_id,batch_id,physical_condition,choice,target_kind,target_code,
                 reason,officer,decided_at,age_at_decision,aging_status,recommendation_snapshot)
                VALUES(1,'BAT-NEW','Layak','Tawarkan ke customer','customer','A',
                       'Cocok dengan unit','Petugas baru','2026-09-30T10:00:00',95,
                       'Melewati batas','{}')''')
            with self.assertRaises(sqlite3.IntegrityError):
                upgraded.execute('''UPDATE recommendation_decisions
                    SET target_kind='site' WHERE batch_id='BAT-NEW' ''')
            with self.assertRaises(sqlite3.IntegrityError):
                upgraded.execute('''UPDATE recommendation_decisions
                    SET reason='Ubah lama' WHERE id=42''')
            self.assertEqual(upgraded.execute('PRAGMA foreign_key_check').fetchall(), [])
        finally:
            upgraded.close()
        self.assertEqual(len(list(self.path.parent.glob('legacy-v6.db.pre-v6-*.bak'))), 1)


if __name__ == '__main__':
    unittest.main()
