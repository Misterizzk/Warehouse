"""The inspection screen lets staff decide and finish an action without a camera."""
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from warehouse.ui import Application
from warehouse.recommendations import RecommendationService


class RecommendationUITests(unittest.TestCase):
    def test_officer_can_record_decision_and_later_mark_it_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            root = tk.Tk()
            app = None
            try:
                app = Application(root, Path(folder) / "gui.db")
                app.show("Pengecekan")
                page = app.session_page
                key = page.service.start("Petugas Uji", "Area A")
                page.open_session(key)
                page.code.set("DEMO-0001")
                page.add_button.invoke()
                scanned_status = page.service.results(key)[0]["status"]
                page.table.choose("DEMO-0001")
                self.assertEqual(page.action_button.cget("state"), "normal")
                page.action_button.invoke()
                self.assertTrue(page.action_window.winfo_exists())
                root.geometry("1366x768")
                root.update()
                self.assertLessEqual(page.action_save.winfo_rooty() + page.action_save.winfo_height(),
                                     root.winfo_screenheight())
                page.condition_var.set("Layak")
                page.choice_var.set("Prioritaskan pemakaian")
                page.reason_text.insert("1.0", "Pakai sebelum batch yang lebih baru.")
                page.action_save.invoke()
                decision = RecommendationService(app.db).for_result(key, "DEMO-0001")
                self.assertEqual(decision["choice"], "Prioritaskan pemakaian")
                self.assertEqual(decision["officer"], "Petugas Uji")

                with patch("warehouse.session_ui.messagebox.askyesno", return_value=True):
                    page.finish_button.invoke()
                page.table.choose("DEMO-0001")
                page.action_button.invoke()
                self.assertEqual(page.action_save.cget("state"), "disabled")
                root.update()
                self.assertLessEqual(page.completion_save.winfo_rooty() + page.completion_save.winfo_height(),
                                     root.winfo_screenheight())
                page.completion_actor.insert(0, "Supervisor")
                page.completion_note.insert("1.0", "Sudah diprioritaskan oleh tim gudang.")
                page.completion_save.invoke()
                complete = RecommendationService(app.db).for_result(key, "DEMO-0001")
                self.assertEqual(complete["action_status"], "Selesai")
                self.assertEqual(complete["completed_by"], "Supervisor")
                self.assertEqual(page.service.results(key)[0]["status"], scanned_status)
            finally:
                if app is not None:
                    app.close()
                else:
                    root.destroy()


if __name__ == "__main__":
    unittest.main()
