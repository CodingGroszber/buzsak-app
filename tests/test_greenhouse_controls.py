"""Greenhouse control gates and command intents, exercised without hardware (VLV-02/03, CTL-01)."""

from __future__ import annotations

import asyncio
import copy
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import flet as ft
import pytest
from conftest import load_state_fixture

from buzsak_app.api.client import AmbiguousCommandResult
from buzsak_app.domain.models import Capability, Parameter, ValueState
from buzsak_app.domain.snapshot import parse_snapshot
from buzsak_app.ui import strings, theme
from buzsak_app.ui.greenhouse_controls import GreenhouseControls
from buzsak_app.ui.greenhouse_readings import GreenhouseReadings
from buzsak_app.ui.view_models import Tone


class DialogPage:
    def __init__(self) -> None:
        self.dialogs = []
        self.updates = 0

    def show_dialog(self, dialog) -> None:
        self.dialogs.append(dialog)

    def pop_dialog(self):
        return self.dialogs.pop() if self.dialogs else None

    def update(self) -> None:
        self.updates += 1


def _device(*, enabled: bool = False, mode: str = "automatic", stale_mode: bool = False):
    payload = copy.deepcopy(load_state_fixture("normal"))
    raw = next(p for p in payload["parties"]
               if p["id"] == "valve_controller")["devices"][0]
    raw["health"]["status"] = "healthy"
    for capability in raw["capabilities"]:
        capability["enabled"] = enabled
        capability["disabled_reason"] = None if enabled else "Valve control disabled by server."
    params = {item["id"]: item for item in raw["parameters"]}
    params["mode"]["value"] = mode
    params["mode"]["stale"] = stale_mode
    states = {"relay1": True, "relay2": False,
              "relay3": False, "relay4": False}
    for relay, state in states.items():
        suffix = relay.removeprefix("relay")
        params[f"relay{suffix}_controllable"] = {
            "id": f"relay{suffix}_controllable", "category": "configuration",
            "unit": None, "value": "true", "value_type": "bool", "quality": "good",
            "stale": False, "observed_at": "2026-10-05T11:59:59Z",
            "last_changed_at": "2026-10-05T11:59:59Z", "revision": 1, "has_data": True,
        }
        params[f"relay{suffix}_always_manual"] = {
            "id": f"relay{suffix}_always_manual", "category": "configuration",
            "unit": None, "value": "true" if relay == "relay4" else "false",
            "value_type": "bool", "quality": "good", "stale": False,
            "observed_at": "2026-10-05T11:59:59Z",
            "last_changed_at": "2026-10-05T11:59:59Z", "revision": 1, "has_data": True,
        }
    raw["parameters"] = list(params.values())
    return parse_snapshot(payload).parties[1].devices[0]


def _controls(device, *, page=None, handler=None):
    return GreenhouseControls(device, page=page, on_command=handler)


def _device_with_readings():
    device = _device()
    observed = datetime(2026, 10, 7, 16, 0, tzinfo=UTC)
    extra = (
        ("firmware", "identity", "v0.9", "string", None),
        ("ip", "identity", "192.168.1.109", "string", None),
        ("rain_valve_on", "boolean", False, "bool", None),
        ("rain_start_hour", "configuration", 5, "int", None),
        ("rain_start_minute", "configuration", 0, "int", None),
        ("rain_duration_s", "configuration", 1200, "int", "s"),
        ("rain_has_last_run", "boolean", True, "bool", None),
        ("rain_last_run_duration_s", "continuous", 1200, "int", "s"),
        ("rain_time_synced", "boolean", True, "bool", None),
        ("sensor_a_ok", "boolean", True, "bool", None),
        ("sensor_a_last_error", "diagnostic", "", "string", None),
        ("sensor_a_age_s", "diagnostic", 8, "int", "s"),
        ("sensor_b_ok", "boolean", True, "bool", None),
        ("sensor_b_last_error", "diagnostic", "timeout", "string", None),
        ("sensor_b_age_s", "diagnostic", 0, "int", "s"),
    )
    parameters = list(device.parameters)
    for parameter_id, category, value, value_type, unit in extra:
        parameters.append(Parameter(
            id=parameter_id, category=category, unit=unit, value=value,
            value_type=value_type, state=ValueState.GOOD,
            observed_at=observed, last_changed_at=observed, revision=1,
        ))
    return replace(device, parameters=tuple(parameters))


