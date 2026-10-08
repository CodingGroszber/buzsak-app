"""Frozen-automation rule for the valve controller (DATA-02, VLV-07).

While `mode == manual` the controller stops updating its `automation_*` values, yet
the server keeps reporting them with quality `good`. They must not be shown as live.
"""

from __future__ import annotations

from buzsak_app.domain.models import Device

AUTOMATION_PREFIX = "automation_"
MODE_PARAMETER = "mode"
MANUAL = "manual"


def is_automation_parameter(parameter_id: str) -> bool:
    return parameter_id.startswith(AUTOMATION_PREFIX)


def is_frozen(device: Device, parameter_id: str) -> bool:
    """True if `parameter_id` is an automation value and the device is in manual mode.

    Uses the last known mode even if it is stale: its own state is shown separately,
    and an unknown mode (no value) never claims "frozen".
    """
    if not is_automation_parameter(parameter_id):
        return False
    mode = device.parameter(MODE_PARAMETER)
    return mode is not None and mode.value == MANUAL
