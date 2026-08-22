"""Runtime and UI constants used by the dashboard."""

from __future__ import annotations

from pathlib import Path

PLC_DIRECT_URL = "http://192.168.1.94/api/state"

TIMEOUT_DIRECT = 0.4
POLL_DIRECT = 0.5
POLL_MATTER = 1.0
UI_TICK = 0.35

# Sensor history logging (SQLite, batched writes to limit SD card wear).
LOG_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "sensor_log.db"
LOG_WINDOW_SECONDS = 5.0  # readings are averaged over this window before logging
LOG_FLUSH_INTERVAL = 60.0  # seconds between batched disk writes
LOG_RETENTION_DAYS = 365

# History chart display window.
CHART_WINDOW_SECONDS = 3600.0  # trailing window of history shown on the chart
CHART_UPDATE_INTERVAL = 60.0  # seconds between chart refreshes

# Prefer local loopback on the Pi; fallback to LAN IP if routes shift.
MATTER_WS_URLS = (
    "ws://127.0.0.1:5580/ws",
    "ws://192.168.1.95:5580/ws",
)
MATTER_TIMEOUT = 2.0
MATTER_CONNECT_RETRIES = 2
MATTER_FAILS_TO_OFFLINE = 3
MATTER_ENDPOINT_ID = 1
MATTER_ONOFF_CLUSTER = 6
MATTER_PULSE_SECONDS = 0.5

MATTER_DOORS = {
    "right": {"label": "GARAGE RIGHT", "node_id": 1},
    "left": {"label": "GARAGE LEFT", "node_id": 3},
}

# Visual theme aligned with Garden PLC HTML.
C_BG = "#0c0c0c"
C_SURFACE = "#141414"
C_BORDER = "#222222"
C_TEXT = "#d4d4d4"
C_DIM = "#555555"
C_DIM2 = "#3a3a3a"
C_ON = "#22c55e"
C_WARN = "#ef4444"
C_ACCENT = "#3b82f6"
C_AMBER = "#f59e0b"


def key_prefix(side: str) -> str:
    """Map garage side names to state key prefixes."""
    return "mr" if side == "right" else "ml"
