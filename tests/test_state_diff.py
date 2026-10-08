"""Snapshot diffing: only real display changes count (UPD-07)."""

from __future__ import annotations

import copy

from conftest import load_state_fixture

from buzsak_app.domain.snapshot import parse_snapshot
from buzsak_app.state.diff import diff_snapshots


def _snap(payload):
    return parse_snapshot(payload)


def _param(payload, device_index, party_index, parameter_id):
    device = payload["parties"][party_index]["devices"][device_index]
    return next(p for p in device["parameters"] if p["id"] == parameter_id)


def test_first_snapshot_marks_everything_changed() -> None:
    new = _snap(load_state_fixture("normal"))
    diff = diff_snapshots(None, new)
    assert diff.structure_changed
    assert {"garden-plc", "valve-controller",
            "sonoff-1", "sonoff-2"} <= diff.changed_devices
    assert ("garden-plc", "pressure_bar") in diff.changed_parameters


def test_identical_snapshot_is_empty() -> None:
    payload = load_state_fixture("normal")
    assert diff_snapshots(_snap(payload), _snap(
        copy.deepcopy(payload))).is_empty


def test_new_observation_time_alone_is_not_a_change() -> None:
    old = load_state_fixture("normal")
    new = copy.deepcopy(old)
    new["generated_at"] = "2026-10-05T12:00:05Z"
    for party in new["parties"]:
        for device in party["devices"]:
            for parameter in device["parameters"]:
                parameter["observed_at"] = "2026-10-05T12:00:04Z"
            device["health"]["last_success_at"] = "2026-10-05T12:00:04Z"
    assert diff_snapshots(_snap(old), _snap(
        new)).changed_parameters == frozenset()


def test_value_change_marks_only_that_parameter() -> None:
    old = load_state_fixture("normal")
    new = copy.deepcopy(old)
    _param(new, 0, 0, "pressure_bar").update(value="3.1",
                                             revision=1524, last_changed_at="2026-10-05T12:00:01Z")
    diff = diff_snapshots(_snap(old), _snap(new))
    assert diff.changed_parameters == {("garden-plc", "pressure_bar")}
    assert diff.changed_devices == frozenset()
    assert not diff.structure_changed


def test_state_change_without_value_change_is_a_change() -> None:
    old = load_state_fixture("normal")
    new = copy.deepcopy(old)
    _param(new, 0, 0, "tank_pump").update(stale=True)
    assert diff_snapshots(_snap(old), _snap(new)).changed_parameters == {
        ("garden-plc", "tank_pump")}


def test_health_change_marks_the_device_not_its_parameters() -> None:
    old = load_state_fixture("normal")
    new = copy.deepcopy(old)
    new["parties"][0]["devices"][0]["health"].update(
        status="degraded", consecutive_failures=1)
    diff = diff_snapshots(_snap(old), _snap(new))
    assert diff.changed_devices == {"garden-plc"}
    assert diff.changed_parameters == frozenset()


def test_capability_enabled_change_marks_the_device() -> None:
    old = load_state_fixture("normal")
    new = copy.deepcopy(old)
    new["parties"][1]["devices"][0]["capabilities"][0].update(
        enabled=True, disabled_reason=None)
    assert diff_snapshots(_snap(old), _snap(new)).changed_devices == {
        "valve-controller"}


def test_last_pulse_change_marks_the_device() -> None:
    old = load_state_fixture("normal")
    new = copy.deepcopy(old)
    new["parties"][2]["devices"][1]["last_pulse"] = {
        "status": "pending", "requested_at": "2026-10-05T12:00:01Z", "executed_at": None, "error": None,
    }
    assert diff_snapshots(_snap(old), _snap(
        new)).changed_devices == {"sonoff-2"}


def test_added_device_changes_structure() -> None:
    old = load_state_fixture("normal")
    new = copy.deepcopy(old)
    extra = copy.deepcopy(new["parties"][2]["devices"][0])
    extra["id"] = "sonoff-3"
    new["parties"][2]["devices"].append(extra)
    diff = diff_snapshots(_snap(old), _snap(new))
    assert diff.structure_changed
    assert "sonoff-3" in diff.changed_devices
    assert ("sonoff-3", "on_off") in diff.changed_parameters


def test_removed_device_changes_structure() -> None:
    old = load_state_fixture("normal")
    new = copy.deepcopy(old)
    new["parties"][2]["devices"].pop()
    assert diff_snapshots(_snap(old), _snap(new)).structure_changed


def test_reordered_parties_change_structure() -> None:
    old = load_state_fixture("normal")
    new = copy.deepcopy(old)
    new["parties"].reverse()
    assert diff_snapshots(_snap(old), _snap(new)).structure_changed


def test_party_becoming_configured_changes_structure() -> None:
    old = load_state_fixture("matter_unconfigured")
    new = load_state_fixture("normal")
    assert diff_snapshots(_snap(old), _snap(new)).structure_changed


def test_removed_parameter_marks_the_device() -> None:
    old = load_state_fixture("normal")
    new = copy.deepcopy(old)
    new["parties"][0]["devices"][0]["parameters"].pop()
    assert "garden-plc" in diff_snapshots(_snap(old),
                                          _snap(new)).changed_devices
