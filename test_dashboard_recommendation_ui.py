"""The dashboard reveals a specific demo destination for the selected item."""
import tempfile
import tkinter as tk
import unittest
from pathlib import Path

from warehouse.ui import Application


class DashboardRecommendationUITests(unittest.TestCase):
    def test_selected_item_shows_specific_demo_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            root = tk.Tk()
            root.withdraw()
            app = Application(root, Path(folder) / "dashboard.db")
            try:
                with app.db:
                    app.db.execute(
                        """INSERT INTO site_demand
                           (material, site, demand_prev, demand_now, open_demand, site_stock)
                           VALUES ('MAT-004', 'A', 2, 8, 9, 1)"""
                    )
                app.show("Dashboard")
                page = app.dashboard_page
                page.selected_item = next(row for row in page.data["rows"] if row["id"] == "DEMO-0004")
                page.update_info()
                self.assertIn("Site A", page.info_caption.cget("text"))
                self.assertIn("simulasi", page.info_caption.cget("text").lower())
            finally:
                app.close()


if __name__ == "__main__":
    unittest.main()
