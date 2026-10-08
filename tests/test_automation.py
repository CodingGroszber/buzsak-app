"""Frozen automation values (DATA-02, VLV-07)."""

from __future__ import annotations

import pytest
from conftest import load_state_fixture

from buzsak_app.domain.automation import is_automation_parameter, is_frozen
from buzsak_app.domain.snapshot import parse_snapshot


def _valve(fixture: str, mode_override: dict | None = None):
    payload = load_state_fixture(fixture)
    if mode_override is not None:
        mode = next(p for p in payload["parties"][1]
                    ["devices"][0]["parameters"] if p["id"] == "mode")
        mode.update(mode_override)
    return parse_snapshot(payload).parties[1].devices[0]


def test_automation_values_are_live_in_automatic_mode() -> None:
    valve = _valve("normal")
    assert not is_frozen(valve, "automation_duty")
    assert not is_frozen(valve, "automation_elapsed_s")


def test_automation_values_are_frozen_in_manual_mode() -> None:
    valve = _valve("degraded")  # mode == manual
    for parameter_id in ("automation_duty", "automation_elapsed_s", "automation_valve_on"):
        assert is_frozen(valve, parameter_id)


def test_non_automation_values_are_never_frozen() -> None:
    valve = _valve("degraded")
    for parameter_id in ("relay1_mist", "sensor_a_temperature_c", "mode"):
        assert not is_frozen(valve, parameter_id)


def test_unknown_mode_does_not_claim_frozen() -> None:
    valve = _valve(
        "normal", {"value": None, "value_type": "null", "quality": "unavailable"})
    assert not is_frozen(valve, "automation_duty")


def test_device_without_mode_parameter_is_not_frozen() -> None:
    plc = parse_snapshot(load_state_fixture("normal")).parties[0].devices[0]
    assert not is_frozen(plc, "automation_duty")


@pytest.mark.parametrize(
    ("parameter_id", "expected"),
    [("automation_duty", True), ("automation_", True),
     ("mode", False), ("my_automation_x", False)],
)
def test_is_automation_parameter(parameter_id, expected) -> None:
    assert is_automation_parameter(parameter_id) is expected