def _rain_controls(*, enabled=True, mode="manual", handler=None, lookup=None):
    device = _device_with_readings()
    device = replace(device, parameters=tuple(
        replace(parameter, value=mode) if parameter.id == "mode" else parameter
        for parameter in device.parameters
    ), capabilities=tuple(replace(capability, enabled=True, disabled_reason=None)
                          for capability in device.capabilities) + (Capability(
                              "set_rain_schedule",
                              {"start": "HH:MM", "duration_minutes": {
                                  "type": "int", "minimum": 1, "maximum": 60}},
                              enabled, None if enabled else "Rain schedule disabled by deployment",
                          ),))
    return GreenhouseControls(device, page=None, on_command=handler, on_check_command=lookup)


def test_rain_editor_loads_reported_schedule_and_requires_manual_mode_and_capability():
    panel = _rain_controls(handler=lambda *args: None)
    assert panel._rain_start.value == "05:00"
    assert panel._rain_minutes.value == "20"
    assert not panel._rain_apply.disabled
    assert _rain_controls(
        mode="automatic", handler=lambda *args: None)._rain_apply.disabled
    assert _rain_controls()._rain_apply.disabled
    blocked = _rain_controls(enabled=False, handler=lambda *args: None)
    assert blocked._rain_apply.disabled
    assert blocked._rain_reason.value == "Rain schedule disabled by deployment"


def test_rain_editor_is_compact_and_has_no_visible_helper_copy():
    panel = _rain_controls(handler=lambda *args: None)
    row = panel._rain_schedule.controls[1]
    assert isinstance(row, ft.Row)
    assert row.controls == [panel._rain_start,
                            panel._rain_minutes, panel._rain_apply]
    assert len(panel._rain_schedule.controls) == 4
    assert not panel._rain_message.visible and not panel._rain_reason.visible
    assert panel._rain_apply.tooltip == strings.RAIN_SCHEDULE_WARNING
    assert panel.control.spacing == theme.SPACING.sm


def test_rain_editor_visibility_tracks_reported_mode_without_discarding_drafts():
    panel = _rain_controls(handler=lambda *args: None)
    assert panel._rain_schedule.visible
    panel._rain_start.value = "06:15"
    panel._rain_start.on_change(None)
    manual = panel._device
    automatic = replace(manual, parameters=tuple(
        replace(parameter, value="automatic") if parameter.id == "mode" else parameter
        for parameter in manual.parameters
    ))
    panel.sync(automatic)
    assert not panel._rain_schedule.visible
    panel.sync(manual)
    assert panel._rain_schedule.visible and panel._rain_start.value == "06:15"
    stale = replace(manual, parameters=tuple(
        replace(
            parameter, state=ValueState.STALE) if parameter.id == "mode" else parameter
        for parameter in manual.parameters
    ))
    panel.sync(stale)
    assert not panel._rain_schedule.visible


@pytest.mark.parametrize(("start", "minutes"), [
    ("5:00", "10"), ("24:00", "10"), ("05:60", "10"),
    ("05:00", "0"), ("05:00", "61"), ("05:00", "1.5"),
    ("05:00", "True"), ("05:00", ""), ("\uff10\uff15:00", "10"),
])
def test_rain_editor_rejects_invalid_input_without_submitting(start, minutes):
    calls = []

    async def submit(*args):
        calls.append(args)
        return "confirmed"

    panel = _rain_controls(handler=submit)
    panel._rain_start.value = start
    panel._rain_minutes.value = minutes
    asyncio.run(panel._rain_apply.on_click(None))
    assert not calls
    assert panel._rain_message.value == strings.RAIN_SCHEDULE_INVALID


