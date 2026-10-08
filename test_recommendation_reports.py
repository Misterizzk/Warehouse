"""Decisions in finished reports remain the facts recorded by the officer."""
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from openpyxl import load_workbook

from warehouse.database import connect, seed_demo
from warehouse.inventory import Inventory
from warehouse.recommendations import RecommendationService
from warehouse.reports import export_excel, export_pdf, report_data
from warehouse.sessions import Sessions


class RecommendationReportTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = connect(Path(self.folder.name) / "report.db")
        seed_demo(self.db)

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    def test_report_and_excel_keep_inspection_decision_after_inventory_change(self):
        item = Inventory(self.db).list_batches()[0]
        inventory = Inventory(self.db)
        inventory.update(item["id"], dict(item, received_date=(date.today() - timedelta(days=120)).isoformat()))
        sessions = Sessions(self.db)
        key = sessions.start("Petugas Uji", "Area A")
        sessions.add_code(key, item["id"])
        decision = RecommendationService(self.db).save_decision(
            key, item["id"], "Layak", "Perlu dipindahkan", "Barang layak; cek kebutuhan site lain."
        )
        sessions.finish(key)
        inventory.update(item["id"], dict(item, received_date=date.today().isoformat(), stock="1"))

        data = report_data(self.db, key)
        row = data["rows"][0]
        self.assertEqual(row["status"], "Melewati batas")
        self.assertEqual(row["age"], decision["age_at_decision"])
        self.assertEqual(row["decision"]["choice"], "Perlu dipindahkan")
        self.assertEqual(row["decision"]["reason"], "Barang layak; cek kebutuhan site lain.")
        self.assertEqual(row["decision"]["officer"], "Petugas Uji")

        output = Path(self.folder.name) / "report.xlsx"
        export_excel(data, output)
        workbook = load_workbook(output, read_only=True, data_only=True)
        try:
            values = list(workbook["Hasil pengecekan"].values)
            columns = values[0]
            record = dict(zip(columns, values[1]))
            self.assertEqual(record["Keputusan petugas"], "Perlu dipindahkan")
            self.assertEqual(record["Kondisi fisik"], "Layak")
            self.assertIn("kebutuhan site lain", record["Alasan keputusan"])
            self.assertIn("Prioritaskan pemeriksaan fisik", record["Rekomendasi saat cek"])
        finally:
            workbook.close()
        RecommendationService(self.db).complete(decision["id"], "Supervisor", "Sudah ditindaklanjuti.")
        self.assertEqual(report_data(self.db, key)["rows"], data["rows"])

    def test_pdf_exports_old_results_without_decision(self):
        key = Sessions(self.db).start("Petugas Uji", "Area A")
        Sessions(self.db).add_code(key, "DEMO-0001")
        Sessions(self.db).finish(key)
        data = report_data(self.db, key)
        self.assertIsNone(data["rows"][0]["decision"])
        path = Path(self.folder.name) / "report.pdf"
        export_pdf(data, path)
        self.assertGreater(path.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
