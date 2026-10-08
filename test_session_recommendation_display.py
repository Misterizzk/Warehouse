"""A resumed draft shows current advice; finished history keeps recorded advice."""
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from warehouse.database import connect, seed_demo
from warehouse.inventory import Inventory
from warehouse.sessions import Sessions
from warehouse.session_ui import advice_for_result
from warehouse.recommendations import RecommendationService


class SessionAdviceDisplayTests(unittest.TestCase):
    def test_saved_draft_decision_can_be_revised_using_new_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            db = connect(Path(folder) / 'destination.db')
            try:
                seed_demo(db)
                with db:
                    db.execute('INSERT INTO site_demand VALUES(?,?,?,?,?,?)',
                               ('MAT-004', 'A', 2, 8, 9, 1))
                sessions = Sessions(db)
                key = sessions.start('Petugas', 'A')
                sessions.add_code(key, 'DEMO-0004')
                service = RecommendationService(db)
                recorded = service.save_decision(
                    key, 'DEMO-0004', 'Layak', 'Pindahkan ke site',
                    'Site A membutuhkan barang.', target_kind='site', target_code='A')
                with db:
                    db.execute("DELETE FROM site_demand WHERE material='MAT-004'")
                    db.execute('INSERT INTO site_demand VALUES(?,?,?,?,?,?)',
                               ('MAT-004', 'B', 2, 8, 9, 1))

                item = sessions.results(key)[0]
                current = advice_for_result(db, sessions.get(key), item, recorded)
                self.assertEqual(current['options'][0]['target'], 'B')
                self.assertEqual(service.for_result(key, item['id'])['target_code'], 'A')
                sessions.finish(key)
                historical = advice_for_result(db, sessions.get(key), item, recorded)
                self.assertEqual(historical['options'][0]['target'], 'A')
            finally:
                db.close()

    def test_draft_uses_current_item_but_finished_result_uses_scan_date(self):
        with tempfile.TemporaryDirectory() as folder:
            db = connect(Path(folder) / "demo.db")
            try:
                seed_demo(db)
                inventory = Inventory(db)
                item = inventory.list_batches()[0]
                inventory.update(item["id"], dict(item, received_date=(date.today() - timedelta(days=89)).isoformat()))
                service = Sessions(db)
                key = service.start("Petugas", "Area A")
                service.add_code(key, item["id"])
                scan = service.results(key)[0]
                self.assertEqual(scan["status"], "Warning")
                inventory.update(item["id"], dict(item, received_date=(date.today() - timedelta(days=91)).isoformat()))
                current = advice_for_result(db, service.get(key), scan)
                self.assertEqual(current["code"], "MELEWATI_BATAS")
                service.finish(key)
                historical = advice_for_result(db, service.get(key), scan)
                self.assertEqual(historical["code"], "WARNING")
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
