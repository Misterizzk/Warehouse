"""Desktop smoke checks for the persistent Live monitoring page."""
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from datetime import date
from unittest.mock import patch

from warehouse.ui import Application
from warehouse.live_monitor import LiveDetection, LiveSnapshot
from warehouse.live_ui import current_item


class LivePageTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = Application(self.root, Path(self.folder.name) / 'demo.db')

    def tearDown(self):
        if self.root.winfo_exists():
            self.app.close()
        self.folder.cleanup()

    def test_live_page_is_in_navigation_and_has_camera_controls(self):
        self.assertIn('Live', self.app.nav)
        self.app.show('Live')
        self.root.update()
        self.assertEqual(self.app.page, 'Live')
        self.assertEqual(self.app.live_page.start_button.cget('text'), 'Aktifkan kamera')
        self.assertEqual(self.app.live_page.stop_button.cget('text'), 'Matikan kamera')

    def test_navigating_away_does_not_stop_monitor(self):
        self.app.show('Live')
        monitor = self.app.live_monitor
        with patch.object(monitor, 'stop') as stop:
            self.app.show('Dashboard')
            self.assertIs(self.app.live_monitor, monitor)
            stop.assert_not_called()

    def test_list_keeps_existing_row_order_when_status_refreshes(self):
        self.app.show('Live')
        detections = (
            LiveDetection('ID:DEMO-0001', (), 1.0, 1.0, True),
            LiveDetection('ID:DEMO-0002', (), 2.0, 2.0, True),
        )
        snapshot = LiveSnapshot(None, detections, (), True)
        first = {
            detections[0].code: dict(material='MAT-A', location_code='A-B01-K01-R01-T01',
                                     age=120, status='Melewati batas'),
            detections[1].code: dict(material='MAT-B', location_code='A-B01-K01-R01-T02',
                                     age=20, status='Normal'),
        }
        self.app.live_page.update(snapshot, first)
        original_order = self.app.live_page._codes
        original_rows = {code: row['shell'] for code, row in self.app.live_page._rows.items()}
        changed = {
            detections[0].code: dict(first[detections[0].code], status='Normal'),
            detections[1].code: dict(first[detections[1].code], status='Melewati batas'),
        }
        self.app.live_page.update(snapshot, changed)
        self.assertEqual(self.app.live_page._codes, original_order)
        self.assertEqual({code: row['shell'] for code, row in self.app.live_page._rows.items()},
                         original_rows)

    def test_moving_qr_box_does_not_rewrite_unchanged_list_row(self):
        self.app.show('Live')
        code = 'ID:DEMO-0001'
        item = {code: dict(material='MAT-A', location_code='A-B01-K01-R01-T01',
                           age=30, status='Normal')}
        first = LiveSnapshot(None, (LiveDetection(code, ((1, 1),), 1, 1, True),), (), True)
        moved = LiveSnapshot(None, (LiveDetection(code, ((2, 2),), 1, 2, True),), (), True)
        self.app.live_page.update(first, item)
        label = self.app.live_page._rows[code]['material']
        with patch.object(label, 'configure') as configure:
            self.app.live_page.update(moved, item)
            configure.assert_not_called()

    def test_live_inventory_lookup_does_not_write_report(self):
        statements = []
        self.app.db.set_trace_callback(statements.append)
        item = current_item(self.app.db, 'ID:DEMO-0001')
        unknown = current_item(self.app.db, 'ID:NOT-IN-INVENTORY')
        self.app.db.set_trace_callback(None)
        self.assertEqual(item['code'], 'ID:DEMO-0001')
        self.assertEqual(unknown['status'], 'QR tidak dikenal')
        self.assertFalse(any(sql.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))
                             for sql in statements))

    def test_live_status_follows_calendar_without_a_new_scan(self):
        with self.app.db:
            self.app.db.execute("UPDATE batches SET received_date='2026-01-01' WHERE id='DEMO-0001'")
        code = 'ID:DEMO-0001'
        self.assertEqual(current_item(self.app.db, code, date(2026, 1, 31))['status'], 'Normal')
        self.assertEqual(current_item(self.app.db, code, date(2026, 2, 1))['status'], 'Warning')
        self.assertEqual(current_item(self.app.db, code, date(2026, 4, 2))['status'],
                         'Melewati batas')

    def test_opening_next_scanner_cancels_pending_live_resume(self):
        self.app.live_paused_for_scan = True
        self.app.live_resume_ready = True
        self.app.live_resume_worker = object()
        self.app.pause_live_for_scan()
        self.assertTrue(self.app.live_paused_for_scan)
        self.assertFalse(self.app.live_resume_ready)
        self.assertIsNone(self.app.live_resume_worker)

    def test_explicitly_stopped_live_does_not_resume_after_scanner(self):
        self.app.live_monitor._running = True  # Device release has not completed yet.
        self.app.live_stopping = True
        with patch.object(self.app.live_monitor, 'stop') as stop:
            self.app.pause_live_for_scan()
            stop.assert_not_called()
        self.assertFalse(self.app.live_paused_for_scan)
        self.app.resume_live_after_scan(None)
        self.assertFalse(self.app.live_resume_ready)


if __name__ == '__main__':
    unittest.main()
