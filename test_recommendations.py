"""Behavioral tests for aging advice and staff follow-up decisions."""
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from warehouse.database import SCHEMA_VERSION, connect, seed_demo
from warehouse.inventory import Inventory
from warehouse.recommendations import RecommendationService, recommend_for
from warehouse.sessions import Sessions


class AgingRecommendationTests(unittest.TestCase):
    def test_advice_is_recomputed_from_age_and_respects_zero_stock(self):
        today = date(2026, 9, 29)
        item = dict(received_date='2026-06-15', stock=4)
        over = recommend_for(item, today=today)
        self.assertEqual(over['code'], 'MELEWATI_BATAS')
        self.assertEqual(over['priority'], 3)
        self.assertIn('pemeriksaan fisik', over['next_action'].lower())
        self.assertIn('site lain', over['next_action'].lower())

        item['received_date'] = (today - timedelta(days=89)).isoformat()
        self.assertEqual(recommend_for(item, today=today)['code'], 'WARNING')
        item['received_date'] = (today - timedelta(days=10)).isoformat()
        self.assertEqual(recommend_for(item, today=today)['code'], 'NORMAL')
        item['stock'] = 0
        self.assertEqual(recommend_for(item, today=today)['code'], 'STOK_HABIS')
        self.assertEqual(recommend_for(item, today=today)['priority'], 0)

    def test_session_limits_change_advice(self):
        item = dict(received_date='2026-09-19', stock=1)
        self.assertEqual(recommend_for(item, today=date(2026, 9, 29))['code'], 'NORMAL')
        self.assertEqual(recommend_for(item, normal_max=3, age_limit=7,
                                       today=date(2026, 9, 29))['code'], 'MELEWATI_BATAS')


class RecommendationDecisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'demo.db'
        self.db = connect(self.path)
        seed_demo(self.db)
        self.sessions = Sessions(self.db)
        self.service = RecommendationService(self.db)
        self.batch_id = 'DEMO-0041'
        self.session_id = self.sessions.start('Petugas Contoh', 'Area A')
        self.sessions.add_code(self.session_id, self.batch_id)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_decision_snapshot_and_completion_survive_finished_session(self):
        decision = self.service.save_decision(self.session_id, self.batch_id,
            'Layak', 'Perlu dipindahkan', 'Kondisi kemasan baik; usulkan pengecekan kebutuhan site lain.')
        self.assertEqual(decision['action_status'], 'Belum selesai')
        self.assertEqual(decision['recommendation_code'], 'MELEWATI_BATAS')
        self.assertEqual(decision['officer'], 'Petugas Contoh')
        self.assertIsNone(decision['completed_at'])
        original_advice = decision['recommendation_next_action']
        original_age = decision['age_at_decision']

        self.sessions.finish(self.session_id)
        row = Inventory(self.db).list_batches(query=self.batch_id)[0]
        Inventory(self.db).update(self.batch_id, dict(row, received_date=date.today().isoformat(), stock='8'))
        self.assertEqual(self.service.for_result(self.session_id, self.batch_id)['recommendation_next_action'], original_advice)
        self.assertEqual(self.service.for_result(self.session_id, self.batch_id)['age_at_decision'], original_age)

        done = self.service.complete(decision['id'], 'Petugas Lanjutan', 'Pemindahan selesai; stok dicatat terpisah.')
        self.assertEqual(done['action_status'], 'Selesai')
        self.assertEqual(done['completed_by'], 'Petugas Lanjutan')
        self.assertEqual(self.service.latest_action_for_batch(self.batch_id)['id'], decision['id'])
        self.assertEqual(self.db.execute('SELECT stock FROM batches WHERE id=?', (self.batch_id,)).fetchone()[0], 8)
        self.db.close()
        self.db = connect(self.path)
        self.service = RecommendationService(self.db)
        self.assertEqual(self.service.latest_action_for_batch(self.batch_id)['action_status'], 'Selesai')

    def test_decision_requires_scan_draft_and_valid_physical_assessment(self):
        with self.assertRaises(ValueError):
            self.service.save_decision(self.session_id, 'DEMO-0042', 'Layak', 'Perlu dipindahkan', 'Alasan')
        with self.assertRaises(ValueError):
            self.service.save_decision(self.session_id, self.batch_id, 'Tidak layak', 'Perlu dipindahkan', 'Alasan')
        with self.assertRaises(ValueError):
            self.service.save_decision(self.session_id, self.batch_id, 'Layak', 'Perlu dipindahkan', '')
        self.sessions.finish(self.session_id)
        with self.assertRaises(ValueError):
            self.service.save_decision(self.session_id, self.batch_id, 'Layak', 'Perlu dipindahkan', 'Alasan')
        self.assertIsNone(self.service.for_result(self.session_id, self.batch_id))

    def test_draft_decision_can_be_corrected_then_final_report_is_locked(self):
        first = self.service.save_decision(self.session_id, self.batch_id,
            'Layak', 'Tunda evaluasi', 'Periksa ulang kondisi kemasan.')
        corrected = self.service.save_decision(self.session_id, self.batch_id,
            'Layak', 'Perlu dipindahkan', 'Kondisi baik; periksa kebutuhan site lain.')
        self.assertEqual(corrected['id'], first['id'])
        self.assertEqual(corrected['choice'], 'Perlu dipindahkan')
        self.assertEqual(corrected['reason'], 'Kondisi baik; periksa kebutuhan site lain.')
        self.sessions.finish(self.session_id)
        with self.assertRaises(ValueError):
            self.service.save_decision(self.session_id, self.batch_id,
                'Layak', 'Tunda evaluasi', 'Coba mengubah laporan final.')
        for sql, params in (
            ('UPDATE recommendation_decisions SET reason=? WHERE id=?', ('ubah', first['id'])),
            ('DELETE FROM recommendation_decisions WHERE id=?', (first['id'],)),
        ):
            with self.assertRaises(sqlite3.IntegrityError), self.db:
                self.db.execute(sql, params)

    def test_duplicate_open_actions_are_rejected_until_completed(self):
        first = self.service.save_decision(self.session_id, self.batch_id,
            'Layak', 'Perlu dipindahkan', 'Perlu evaluasi kebutuhan site lain.')
        next_session = self.sessions.start('Petugas Kedua', 'Area A')
        self.sessions.add_code(next_session, self.batch_id)
        with self.assertRaises(ValueError):
            self.service.save_decision(next_session, self.batch_id,
                'Layak', 'Perlu dipindahkan', 'Jangan duplikat tindak lanjut.')
        self.service.complete(first['id'], 'Petugas Contoh', 'Tindakan sudah selesai.')
        second = self.service.save_decision(next_session, self.batch_id,
            'Layak', 'Tidak perlu tindakan', 'Pemeriksaan ulang tidak menemukan masalah.')
        self.assertEqual(second['action_status'], 'Tidak perlu tindakan')
        self.assertEqual(self.service.latest_action_for_batch(self.batch_id)['id'], second['id'])
        with self.assertRaises(ValueError):
            self.service.complete(second['id'], 'Petugas Contoh', 'Tidak perlu.')

    def test_reopening_preserves_history_and_backup_of_v4_database(self):
        self.db.close()
        old_path = Path(self.temp.name) / 'old-v4.db'
        old = sqlite3.connect(old_path)
        old.executescript('''
            CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO metadata VALUES('mode','demo');
            CREATE TABLE batches(id TEXT PRIMARY KEY);
            CREATE TABLE check_sessions(id INTEGER PRIMARY KEY, status TEXT NOT NULL);
            CREATE TABLE check_results(session_id INTEGER NOT NULL, batch_id TEXT NOT NULL,
                PRIMARY KEY(session_id,batch_id));
            INSERT INTO batches VALUES('BAT-HISTORY');
            INSERT INTO check_sessions VALUES(1,'Selesai');
            INSERT INTO check_results VALUES(1,'BAT-HISTORY');
            PRAGMA user_version=4;
        ''')
        old.close()
        self.db = connect(old_path)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
        self.assertEqual(tuple(self.db.execute('SELECT * FROM check_results').fetchone()), (1, 'BAT-HISTORY'))
        self.assertEqual(len(list(old_path.parent.glob('old-v4.db.pre-v4-*.bak'))), 1)
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(), [])


if __name__ == '__main__':
    unittest.main()
