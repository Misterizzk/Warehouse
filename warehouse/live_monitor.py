"""Transient multi-QR camera state for the Live page.

The camera worker owns capture and decoding. Call ``poll`` on the UI thread;
inventory lookups, if needed, also belong there. This module never writes to
SQLite or creates check-in results.
"""

import queue
import time
from dataclasses import dataclass

from .camera import CameraWorker


@dataclass(frozen=True)
class LiveDetection:
    code: str
    points: tuple[tuple[float, float], ...]
    first_seen: float
    last_seen: float
    visible: bool


@dataclass(frozen=True)
class LiveSnapshot:
    frame: object | None
    detections: tuple[LiveDetection, ...]
    messages: tuple[tuple[str, object], ...]
    running: bool


@dataclass
class _Track:
    code: str
    points: tuple[tuple[float, float], ...]
    first_seen: float
    last_seen: float
    reads: int = 1
    visible: bool = True


class LiveMonitor:
    """Track QR codes across frames without keeping a detection history.

    Repeated reads confirm a QR. A short missed read leaves its existing card
    in place, preserving the list order and the user's scroll position.
    ``is_running`` remains true after ``stop`` until the worker releases the
    device and its ``stopped`` message has been processed by ``poll``.
    """

    def __init__(self, camera_index=0, confirm_reads=2, hold_seconds=2.0,
                 worker_factory=CameraWorker, clock=time.monotonic):
        if confirm_reads < 1:
            raise ValueError('Jumlah pembacaan konfirmasi harus positif.')
        if hold_seconds < 0:
            raise ValueError('Waktu tahan QR tidak boleh negatif.')
        self.camera_index = camera_index
        self.confirm_reads = confirm_reads
        self.hold_seconds = hold_seconds
        self.clock = clock
        self.worker = worker_factory()
        self._tracks = {}
        self._frame = None
        self._running = False
        self._stopping = False

    @property
    def is_running(self):
        return self._running

    def start(self, index=None):
        if self._running:
            raise ValueError('Kamera Live masih aktif atau sedang berhenti.')
        # CameraWorker.start raises if the device is held by another scan.
        # Only claim the camera after that call succeeds.
        self.worker.start(self.camera_index if index is None else index)
        self._tracks.clear()
        self._frame = None
        self._stopping = False
        self._running = True

    def stop(self):
        if self._running and not self._stopping:
            self._stopping = True
            self.worker.stop()

    def poll(self):
        """Consume all events and only the newest frame, then return UI state."""
        messages = []
        while True:
            try:
                kind, value = self.worker.messages.get_nowait()
            except queue.Empty:
                break
            messages.append((kind, value))
            if kind == 'stopped':
                self._running = False
                self._stopping = False
                self._frame = None
                self._tracks.clear()

        latest = None
        while True:
            try:
                latest = self.worker.frames.get_nowait()
            except queue.Empty:
                break

        now = self.clock()
        self._expire(now)
        if self._running and not self._stopping and latest is not None:
            self._frame, found = latest
            self._observe(found, now)
        detections = tuple(
            LiveDetection(track.code, track.points, track.first_seen,
                          track.last_seen, track.visible)
            for track in self._tracks.values()
            if track.reads >= self.confirm_reads
        )
        return LiveSnapshot(self._frame, detections, tuple(messages), self._running)

    def _observe(self, found, now):
        for track in self._tracks.values():
            track.visible = False
        # Multiple identical labels in one frame count as one observation.
        seen = set()
        for code, points in found:
            if not code or code in seen:
                continue
            seen.add(code)
            corners = tuple((float(x), float(y)) for x, y in points)
            track = self._tracks.get(code)
            if track is None:
                self._tracks[code] = _Track(code, corners, now, now)
            else:
                track.points = corners
                track.last_seen = now
                track.reads += 1
                track.visible = True

    def _expire(self, now):
        for code, track in tuple(self._tracks.items()):
            if now - track.last_seen >= self.hold_seconds:
                del self._tracks[code]