def test_rain_editor_submits_one_intent_and_keeps_reported_readbacks_unchanged():
    calls = []

    async def submit(device_id, action_id, params, key, on_status):
        calls.append((device_id, action_id, dict(params), key))
        assert panel._rain_apply.disabled
        assert panel._mode.disabled
        on_status("confirmed", None, "rain-1")
        return "confirmed"

    panel = _rain_controls(handler=submit)
    panel._rain_start.value = "23:55"
    panel._rain_minutes.value = "60"
    asyncio.run(panel._rain_apply.on_click(None))
    assert len(calls) == 1
    assert calls[0][:3] == ("valve-controller", "set_rain_schedule",
                            {"start": "23:55", "duration_minutes": 60})
    assert panel._readings._rain_time._value.value == "05:00"
    assert panel._readings._rain_duration._value.value == "1200 s"


def test_ambiguous_rain_write_locks_controller_without_retry():
    calls = []

    async def submit(*args):
        calls.append(args)
        raise AmbiguousCommandResult("lost schedule response")

    panel = _rain_controls(handler=submit)
    panel._rain_minutes.value = "10"
    asyncio.run(panel._rain_apply.on_click(None))
    asyncio.run(panel._rain_apply.on_click(None))
    asyncio.run(panel._retry_command(None))
    assert len(calls) == 1
    assert panel._locked and panel._rain_apply.disabled and panel._mode.disabled
    assert not panel._retry.visible


def test_rain_polling_preserves_unsaved_drafts_and_offline_blocks_apply():
    panel = _rain_controls(handler=lambda *args: None)
    panel._rain_start.value = "06:15"
    panel._rain_minutes.value = "12"
    panel._rain_start.on_change(None)
    panel.sync(panel._device)
    assert panel._rain_start.value == "06:15" and panel._rain_minutes.value == "12"
    panel.set_available(False)
    assert panel._rain_apply.disabled


@pytest.mark.parametrize("identifier", [
    "mode", "rain_valve_on", "relay2_rain", "rain_start_hour", "rain_start_minute", "rain_duration_s",
])
@pytest.mark.parametrize("quality", [ValueState.STALE, ValueState.INVALID, ValueState.UNAVAILABLE, ValueState.NO_DATA])
def test_rain_schedule_requires_fresh_good_prerequisites(identifier, quality):
    panel = _rain_controls(handler=lambda *args: None)
    panel.sync(replace(panel._device, parameters=tuple(
        replace(parameter, state=quality) if parameter.id == identifier else parameter
        for parameter in panel._device.parameters
    )))
    assert panel._rain_apply.disabled


@pytest.mark.parametrize("identifier", ["rain_valve_on", "relay2_rain"])
def test_rain_schedule_requires_both_rain_signals_idle(identifier):
    panel = _rain_controls(handler=lambda *args: None)
    panel.sync(replace(panel._device, parameters=tuple(
        replace(parameter, value=True) if parameter.id == identifier else parameter
        for parameter in panel._device.parameters
    )))
    assert panel._rain_apply.disabled


def test_rain_schedule_rejects_unknown_or_boolean_schema_bounds():
    panel = _rain_controls(handler=lambda *args: None)
    for schema in (
        {"start": "HH:MM", "duration_minutes": {
            "type": "int", "minimum": True, "maximum": 60}},
        {"start": "string", "duration_minutes": "int"},
    ):
        panel.sync(replace(panel._device, capabilities=tuple(
            replace(
                capability, params_schema=schema) if capability.action_id == "set_rain_schedule" else capability
            for capability in panel._device.capabilities
        )))
        assert panel._rain_apply.disabled


def test_uncertain_rain_command_recovers_with_get_only_status():
    submissions = []
    lookups = []

    async def submit(*args):
        submissions.append(args)
        args[-1]("uncertain", None, "rain-uncertain-1")
        return "uncertain"

    async def lookup(command_id, on_status):
        lookups.append(command_id)
        on_status("confirmed", None, command_id)
        return "confirmed"

    panel = _rain_controls(handler=submit, lookup=lookup)
    asyncio.run(panel._rain_apply.on_click(None))
    assert panel._check_status.visible and panel._rain_apply.disabled
    asyncio.run(panel._check_status.on_click(None))
    assert len(submissions) == 1 and lookups == ["rain-uncertain-1"]
    assert not panel._locked and not panel._check_status.visible


