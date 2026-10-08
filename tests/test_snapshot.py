"""Snapshot parsing against synthetic server payloads (SRV-01, SRV-11, DATA-02, SSOT-08, NFR-04)."""

from __future__ import annotations

import copy
from datetime import UTC, datetime

import pytest
from conftest import load_state_fixture

from buzsak_app.domain.models import HealthStatus, ValueState
from buzsak_app.domain.snapshot import SnapshotFormatError, parse_snapshot


def _device(snapshot, device_id):
    return next(d for p in snapshot.parties for d in p.devices if d.id == device_id)


def _payload_with_param(**overrides) -> dict:
    """normal.json with sensor values on the first PLC parameter replaced."""
    payload = load_state_fixture("normal")
    payload["parties"][0]["devices"][0]["parameters"][1].update(
        overrides)  # pressure_bar
    return payload


def _pressure(snapshot):
    return _device(snapshot, "garden-plc").parameter("pressure_bar")


class TestNormal:
    def test_structure_and_order(self) -> None:
        snap = parse_snapshot(load_state_fixture("normal"))
        assert snap.generated_at == datetime(2026, 10, 5, 12, tzinfo=UTC)
        assert [p.id for p in snap.parties] == [
            "garden_plc", "valve_controller", "matter"]
        assert [p.label for p in snap.parties] == [
            "PUMP", "GREENHOUSE", "GARAGE"]
        assert [d.id for d in snap.parties[2].devices] == [
            "sonoff-1", "sonoff-2"]
        assert snap.issues == ()

    def test_every_parameter_is_good_and_typed(self) -> None:
        snap = parse_snapshot(load_state_fixture("normal"))
        valve = _device(snap, "valve-controller")
        assert valve.parameter("mode").value == "automatic"
        assert valve.parameter("automation_period_s").value == 600
        assert valve.parameter("relay1_mist").value is True
        assert valve.parameter("sensor_a_humidity_pct").value == 87.4
        assert all(
            p.state is ValueState.GOOD for d in snap.parties[1].devices for p in d.parameters)

    def test_false_and_zero_are_values_not_missing(self) -> None:
        snap = parse_snapshot(load_state_fixture("normal"))
        rain = _device(snap, "valve-controller").parameter("relay2_rain")
        assert rain.value is False
        assert rain.state is ValueState.GOOD

    def test_health_and_last_pulse(self) -> None:
        snap = parse_snapshot(load_state_fixture("normal"))
        assert _device(
            snap, "garden-plc").health.status is HealthStatus.HEALTHY
        assert _device(snap, "garden-plc").last_pulse is None
        pulse = _device(snap, "sonoff-1").last_pulse
        assert pulse.status == "succeeded"
        assert pulse.executed_at == datetime(2026, 10, 5, 7, 30, 1, tzinfo=UTC)

    def test_capabilities_follow_the_server_flag(self) -> None:
        snap = parse_snapshot(load_state_fixture("normal"))
        valve = _device(snap, "valve-controller")
        for action in ("set_mode", "set_output"):
            cap = valve.capability(action)
            assert cap.enabled is False
            assert "not implemented" in cap.disabled_reason
        pulse = _device(snap, "sonoff-1").capability("pulse")
        assert pulse.enabled is True
        assert pulse.disabled_reason is None
        assert valve.capability(
            "set_output").params_schema["name"][0] == "relay1"


