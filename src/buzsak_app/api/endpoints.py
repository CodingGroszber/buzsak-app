"""Server endpoint paths in one place, so the move to /api/v1 is a one-line change (SRV-03)."""

from __future__ import annotations

STATE_PATH = "/api/dashboard/state"  # SRV-01
COMMANDS_PATH = "/api/v1/devices/{device_id}/commands"
COMMAND_STATUS_PATH = "/api/v1/commands/{command_id}"
PULSE_PATH = "/api/dashboard/devices/{device_id}/pulse"  # CTL-11
HEALTHZ_PATH = "/healthz"  # SRV-02
READYZ_PATH = "/readyz"  # SRV-02