def test_distinct_explicit_rain_submissions_use_distinct_keys_after_definitive_failure():
    keys = []

    async def submit(device_id, action_id, params, key, on_status):
        keys.append(key)
        on_status("failed", "device_rejected", "rain-failed-1")
        return "failed"

    panel = _rain_controls(handler=submit)
    asyncio.run(panel._rain_apply.on_click(None))
    asyncio.run(panel._rain_apply.on_click(None))
    assert len(keys) == 2 and keys[0] != keys[1]


def test_new_rain_intent_does_not_reuse_an_unrelated_prior_command_id():
    async def submit(*args):
        raise AmbiguousCommandResult("lost response")

    panel = _rain_controls(handler=submit, lookup=lambda *args: None)
    panel._command_id = "prior-valve-command"
    asyncio.run(panel._rain_apply.on_click(None))
    assert panel._command_id is None and not panel._check_status.visible


def test_schedule_apply_is_disabled_by_offline_or_overdue_store_state(clock):
    from buzsak_app.settings import Settings
    from buzsak_app.state.connection import ConnectionStatus
    from buzsak_app.state.store import Store
    from buzsak_app.ui.app_view import AppView

    class Page:
        def update(self):
            pass

    original = _rain_controls(handler=lambda *args: None)._device
    source = parse_snapshot(load_state_fixture("normal"))
    source = replace(source, parties=(
        replace(source.parties[1], devices=(original,)),))
    store = Store(clock)
    view = AppView(Page(), store, Settings(), clock, lambda *args: None,
                   on_command=lambda *args: None)
    store.apply_snapshot(source)
    panel = view._party_tabs["valve_controller"]._sections[original.id]._greenhouse
    assert not panel._rain_apply.disabled
    store.apply_failure(ConnectionStatus.OFFLINE, "offline")
    assert panel._rain_apply.disabled
    store.apply_snapshot(source)
    assert not panel._rain_apply.disabled
    clock.advance(30)
    view.tick()
    assert panel._rain_apply.disabled


def test_server_disabled_capabilities_keep_controls_disabled_and_show_reason() -> None:
    panel = _controls(_device())
    assert panel._mode.disabled
    assert all(button.disabled for _, button in panel._relay_rows.values())
    assert panel._reason.value == "Valve control disabled by server."


@pytest.mark.parametrize(("status", "emoji", "tone"), [
    ("pending", "🕒", Tone.MUTED),
    ("dispatching", "⚙️", Tone.WARNING),
    ("sent", "📡", Tone.WARNING),
    ("acknowledged", "📨", Tone.WARNING),
    ("confirmed", "✅", Tone.OK),
    ("failed", "❌", Tone.ERROR),
    ("expired", "⌛", Tone.ERROR),
    ("cancelled", "⏹", Tone.MUTED),
    ("uncertain", "⚠️", Tone.WARNING),
])
def test_command_lifecycle_has_emoji_and_state_color(status, emoji, tone) -> None:
    panel = _controls(_device())
    panel._set_status(status)
    assert panel._message.value.startswith(emoji)
    assert panel._message.color == theme.tone_color(tone)


def test_fresh_manual_mode_enables_controllable_relays_only() -> None:
    panel = _controls(_device(enabled=True, mode="manual"),
                      handler=lambda *args: None)
    assert not panel._mode.disabled
    assert all(not button.disabled for _, button in panel._relay_rows.values())


def test_manual_relay_button_click_submits_without_a_dialog() -> None:
    calls = []

    async def handler(device_id, action_id, params, key, on_status):
        calls.append((device_id, action_id, dict(params)))
        on_status("confirmed", None, "c_relay")
        return "confirmed"

    page = DialogPage()
    panel = _controls(
        _device(enabled=True, mode="manual"), page=page, handler=handler)
    button = panel._relay_rows["relay1"][1]
    asyncio.run(button.on_click(None))

    assert page.dialogs == []
    assert calls == [(
        "valve-controller", "set_output", {"name": "relay1", "state": False})]