class TestDegraded:
    @pytest.fixture
    def snap(self):
        return parse_snapshot(load_state_fixture("degraded"))

    def test_no_data_is_distinct_from_false(self, snap) -> None:
        tank = _device(snap, "garden-plc").parameter("tank_pump")
        assert tank.state is ValueState.NO_DATA
        assert tank.value is None
        assert tank.observed_at is None

    def test_unavailable_keeps_last_value_but_is_not_current(self, snap) -> None:
        pressure = _pressure(snap)
        assert pressure.state is ValueState.UNAVAILABLE
        assert pressure.value == 2.8
        assert not pressure.is_current

    def test_server_invalid(self, snap) -> None:
        level = _device(snap, "garden-plc").parameter("water_level_liters")
        assert level.state is ValueState.INVALID
        assert level.issue is None  # reported by the server, not detected by the app

    def test_stale_flag_on_good_quality(self, snap) -> None:
        pump = _device(snap, "garden-plc").parameter("well_pump")
        assert pump.state is ValueState.STALE
        assert pump.value is False

    def test_good_quality_with_null_value_is_invalid(self, snap) -> None:
        on_off = _device(snap, "sonoff-1").parameter("on_off")
        assert on_off.state is ValueState.INVALID
        assert on_off.value is None

    def test_health_statuses(self, snap) -> None:
        plc = _device(snap, "garden-plc").health
        assert plc.status is HealthStatus.OFFLINE
        assert plc.consecutive_failures == 5
        assert plc.last_error == "timed out"
        assert _device(
            snap, "valve-controller").health.status is HealthStatus.DEGRADED

    def test_failed_pulse(self, snap) -> None:
        pulse = _device(snap, "sonoff-1").last_pulse
        assert (pulse.status, pulse.error) == ("failed", "device unreachable")

    def test_manual_mode_value(self, snap) -> None:
        assert _device(
            snap, "valve-controller").parameter("mode").value == "manual"


def test_unconfigured_party_with_note() -> None:
    snap = parse_snapshot(load_state_fixture("matter_unconfigured"))
    garage = snap.parties[2]
    assert garage.configured is False
    assert garage.devices == ()
    assert "Not configured" in garage.note
    assert snap.parties[0].configured is True and snap.parties[0].devices == ()


