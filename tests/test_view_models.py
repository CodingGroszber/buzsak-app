"""Display rules: what the user is told about each value, device and connection (DATA-02, VLV-07, UX-13)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from conftest import load_state_fixture

from buzsak_app.domain.models import ValueState
from buzsak_app.domain.snapshot import parse_snapshot
from buzsak_app.state.connection import ConnectionStatus
from buzsak_app.ui import strings
from buzsak_app.ui.view_models import (
    Tone,
    connection_view,
    device_detail,
    freshness_text,
    health_view,
    kpi_view,
    sorted_parameters,
)


def _snapshot(name):
    return parse_snapshot(load_state_fixture(name))


def _device(snapshot, device_id):
    return next(d for p in snapshot.parties for d in p.devices if d.id == device_id)


def _view(snapshot, device_id, parameter_id):
    device = _device(snapshot, device_id)
    return kpi_view(device, device.parameter(parameter_id))


class TestKpiView:
    def test_good_number_has_value_unit_and_no_badge(self) -> None:
        view = _view(_snapshot("normal"), "garden-plc", "pressure_bar")
        assert (view.value_text, view.unit, view.badge,
                view.dimmed) == ("2.80", "bar", None, False)
        assert view.label == "Pressure"
        assert view.caption

    def test_ratio_is_a_percentage(self) -> None:
        view = _view(_snapshot("normal"),
                     "valve-controller", "automation_duty")
        assert (view.value_text, view.unit) == ("40", "%")

    def test_false_is_off_and_not_missing(self) -> None:
        view = _view(_snapshot("normal"), "valve-controller", "relay2_rain")
        assert view.value_text == strings.VALUE_OFF
        assert view.badge is None

    def test_true_is_on(self) -> None:
        assert _view(_snapshot("normal"), "valve-controller",
                     "relay1_mist").value_text == strings.VALUE_ON

    def test_mode_is_words_in_smaller_type(self) -> None:
        view = _view(_snapshot("normal"), "valve-controller", "mode")
        assert view.value_text == "Automatic"
        assert view.long_text

    def test_short_values_use_the_large_type(self) -> None:
        assert not _view(_snapshot("normal"), "garden-plc",
                         "pressure_bar").long_text

    def test_no_data_is_a_dash_never_zero_or_off(self) -> None:
        view = _view(_snapshot("degraded"), "garden-plc", "tank_pump")
        assert view.value_text == strings.VALUE_MISSING
        assert view.unit is None
        assert view.badge.text == strings.STATE_NO_DATA
        assert view.badge.tone is Tone.MUTED
        assert not view.dimmed  # nothing to dim: the dash and badge already say so

    def test_stale_keeps_the_value_but_dims_and_flags_it(self) -> None:
        view = _view(_snapshot("degraded"), "garden-plc", "well_pump")
        assert view.value_text == strings.VALUE_OFF
        assert view.badge.text == strings.STATE_STALE
        assert view.dimmed

    def test_unavailable_is_flagged_as_an_error_and_dimmed(self) -> None:
        view = _view(_snapshot("degraded"), "garden-plc", "pressure_bar")
        assert view.badge.text == strings.STATE_UNAVAILABLE
        assert view.badge.tone is Tone.ERROR
        assert view.dimmed

    def test_invalid_is_flagged(self) -> None:
        view = _view(_snapshot("degraded"), "garden-plc", "water_level_liters")
        assert view.badge.text == strings.STATE_INVALID
        assert view.dimmed

    def test_invalid_without_a_value_shows_a_dash(self) -> None:
        view = _view(_snapshot("degraded"), "sonoff-1", "on_off")
        assert view.value_text == strings.VALUE_MISSING
        assert view.badge.text == strings.STATE_INVALID

    def test_every_non_good_state_has_a_badge_with_words_and_an_icon(self) -> None:
        snap = _snapshot("degraded")
        for device in (d for p in snap.parties for d in p.devices):
            for parameter in device.parameters:
                view = kpi_view(device, parameter)
                if not parameter.is_current:
                    assert view.badge is not None and view.badge.text and view.badge.icon

    def test_automation_values_are_frozen_in_manual_mode(self) -> None:
        view = _view(_snapshot("degraded"), "valve-controller",
                     "automation_elapsed_s")
        assert view.badge.text == strings.STATE_FROZEN
        assert view.caption == strings.FROZEN_CAPTION
        assert view.dimmed
        assert view.value_text == "187"  # the last value stays visible

    def test_automation_values_are_live_in_automatic_mode(self) -> None:
        view = _view(_snapshot("normal"), "valve-controller",
                     "automation_elapsed_s")
        assert view.badge is None and not view.dimmed

    def test_a_stale_automation_value_shows_stale_not_frozen(self) -> None:
        snap = _snapshot("degraded")
        device = _device(snap, "valve-controller")
        parameter = device.parameter("automation_duty")
        stale = replace(parameter, state=ValueState.STALE)
        view = kpi_view(device, stale)
        assert view.badge.text == strings.STATE_STALE

    def test_detail_names_the_parameter_and_times(self) -> None:
        view = _view(_snapshot("normal"), "garden-plc", "pressure_bar")
        assert "pressure_bar" in view.detail
        assert strings.DETAIL_OBSERVED in view.detail and strings.DETAIL_CHANGED in view.detail

    def test_detail_shows_the_problem_the_app_found(self) -> None:
        payload = load_state_fixture("normal")
        payload["parties"][0]["devices"][0]["parameters"][1]["value"] = "abc"
        snap = parse_snapshot(payload)
        assert strings.DETAIL_PROBLEM in _view(
            snap, "garden-plc", "pressure_bar").detail

    def test_unknown_parameter_gets_a_generic_card(self) -> None:
        payload = load_state_fixture("normal")
        payload["parties"][0]["devices"][0]["parameters"].append(
            {"id": "flow_lpm", "category": "continuous", "unit": "L/min", "value": "3.5", "value_type": "float",
             "quality": "good", "stale": False, "observed_at": "2026-10-05T11:59:59Z",
             "last_changed_at": None, "revision": 1, "has_data": True}
        )
        view = _view(parse_snapshot(payload), "garden-plc", "flow_lpm")
        assert (view.label, view.value_text, view.unit, view.icon) == (
            "Flow lpm", "3.5", "L/min", "sensors")


def test_sorted_parameters_follow_the_catalog_then_unknown_by_id() -> None:
    payload = load_state_fixture("normal")
    payload["parties"][0]["devices"][0]["parameters"].append(
        {"id": "a_new_one", "category": "continuous", "unit": None, "value": "1", "value_type": "int",
         "quality": "good", "stale": False, "observed_at": "2026-10-05T11:59:59Z",
         "last_changed_at": None, "revision": 1, "has_data": True}
    )
    ids = [p.id for p in sorted_parameters(
        _device(parse_snapshot(payload), "garden-plc"))]
    assert ids[:2] == ["pressure_bar", "water_level_liters"]
    assert ids[-1] == "a_new_one"


class TestHealthAndDetail:
    def test_healthy(self) -> None:
        view = health_view(_device(_snapshot("normal"), "garden-plc"))
        assert (view.text, view.tone, view.detail) == (
            strings.HEALTH_HEALTHY, Tone.OK, None)

    def test_offline_explains_itself(self) -> None:
        view = health_view(_device(_snapshot("degraded"), "garden-plc"))
        assert view.text == strings.HEALTH_OFFLINE
        assert view.tone is Tone.ERROR
        assert "5 failed polls" in view.detail and "timed out" in view.detail

    def test_singular_failure(self) -> None:
        assert "1 failed poll:" in health_view(
            _device(_snapshot("degraded"), "valve-controller")).detail

    def test_detail_adds_the_last_pulse(self) -> None:
        assert device_detail(
            _device(_snapshot("normal"), "sonoff-1")) == "Last pulse: succeeded"
        failed = device_detail(_device(_snapshot("degraded"), "sonoff-1"))
        assert failed == "Last pulse: failed (device unreachable)"

    def test_no_detail_for_a_quiet_healthy_device(self) -> None:
        assert device_detail(
            _device(_snapshot("normal"), "garden-plc")) is None

    def test_unknown_health_is_muted(self) -> None:
        payload = load_state_fixture("normal")
        del payload["parties"][0]["devices"][0]["health"]
        assert health_view(_device(parse_snapshot(payload),
                           "garden-plc")).tone is Tone.MUTED


class TestConnectionView:
    @pytest.mark.parametrize(
        ("status", "banner"),
        [
            (ConnectionStatus.CONNECTING, False),
            (ConnectionStatus.ONLINE, False),
            (ConnectionStatus.OFFLINE, True),
            (ConnectionStatus.SERVER_UNHEALTHY, True),
        ],
    )
    def test_banner_only_when_data_may_be_out_of_date(self, status, banner) -> None:
        view = connection_view(status)
        assert view.show_banner is banner
        assert view.text and view.icon

    def test_every_status_has_a_view(self) -> None:
        assert {connection_view(s).text for s in ConnectionStatus}.__len__() == len(
            ConnectionStatus)


class TestFreshness:
    @pytest.mark.parametrize(
        ("age", "text"),
        [(0, "Updated 0 s ago"), (3.9, "Updated 3 s ago"), (59, "Updated 59 s ago"),
         (60, "Updated 1 min ago"), (125, "Updated 2 min ago"), (3600, "Updated 1 h ago")],
    )
    def test_text(self, age, text) -> None:
        assert freshness_text(age) == text

    def test_never(self) -> None:
        assert freshness_text(None) == strings.FRESHNESS_NEVER