def test_automatic_mode_only_enables_the_always_manual_light() -> None:
    panel = _controls(_device(enabled=True), handler=lambda *args: None)
    assert panel._mode.selected == ["automatic"]
    assert [button.disabled for _, button in panel._relay_rows.values()] == [
        True, True, True, False]
    assert [button.content for _, button in panel._relay_rows.values()] == [
        strings.VALUE_OPEN, strings.VALUE_CLOSED,
        strings.VALUE_CLOSED, strings.VALUE_CLOSED,
    ]


def test_stale_mode_disables_all_controls() -> None:
    panel = _controls(
        _device(enabled=True, mode="manual", stale_mode=True), handler=lambda *args: None)
    assert panel._mode.disabled
    assert all(button.disabled for _, button in panel._relay_rows.values())


def test_rain_panel_placeholder_is_visible_when_server_omits_rain_fields() -> None:
    panel = _controls(_device())
    assert panel._readings._rain_missing.visible
    assert panel._readings._rain_missing.value == strings.RAIN_NOT_REPORTED


def test_greenhouse_readings_show_automation_schedules_and_sensors_without_identity_footer() -> None:
    readings = GreenhouseReadings(_device_with_readings())

    assert readings._mist_target._value.value == "90 %"
    assert readings._mist_duty._value.value == "40 %"
    assert readings._mist_progress.value == pytest.approx(187 / 600)
    assert readings._mist_progress_text.value == "187 s of 600 s · 31%"
    assert readings._rain_time._value.value == "05:00"
    assert readings._rain_duration._value.value == "1200 s"
    assert readings._rain_last_run._value.value == "1200 s"
    assert readings._mist_sensor._value.value == strings.SENSOR_VALID
    assert readings._mist_time._value.value == strings.TIME_SYNCHRONIZED
    assert readings._rain_time_sync._value.value == strings.TIME_SYNCHRONIZED
    assert readings._sensors[0]._temperature._value.value == "21.6°C"
    assert readings._sensors[0]._humidity._value.value == "87.4%"
    assert readings._sensors[0]._age.value == "Last good frame 8 s ago"
    assert readings._sensors[1]._age.value == strings.SENSOR_NO_GOOD_FRAME
    assert readings._sensors[1]._error.visible
    assert readings.control.tight
    assert isinstance(readings.control.controls[-1], ft.ResponsiveRow)
    assert readings.control.controls[0].value == strings.SENSORS
    assert readings.control.controls[1].controls == [
        sensor.control for sensor in readings._sensors]
    assert readings.control.controls[-1].controls == [
        readings._mist_panel, readings._rain_panel]
    assert not readings._rain_missing.visible


def test_greenhouse_uses_the_same_compact_header_as_pump_and_updates_identity() -> None:
    from buzsak_app.state.diff import SnapshotDiff
    from buzsak_app.ui.party_tab import PartyTab
    from buzsak_app.ui.view_models import device_identity

    source = parse_snapshot(load_state_fixture("normal")).parties[1]
    original = _device_with_readings()
    source = replace(source, devices=(original,))
    tab = PartyTab(source)
    section = tab._sections[original.id]
    body = section.control.controls[0].content
    heading = body.controls[0]
    assert isinstance(heading, ft.Row)
    assert heading.controls == [section._detail, section._health.control]
    assert original.id not in section._detail.value
    assert section._detail.value == device_identity(original)
    assert body.tight and not section._grid.visible
    updated = replace(original, parameters=tuple(
        replace(parameter, value="v1.0", state=ValueState.STALE)
        if parameter.id == "firmware" else parameter for parameter in original.parameters
    ))
    tab.apply(replace(source, devices=(updated,)), SnapshotDiff(
        structure_changed=False, changed_devices=frozenset(),
        changed_parameters=frozenset({(original.id, "firmware")}),
    ))
    assert "v1.0" in section._detail.value and strings.STATE_STALE in section._detail.value


def test_valve_rows_match_device_page_duty_and_daily_run_hints() -> None:
    panel = GreenhouseControls(
        _device_with_readings(), page=None, on_command=lambda *args: None)
    assert panel._relay_hints["relay1"].value == "4m"
    assert panel._relay_hints["relay2"].value == "05:00 · 20m"


