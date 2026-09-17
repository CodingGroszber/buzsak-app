"""SQLite storage layer for sensor readings.

Owns the connection, schema, and raw read/write/prune operations only —
no averaging, scheduling, or PLC-payload knowledge belongs here.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

Row = tuple[float, float | None, float | None]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    ts REAL NOT NULL,
    pressure_bar REAL,
    water_level_l REAL
)
"""


class SensorDatabase:
    """Thin SQLite (WAL mode) wrapper for the ``readings`` table."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(_SCHEMA)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_readings_ts ON readings(ts)")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=5.0)

    def insert_many(self, rows: list[Row]) -> None:
        """Batch-insert rows in a single transaction."""
        if not rows:
            return
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO readings (ts, pressure_bar, water_level_l) VALUES (?, ?, ?)",
                rows,
            )

    def prune_before(self, cutoff_ts: float) -> None:
        """Delete rows older than ``cutoff_ts`` (epoch seconds)."""
        with self._connect() as conn:
            conn.execute("DELETE FROM readings WHERE ts < ?", (cutoff_ts,))

    def query_since(self, since_ts: float) -> list[Row]:
        """Return rows with ``ts >= since_ts``, oldest first."""
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT ts, pressure_bar, water_level_l FROM readings WHERE ts >= ? ORDER BY ts",
                (since_ts,),
            )
            return cur.fetchall()

    def query_all(self) -> list[Row]:
        """Return every stored row, oldest first."""
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT ts, pressure_bar, water_level_l FROM readings ORDER BY ts"
            )
            return cur.fetchall()


__all__ = ["SensorDatabase", "Row"]
