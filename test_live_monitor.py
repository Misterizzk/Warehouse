"""Behavior of the in-memory, multi-QR Live monitor."""

import queue
import unittest

from warehouse.live_monitor import LiveMonitor


POINTS = ((10, 10), (30, 10), (30, 30), (10, 30))
MOVED_POINTS = ((50, 50), (70, 50), (70, 70), (50, 70))


class FakeWorker:
    def __init__(self):
        self.frames = queue.Queue()
        self.messages = queue.Queue()
        self.starts = []
        self.stop_requests = 0
        self.start_error = None

    def start(self, index=0):
        if self.start_error:
            raise self.start_error
        self.starts.append(index)

    def stop(self):
        self.stop_requests += 1

    def frame(self, image, found):
        self.frames.put((image, found))


class LiveMonitorTests(unittest.TestCase):
    def setUp(self):
        self.now = [0.0]
        self.worker = FakeWorker()
        self.monitor = LiveMonitor(worker_factory=lambda: self.worker, clock=lambda: self.now[0])

    def test_confirms_distinct_reads_and_retains_temporarily_missed_code(self):
        self.monitor.start()
        first_frame = object()
        self.worker.frame(first_frame, [('ID:A', POINTS), ('ID:A', MOVED_POINTS)])
        snapshot = self.monitor.poll()
        self.assertIs(snapshot.frame, first_frame)
        self.assertEqual(snapshot.detections, ())

        self.now[0] = 0.1
        self.worker.frame(object(), [('ID:A', MOVED_POINTS)])
        snapshot = self.monitor.poll()
        self.assertEqual(len(snapshot.detections), 1)
        detection = snapshot.detections[0]
        self.assertEqual(detection.code, 'ID:A')
        self.assertEqual(detection.points, MOVED_POINTS)
        self.assertTrue(detection.visible)

        self.now[0] = 0.5
        self.worker.frame(object(), [])
        snapshot = self.monitor.poll()
        self.assertEqual(len(snapshot.detections), 1)
        self.assertFalse(snapshot.detections[0].visible)

        self.now[0] = 2.09
        self.assertEqual(len(self.monitor.poll().detections), 1)
        self.now[0] = 2.1
        self.assertEqual(self.monitor.poll().detections, ())

    def test_latest_frame_only_and_stable_order_when_codes_move(self):
        self.monitor.start()
        self.worker.frame('discarded-1', [('ID:OLD', POINTS)])
        self.worker.frame('discarded-2', [('ID:OLD', POINTS)])
        self.worker.frame('latest', [('ID:B', POINTS), ('ID:A', POINTS)])
        snapshot = self.monitor.poll()
        self.assertEqual(snapshot.frame, 'latest')
        self.assertEqual(snapshot.detections, ())

        self.now[0] = 0.1
        self.worker.frame('next', [('ID:B', POINTS), ('ID:A', POINTS)])
        self.assertEqual(tuple(d.code for d in self.monitor.poll().detections), ('ID:B', 'ID:A'))

        self.now[0] = 0.2
        self.worker.frame('moved', [('ID:A', MOVED_POINTS), ('ID:B', MOVED_POINTS)])
        snapshot = self.monitor.poll()
        self.assertEqual(tuple(d.code for d in snapshot.detections), ('ID:B', 'ID:A'))
        self.assertEqual(snapshot.detections[0].points, MOVED_POINTS)
        self.assertEqual(snapshot.detections[1].points, MOVED_POINTS)

    def test_read_after_hold_expires_requires_fresh_confirmation(self):
        self.monitor.start()
        self.worker.frame(object(), [('ID:A', POINTS)])
        self.monitor.poll()

        self.now[0] = 3.0
        self.worker.frame(object(), [('ID:A', POINTS)])
        self.assertEqual(self.monitor.poll().detections, ())

        self.now[0] = 3.1
        self.worker.frame(object(), [('ID:A', POINTS)])
        self.assertEqual(tuple(d.code for d in self.monitor.poll().detections), ('ID:A',))

    def test_start_stop_restart_and_all_messages(self):
        self.monitor.start(index=2)
        self.assertTrue(self.monitor.is_running)
        self.assertEqual(self.worker.starts, [2])
        with self.assertRaises(ValueError):
            self.monitor.start()

        self.monitor.stop()
        self.assertTrue(self.monitor.is_running)
        self.assertEqual(self.worker.stop_requests, 1)
        self.worker.messages.put(('error', 'Kamera terputus'))
        self.worker.messages.put(('stopped', None))
        snapshot = self.monitor.poll()
        self.assertEqual(snapshot.messages, (('error', 'Kamera terputus'), ('stopped', None)))
        self.assertFalse(snapshot.running)
        self.assertFalse(self.monitor.is_running)

        self.monitor.start()
        self.assertTrue(self.monitor.is_running)
        self.assertEqual(self.worker.starts, [2, 0])

    def test_failed_start_does_not_claim_camera_is_running(self):
        self.worker.start_error = ValueError('Kamera dipakai aplikasi lain')
        with self.assertRaisesRegex(ValueError, 'dipakai'):
            self.monitor.start()
        self.assertFalse(self.monitor.is_running)
        self.assertEqual(self.monitor.poll().messages, ())
        self.worker.start_error = None
        self.monitor.start()
        self.assertTrue(self.monitor.is_running)


if __name__ == '__main__':
    unittest.main()