def test_no_rain_history_is_not_rendered_as_zero() -> None:
    device = _device_with_readings()
    parameters = tuple(
        replace(
            parameter, value=False) if parameter.id == "rain_has_last_run" else parameter
        for parameter in device.parameters
    )
    readings = GreenhouseReadings(replace(device, parameters=parameters))
    assert readings._rain_last_run._value.value == strings.RAIN_NO_PREVIOUS_RUN


def test_manual_mode_marks_both_automation_panels_frozen() -> None:
    device = _device_with_readings()
    device = replace(device, parameters=tuple(
        replace(parameter, value="manual",
                revision=2) if parameter.id == "mode" else parameter
        for parameter in device.parameters
    ))
    readings = GreenhouseReadings(device)
    assert readings._mode_badge.control.visible
    assert readings._mist_panel.opacity < 1.0
    assert readings._rain_panel.opacity < 1.0


def test_stale_sensor_reading_keeps_its_quality_badge() -> None:
    device = _device_with_readings()
    parameters = tuple(
        replace(parameter, state=ValueState.STALE)
        if parameter.id == "sensor_a_humidity_pct" else parameter
        for parameter in device.parameters
    )
    readings = GreenhouseReadings(replace(device, parameters=parameters))
    humidity = readings._sensors[0]._humidity
    assert humidity._value.value == "87.4%"
    assert humidity._badge.control.visible
    assert humidity._badge._text.value == strings.STATE_STALE


def test_sensor_readings_share_one_compact_status_name_temperature_humidity_row():
    readings = GreenhouseReadings(_device_with_readings())
    sensor = readings._sensors[0]
    assert sensor._row.controls == [
        sensor._indicator, sensor._title, sensor._measurements]
    assert sensor._measurements.controls[0] is sensor._temperature._value
    assert sensor._measurements.controls[1].value == "/"
    assert sensor._measurements.controls[2] is sensor._humidity._value
    assert sensor._title.expand
    assert not sensor._health.control.visible and not sensor._quality.visible
    assert sensor.control.bgcolor is None
    assert sensor._age not in sensor.control.content.controls
    assert strings.sensor_age(8) in sensor.control.tooltip


@pytest.mark.parametrize("quality", [ValueState.STALE, ValueState.INVALID, ValueState.UNAVAILABLE, ValueState.NO_DATA])
def test_compact_sensor_rows_keep_explicit_bad_quality_and_no_healthy_indicator(quality):
    original = _device_with_readings()
    original = replace(original, parameters=tuple(
        replace(
            parameter, state=quality) if parameter.id == "sensor_a_humidity_pct" else parameter
        for parameter in original.parameters
    ))
    sensor = GreenhouseReadings(original)._sensors[0]
    assert sensor._quality.visible and sensor._humidity._badge.control.visible
    assert sensor._indicator.icon != ft.Icons.CHECK_CIRCLE
    assert sensor._indicator.semantics_label == sensor._humidity._badge._text.value


def test_compact_sensor_row_preserves_zero_readings_and_reports_faults_explicitly():
    original = _device_with_readings()
    original = replace(original, parameters=tuple(
        replace(parameter, value=0.0) if parameter.id in {"sensor_a_temperature_c", "sensor_a_humidity_pct"}
        else replace(parameter, value=False) if parameter.id == "sensor_a_ok"
        else parameter for parameter in original.parameters
    ))
    sensor = GreenhouseReadings(original)._sensors[0]
    assert sensor._temperature._value.value == "0.0°C"
    assert sensor._humidity._value.value == "0.0%"
    assert sensor._health.control.visible
    assert sensor._health._text.value == strings.SENSOR_FAULT
    assert sensor._indicator.semantics_label == strings.SENSOR_FAULT


def test_rain_start_combines_stale_fields_without_marking_the_time_fresh() -> None:
    device = _device_with_readings()
    parameters = tuple(
        replace(parameter, state=ValueState.STALE)
        if parameter.id == "rain_start_minute" else parameter
        for parameter in device.parameters
    )
    readings = GreenhouseReadings(replace(device, parameters=parameters))
    assert readings._rain_time._badge.control.visible
    assert readings._rain_time._badge._text.value == strings.STATE_STALE


