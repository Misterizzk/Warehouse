"""Live/inspection camera ownership without a physical webcam."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from warehouse.camera_ui import CameraWindow
from warehouse.session_ui import SessionPage


class HandoffTests(unittest.TestCase):
    def page(self, events):
        app = SimpleNamespace(
            stop_camera=lambda: events.append('close_previous'),
            pause_live_for_scan=lambda: events.append('pause_live'),
            resume_live_after_scan=lambda worker: events.append(('resume_live', worker)),
            camera_window=None,
        )
        page = SessionPage.__new__(SessionPage)
        page.app = app
        page.session_id = 42
        page.refresh_results = Mock()
        page.notice = Mock()
        return page

    def test_session_pauses_live_before_opening_scanner(self):
        events = []
        page = self.page(events)

        def build(*args):
            events.append('open_scanner')
            return object()

        with patch('warehouse.camera_ui.CameraWindow', side_effect=build):
            page.open_camera()
        self.assertEqual(events, ['close_previous', 'pause_live', 'open_scanner'])
        self.assertIsNotNone(page.app.camera_window)

    def test_failed_scanner_construction_restores_live(self):
        events = []
        page = self.page(events)
        with patch('warehouse.camera_ui.CameraWindow', side_effect=ValueError('Sesi selesai')):
            page.open_camera()
        self.assertEqual(events, ['close_previous', 'pause_live', ('resume_live', None)])
        page.notice.assert_called_once_with('Sesi selesai')

    def test_unexpected_scanner_construction_error_also_restores_live(self):
        events = []
        page = self.page(events)
        with patch('warehouse.camera_ui.CameraWindow', side_effect=RuntimeError('Tk failed')):
            with self.assertRaisesRegex(RuntimeError, 'Tk failed'):
                page.open_camera()
        self.assertEqual(events, ['close_previous', 'pause_live', ('resume_live', None)])

    def window(self):
        window = CameraWindow.__new__(CameraWindow)
        window.app = SimpleNamespace(
            live_monitor=SimpleNamespace(is_running=True),
            resume_live_after_scan=Mock(),
        )
        window.service = SimpleNamespace(require_draft=Mock())
        window.session_id = 42
        window.device = SimpleNamespace(get=lambda: 'Kamera 1 — perangkat 0')
        window.worker = SimpleNamespace(start=Mock(), stop=Mock())
        window.controls = Mock()
        window.next_scan = Mock()
        window.banner = SimpleNamespace(configure=Mock())
        window.after = Mock(return_value='retry-job')
        window.after_cancel = Mock()
        window.pending = None
        window._pending_start = None
        window._pending_start_index = None
        window._destroyed = False
        window.running = False
        return window

    def test_scanner_waits_for_live_release_then_starts_automatically(self):
        window = self.window()
        window.start()
        window.worker.start.assert_not_called()
        window.after.assert_called_once()
        self.assertEqual(window._pending_start, 'retry-job')

        window.app.live_monitor.is_running = False
        window._retry_start()
        window.worker.start.assert_called_once_with(0)
        self.assertIsNone(window._pending_start)

    def test_camera_discovery_also_waits_for_live_release(self):
        window = self.window()
        window.discover()
        window.worker.start.assert_not_called()
        window.app.live_monitor.is_running = False
        window._retry_discover()
        window.worker.start.assert_called_once_with(discover=True)

    def test_closing_scanner_cancels_wait_and_resumes_live_once(self):
        window = self.window()
        window.start()
        with patch('warehouse.camera_ui.tk.Toplevel.destroy') as destroy_window:
            window.destroy()
            window.destroy()
        window.after_cancel.assert_called_once_with('retry-job')
        window.worker.stop.assert_called_once()
        window.app.resume_live_after_scan.assert_called_once_with(window.worker)
        destroy_window.assert_called_once()


if __name__ == '__main__':
    unittest.main()