class TestTolerance:
    def test_unknown_fields_are_ignored(self) -> None:
        payload = load_state_fixture("normal")
        payload["future_field"] = 1
        payload["parties"][0]["devices"][0]["new_thing"] = {"a": 1}
        payload["parties"][0]["devices"][0]["parameters"][0]["extra"] = True
        assert parse_snapshot(payload).issues == ()

    def test_unknown_parameter_and_category_still_parse(self) -> None:
        payload = load_state_fixture("normal")
        payload["parties"][0]["devices"][0]["parameters"].append(
            {"id": "flow_lpm", "category": "newcat", "unit": "L/min", "value": "3.5", "value_type": "float",
             "quality": "good", "stale": False, "observed_at": "2026-10-05T11:59:59Z",
             "last_changed_at": None, "revision": 1, "has_data": True}
        )
        flow = _device(parse_snapshot(payload),
                       "garden-plc").parameter("flow_lpm")
        assert flow.value == 3.5 and flow.category == "newcat"

    def test_malformed_value_marks_parameter_invalid_and_keeps_snapshot(self) -> None:
        snap = parse_snapshot(_payload_with_param(value="abc"))
        assert _pressure(snap).state is ValueState.INVALID
        assert _pressure(snap).value is None
        assert "not a float" in _pressure(snap).issue
        assert any("pressure_bar" in i for i in snap.issues)
        assert _device(
            snap, "valve-controller").parameter("mode").state is ValueState.GOOD

    def test_good_quality_with_null_value_is_invalid_not_zero(self) -> None:
        snap = parse_snapshot(_payload_with_param(
            value=None, value_type="null"))
        assert _pressure(snap).state is ValueState.INVALID
        assert _pressure(snap).value is None
        assert _pressure(snap).issue == "no value"

    def test_unknown_quality_is_not_trusted(self) -> None:
        snap = parse_snapshot(_payload_with_param(quality="great"))
        assert _pressure(snap).state is ValueState.INVALID
        assert "great" in _pressure(snap).issue

    def test_bad_observed_at_is_not_trusted(self) -> None:
        assert _pressure(parse_snapshot(_payload_with_param(
            observed_at="soon"))).state is ValueState.INVALID

    def test_quality_stale_string_maps_to_stale(self) -> None:
        assert _pressure(parse_snapshot(_payload_with_param(
            quality="stale"))).state is ValueState.STALE

    def test_missing_has_data_falls_back_to_observed_at(self) -> None:
        payload = _payload_with_param()
        del payload["parties"][0]["devices"][0]["parameters"][1]["has_data"]
        assert _pressure(parse_snapshot(payload)).state is ValueState.GOOD

    def test_device_without_id_is_skipped_and_recorded(self) -> None:
        payload = load_state_fixture("normal")
        payload["parties"][0]["devices"].append({"label": "ghost"})
        snap = parse_snapshot(payload)
        assert [d.id for d in snap.parties[0].devices] == ["garden-plc"]
        assert any("devices[1]" in i for i in snap.issues)

    def test_party_without_id_is_skipped_and_recorded(self) -> None:
        payload = load_state_fixture("normal")
        payload["parties"].insert(0, {"label": "ghost", "devices": []})
        snap = parse_snapshot(payload)
        assert [p.id for p in snap.parties] == [
            "garden_plc", "valve_controller", "matter"]
        assert any("parties[0]" in i for i in snap.issues)

    def test_non_object_party_is_skipped(self) -> None:
        payload = load_state_fixture("normal")
        payload["parties"].append("oops")
        assert len(parse_snapshot(payload).parties) == 3

    def test_device_missing_lists_gives_empty_tuples(self) -> None:
        payload = load_state_fixture("normal")
        device = payload["parties"][0]["devices"][0]
        del device["parameters"], device["capabilities"], device["health"]
        parsed = _device(parse_snapshot(payload), "garden-plc")
        assert parsed.parameters == () and parsed.capabilities == ()
        assert parsed.health.status is HealthStatus.UNKNOWN

    def test_unknown_health_status_is_unknown(self) -> None:
        payload = load_state_fixture("normal")
        payload["parties"][0]["devices"][0]["health"]["status"] = "on-fire"
        assert _device(parse_snapshot(payload),
                       "garden-plc").health.status is HealthStatus.UNKNOWN

    @pytest.mark.parametrize("enabled", [None, "true", 1, "yes"])
    def test_capability_is_enabled_only_by_literal_true(self, enabled) -> None:
        payload = load_state_fixture("normal")
        cap = payload["parties"][1]["devices"][0]["capabilities"][0]
        cap["enabled"] = enabled
        parsed = _device(parse_snapshot(payload),
                         "valve-controller").capability(cap["action_id"])
        assert parsed.enabled is False

    def test_capability_without_enabled_key_is_disabled(self) -> None:
        payload = load_state_fixture("normal")
        del payload["parties"][1]["devices"][0]["capabilities"][0]["enabled"]
        assert _device(parse_snapshot(payload),
                       "valve-controller").capabilities[0].enabled is False

    def test_params_schema_may_be_a_raw_string(self) -> None:
        payload = load_state_fixture("normal")
        payload["parties"][1]["devices"][0][
            "capabilities"][0]["params_schema"] = "{broken"
        assert _device(parse_snapshot(
            payload), "valve-controller").capabilities[0].params_schema == "{broken"

    def test_input_payload_is_not_mutated(self) -> None:
        payload = load_state_fixture("degraded")
        before = copy.deepcopy(payload)
        parse_snapshot(payload)
        assert payload == before


class TestFatal:
    @pytest.mark.parametrize("payload", [None, [], "x", 3])
    def test_non_object(self, payload) -> None:
        with pytest.raises(SnapshotFormatError):
            parse_snapshot(payload)

    @pytest.mark.parametrize("generated_at", [None, "", "never", 5])
    def test_bad_generated_at(self, generated_at) -> None:
        payload = load_state_fixture("normal")
        payload["generated_at"] = generated_at
        with pytest.raises(SnapshotFormatError):
            parse_snapshot(payload)

    @pytest.mark.parametrize("parties", [None, {}, "x"])
    def test_bad_parties(self, parties) -> None:
        payload = load_state_fixture("normal")
        payload["parties"] = parties
        with pytest.raises(SnapshotFormatError):
            parse_snapshot(payload)
