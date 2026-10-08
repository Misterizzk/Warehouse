"""Current inventory advice shown in read-only Live monitoring."""

from datetime import date, timedelta
from pathlib import Path
import tempfile
import unittest

from warehouse.database import connect
from warehouse.inventory import Inventory
from warehouse.inventory_table import recommendation_caption
from warehouse.live_ui import current_item
from warehouse.recommendations import RecommendationService
from warehouse.sessions import Sessions


class RecommendationViewTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='warehouse-reco-view-')
        self.addCleanup(self.folder.cleanup)
        self.db = connect(Path(self.folder.name) / 'demo.db')
        self.addCleanup(self.db.close)
        with self.db:
            self.db.execute('''INSERT INTO locations
                (code,area,rack,"column","row",level) VALUES (?,?,?,?,?,?)''',
                ('A-B01-K01-R01-T01', 'A', 'B01', 1, 1, 1))
            self.db.execute('''INSERT INTO batches
                (id,material,description,plant,storage_location,location_code,received_date,stock)
                VALUES (?,?,?,?,?,?,?,?)''',
                ('TEST-OLD', 'MAT-OLD', 'Older item', 'BHT', 'PBHT',
                 'A-B01-K01-R01-T01', '2026-06-20', 4))

    def test_live_shows_current_advice_without_creating_inspection(self):
        item = current_item(self.db, 'ID:TEST-OLD', today=date(2026, 9, 29))
        self.assertEqual(item['status'], 'Melewati batas')
        self.assertEqual(item['age'], 101)
        self.assertIn('pemeriksaan', item['recommendation']['next_action'].lower())
        self.assertIsNone(item['latest_action'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM check_results').fetchone()[0], 0)

    def test_live_has_no_active_advice_for_empty_stock(self):
        with self.db:
            self.db.execute('UPDATE batches SET stock=0 WHERE id=?', ('TEST-OLD',))
        item = current_item(self.db, 'ID:TEST-OLD', today=date(2026, 9, 29))
        self.assertEqual(item['status'], 'Stok habis')
        self.assertIsNone(item['recommendation'])

    def test_live_reflects_latest_staff_decision_with_attribution(self):
        with self.db:
            self.db.execute('UPDATE batches SET received_date=? WHERE id=?',
                            ((date.today() - timedelta(days=101)).isoformat(), 'TEST-OLD'))
        sessions = Sessions(self.db)
        session_id = sessions.start('Petugas Uji', 'A')
        sessions.add_code(session_id, 'ID:TEST-OLD')
        RecommendationService(self.db).save_decision(
            session_id, 'TEST-OLD', 'Layak', 'Perlu dipindahkan',
            'Petugas akan memeriksa kebutuhan site lain.')

        item = current_item(self.db, 'ID:TEST-OLD', today=date.today())
        self.assertEqual(item['latest_action']['choice'], 'Perlu dipindahkan')
        self.assertEqual(item['latest_action']['officer'], 'Petugas Uji')
        self.assertTrue(item['latest_action']['decided_at'])
        self.assertEqual(item['latest_action']['action_status'], 'Belum selesai')

    def test_data_barang_rows_keep_aging_and_add_separate_advice(self):
        from warehouse.ui import recommendation_rows
        rows = Inventory(self.db).list_batches(today=date(2026, 9, 29))

        displayed = recommendation_rows(self.db, rows, today=date(2026, 9, 29))

        self.assertEqual(displayed[0]['status'], 'Melewati batas')
        self.assertEqual(displayed[0]['recommendation']['title'], 'Periksa barang segera')
        self.assertIsNone(displayed[0]['latest_action'])

    def test_data_barang_table_shows_advice_before_staff_decision(self):
        row = dict(stock=4, recommendation={'title': 'Periksa barang segera'}, latest_action=None)
        self.assertEqual(recommendation_caption(row), 'Periksa barang segera')


if __name__ == '__main__':
    unittest.main()