def test_handled_greenhouse_values_do_not_repeat_in_generic_cards(clock) -> None:
    from conftest import load_state_fixture
    from buzsak_app.domain.snapshot import parse_snapshot
    from buzsak_app.state.store import Store
    from buzsak_app.ui.app_view import AppView
    from buzsak_app.settings import Settings

    class Page:
        def update(self) -> None:
            pass

    async def no_save(url: str, token: str) -> str | None:
        return None

    store = Store(clock)
    view = AppView(Page(), store, Settings(), clock, no_save)
    store.apply_snapshot(parse_snapshot(load_state_fixture("normal")))
    cards = view._party_tabs["valve_controller"]._sections["valve-controller"]._cards
    assert "automation_duty" not in cards
    assert "sensor_a_temperature_c" not in cards
    assert "relay4_light" not in cards


def test_mode_tap_submits_immediately_without_popup_and_keeps_reported_mode() -> None:
    page = DialogPage()
    calls = []

    async def handler(device_id, action_id, params, key, on_status):
        calls.append((device_id, action_id, dict(params)))
        on_status("pending", None, "c_mode")
        return "pending"

    panel = _controls(_device(enabled=True), page=page, handler=handler)
    event = SimpleNamespace(control=SimpleNamespace(selected=["manual"]))
    asyncio.run(panel._mode_changed(event))

    assert page.dialogs == []
    assert calls == [("valve-controller", "set_mode", {"value": "manual"})]
    assert panel._mode.selected == ["automatic"]
    assert "closes all valves" in panel._mode_hint.value.lower()
    panel.sync(_device(enabled=True, mode="manual"))
    assert panel._mode.selected == ["manual"]
    assert all(not button.disabled for _, button in panel._relay_rows.values())


def test_disabled_capability_is_rechecked_before_the_api_call() -> None:
    calls = []

    async def handler(*args):
        calls.append(args)
        return "confirmed"

    panel = _controls(_device(enabled=False), handler=handler)
    asyncio.run(panel._run("set_output", {"name": "relay1", "state": False}))
    assert calls == []
    assert panel._message.value == "Valve control disabled by server."


def test_ambiguous_submission_reuses_the_same_key_on_explicit_retry() -> None:
    calls = []

    async def handler(device_id, action_id, params, key, on_status):
        calls.append((device_id, action_id, dict(params), key))
        if len(calls) == 1:
            raise AmbiguousCommandResult("unknown result")
        on_status("confirmed")
        return "confirmed"

    panel = _controls(_device(enabled=True, mode="manual"), handler=handler)
    params = {"name": "relay1", "state": False}
    asyncio.run(panel._run("set_output", params))
    first_message = panel._message.value
    assert panel._retry.visible
    asyncio.run(panel._retry_command(None))

    assert "same request" in first_message
    assert calls[0] == calls[1]
    assert not panel._locked
    assert panel._message.value == strings.command_status("confirmed")
    assert panel._message.color == theme.tone_color(Tone.OK)


def test_uncertain_command_locks_future_controls() -> None:
    async def handler(device_id, action_id, params, key, on_status):
        on_status("uncertain", "transport_outcome_ambiguous", "c_uncertain")
        return "uncertain"

    async def check(command_id, on_status):
        assert command_id == "c_uncertain"
        on_status("confirmed", None, command_id)
        return "confirmed"

    panel = GreenhouseControls(
        _device(enabled=True, mode="manual"), page=None,
        on_command=handler, on_check_command=check)
    asyncio.run(panel._run("set_output", {"name": "relay1", "state": False}))
    assert panel._locked
    assert all(button.disabled for _, button in panel._relay_rows.values())
    assert strings.command_status("uncertain") in panel._message.value
    assert panel._message.color == theme.tone_color(Tone.WARNING)
    assert panel._check_status.visible

    asyncio.run(panel._check_command_status(None))
    assert not panel._locked
    assert not panel._check_status.visible
    assert panel._message.value == strings.command_status("confirmed")
    assert panel._message.color == theme.tone_color(Tone.OK)
