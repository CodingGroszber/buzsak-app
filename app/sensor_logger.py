"""Averages PLC readings over a short window and batches them into storage.

Pure logging logic: extracts pressure/water level from PLC payloads, means
them over ``window_seconds``, and flushes the accumulated averages to a
``SensorDatabase`` every ``flush_interval`` seconds — independent of how the
database is implemented.
"""

from __future__ import annotations

import threading
import time

from app.plc_view import pick_analog_metric, pick_metric
from app.sensor_store import Row, SensorDatabase


def _extract_pressure(data: dict) -> float | None:
    value = pick_analog_metric(data, "pressure", ["bar", "value", "pressure"])
    if value == "--":
        value = pick_metric(
            data, ["pressure", "pressure_bar", "pressureBar", "plc_pressure"])
    return float(value) if value != "--" else None


def _extract_water_level(data: dict) -> float | None:
    value = pick_analog_metric(data, "water_level", ["liters", "value", "level"])
    if value == "--":
        value = pick_metric(
            data,
            ["water_level", "waterLevel", "tank_level", "tankLevel", "level"],
        )
    return float(value) if value != "--" else None


class SensorLogger:
    """Feeds PLC readings into a 5s mean, batched to disk every ~60s."""

    def __init__(
        self,
        db: SensorDatabase,
        window_seconds: float = 5.0,
        flush_interval: float = 60.0,
        retention_days: int = 30,
    ) -> None:
        self._db = db
        self._window_seconds = window_seconds
        self._flush_interval = flush_interval
        self._retention_days = retention_days
        self._lock = threading.Lock()
        self._window_start = time.monotonic()
        self._window_samples: list[tuple[float | None, float | None]] = []
        self._buffer: list[Row] = []
        self._last_flush_ts = time.monotonic()
        self._last_prune_ts = 0.0

    def record(self, data: dict) -> None:
        """Feed one PLC poll's reading into the current averaging window."""
        sample = (_extract_pressure(data), _extract_water_level(data))
        with self._lock:
            self._window_samples.append(sample)
            now = time.monotonic()
            if now - self._window_start >= self._window_seconds:
                self._close_window_locked()
            if now - self._last_flush_ts >= self._flush_interval:
                self._flush_locked()
                self._last_flush_ts = now

    def flush(self) -> None:
        """Force any pending window average and buffered rows to storage."""
        with self._lock:
            self._close_window_locked()
            self._flush_locked()

    def _close_window_locked(self) -> None:
        """Collapse the current window's samples into a single mean row."""
        if self._window_samples:
            pressures = [p for p, _ in self._window_samples if p is not None]
            levels = [w for _, w in self._window_samples if w is not None]
            mean_pressure = sum(pressures) / len(pressures) if pressures else None
            mean_level = sum(levels) / len(levels) if levels else None
            self._buffer.append((time.time(), mean_pressure, mean_level))
        self._window_samples = []
        self._window_start = time.monotonic()

    def _flush_locked(self) -> None:
        if not self._buffer:
            return
        rows, self._buffer = self._buffer, []
        try:
            self._db.insert_many(rows)
        except Exception:
            # Drop the batch rather than growing the buffer unbounded on repeated failures.
            return
        self._maybe_prune_locked()

    def _maybe_prune_locked(self) -> None:
        """Delete rows past the retention window, at most once per hour."""
        now = time.monotonic()
        if now - self._last_prune_ts < 3600:
            return
        self._last_prune_ts = now
        cutoff = time.time() - self._retention_days * 86400
        self._db.prune_before(cutoff)


__all__ = ["SensorLogger"]
