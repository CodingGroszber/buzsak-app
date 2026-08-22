"""Fetch logged sensor history for common ranges: 1h, 1d, 30d, or max.

Usable as a library (``fetch_range``) or standalone CLI:
    python -m app.sensor_query --range 1d --out history.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime, timezone
from typing import TextIO

from app.constants import LOG_DB_PATH
from app.sensor_store import Row, SensorDatabase

RANGE_SECONDS = {
    "1h": 3600,
    "1d": 86400,
    "30d": 30 * 86400,
}
RANGE_CHOICES = (*RANGE_SECONDS, "max")


def fetch_range(db: SensorDatabase, range_key: str) -> list[Row]:
    """Fetch readings for '1h', '1d', '30d', or 'max' (all stored history)."""
    if range_key == "max":
        return db.query_all()
    if range_key not in RANGE_SECONDS:
        raise ValueError(f"Unknown range: {range_key!r} (expected 1h, 1d, 30d, or max)")
    since_ts = time.time() - RANGE_SECONDS[range_key]
    return db.query_since(since_ts)


def _write_csv(rows: list[Row], out: TextIO) -> None:
    writer = csv.writer(out)
    writer.writerow(["timestamp_utc", "pressure_bar", "water_level_l"])
    for ts, pressure, water_level in rows:
        stamp = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        writer.writerow([stamp, pressure, water_level])


def main() -> None:
    parser = argparse.ArgumentParser(description="Export logged sensor history as CSV")
    parser.add_argument("--range", choices=RANGE_CHOICES, default="1d",
                        help="Time window to export (default: 1d)")
    parser.add_argument("--out", help="Output CSV file path (defaults to stdout)")
    args = parser.parse_args()

    db = SensorDatabase(LOG_DB_PATH)
    rows = fetch_range(db, args.range)

    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            _write_csv(rows, f)
    else:
        _write_csv(rows, sys.stdout)


if __name__ == "__main__":
    main()
