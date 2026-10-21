"""Synthetic PLC refill controls; never actuate hardware (CTL-12, SSOT-08)."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest
from conftest import load_state_fixture

from buzsak_app.api.client import AmbiguousCommandResult
from buzsak_app.domain.models import Capability, HealthStatus, Parameter, ValueState
from buzsak_app.domain.snapshot import parse_snapshot
from buzsak_app.ui.pump_controls import PumpControls


def device(**overrides):
    original = parse_snapshot(
        load_state_fixture("normal")).parties[0].devices[0]
    values = {
        "switch_mode": "automatic", "switch_mode_code": 1,
        "refill_button": False, "refill_active": False,
        "water_level_signal": True, "pressure_signal": True,
        "water_level_liters": 640.0, "pressure_bar": 2.8,
        "firmware": "v4.1", "ip": "192.0.2.94",
    }
    values.update(overrides)
    parameters = {parameter.id: parameter for parameter in original.parameters}
    for identifier, value in values.items():
        parameters[identifier] = Parameter(
            id=identifier, category="configuration", value=value,
            unit="L" if identifier == "water_level_liters" else "bar" if identifier == "pressure_bar" else None,
            value_type="bool" if type(value) is bool else "int" if type(value) is int
            else "float" if type(value) is float else "string",
            state=ValueState.GOOD, observed_at=original.health.last_success_at,
            last_changed_at=original.health.last_success_at, revision=1,
        )
    return replace(original, parameters=tuple(parameters.values()), capabilities=(
        Capability("refill", {}, True, None),
    ))


def panel(source=None, handler=None, lookup=None):
    return PumpControls(source or device(), page=None, on_command=handler,
                        on_check_command=lookup)


def test_fill_requires_server_capability_and_handler():
    assert panel()._fill.disabled
    assert not panel(handler=lambda *args: None)._fill.disabled
    source = device()
    source = replace(source, capabilities=(Capability(
        "refill", {}, False, "Disabled by deployment"),))
    control = panel(source, handler=lambda *args: None)
    assert control._fill.disabled
    assert control._reason.value == "Disabled by deployment"


@pytest.mark.parametrize("changes", [
    {"switch_mode_code": 0}, {"switch_mode_code": 2}, {"switch_mode_code": -1},
    {"switch_mode_code": True}, {"switch_mode": "manual"},
    {"refill_active": True}, {"refill_button": True},
    {"refill_active": None}, {"water_level_signal": False},
    {"water_level_signal": None}, {"water_level_liters": 1000.0},
    {"water_level_liters": True}, {"water_level_liters": -1.0},
    {"water_level_liters": float("nan")},
])
def test_unsafe_telemetry_disables_fill(changes):
    assert panel(device(**changes), handler=lambda *args: None)._fill.disabled


@pytest.mark.parametrize("identifier", [
    "switch_mode_code", "refill_active", "refill_button", "water_level_signal", "water_level_liters",
])
@pytest.mark.parametrize("quality", list(ValueState)[1:])
def test_noncurrent_required_telemetry_disables_fill(identifier, quality):
    source = device()
    source = replace(source, parameters=tuple(
        replace(parameter, state=quality) if parameter.id == identifier else parameter
        for parameter in source.parameters
    ))
    assert panel(source, handler=lambda *args: None)._fill.disabled


def test_disabled_or_unhealthy_device_and_wrong_schema_fail_closed():
    source = device()
    for unsafe in (
        replace(source, enabled=False),
        replace(source, health=replace(
            source.health, status=HealthStatus.DEGRADED)),
        replace(source, capabilities=()),
        replace(source, capabilities=(Capability(
            "refill", {"state": "bool"}, True, None),)),
    ):
        assert panel(unsafe, handler=lambda *args: None)._fill.disabled


def test_fill_submits_once_without_optimistic_physical_state():
    calls = []

    async def submit(device_id, action_id, params, key, on_status):
        calls.append((device_id, action_id, dict(params), key))
        assert control._fill.disabled
        assert control._device.parameter("refill_active").value is False
        on_status("confirmed", None, "refill-1")
        return "confirmed"

    control = panel(handler=submit)
    asyncio.run(control._fill.on_click(None))
    assert len(calls) == 1
    assert calls[0][:3] == ("garden-plc", "refill", {})
    assert calls[0][3]
    assert control._device.parameter("refill_active").value is False


def test_ambiguous_fill_is_locked_and_never_resent():
    calls = []

    async def submit(*args):
        calls.append(args)
        raise AmbiguousCommandResult("unknown acceptance")

    control = panel(handler=submit)
    asyncio.run(control._fill.on_click(None))
    asyncio.run(control._fill.on_click(None))
    assert len(calls) == 1
    assert control._fill.disabled
    assert not control._check_status.visible


def test_uncertain_command_offers_get_only_status_lookup():
    calls = []

    async def submit(*args):
        args[-1]("uncertain", None, "refill-1")
        return "uncertain"

    async def lookup(command_id, on_status):
        calls.append(command_id)
        on_status("confirmed", None, command_id)
        return "confirmed"

    control = panel(handler=submit, lookup=lookup)
    asyncio.run(control._fill.on_click(None))
    assert control._fill.disabled and control._check_status.visible
    asyncio.run(control._check_status.on_click(None))
    assert calls == ["refill-1"]
    assert not control._check_status.visible


def test_pump_uses_greenhouse_width_and_preserves_unknown_parameter_fallback():
    from buzsak_app.ui.party_tab import PartyTab

    source = parse_snapshot(load_state_fixture("normal")).parties[0]
    original = device()
    extra = replace(original.parameters[0], id="future_sensor", value=0)
    original = replace(original, parameters=original.parameters + (extra,))
    tab = PartyTab(replace(source, devices=(original,)))
    section = tab._sections["garden-plc"]
    assert section._pump is not None
    assert set(section._cards) == {"future_sensor"}
    assert section.control.controls[0].col == {
        "xs": 12, "md": 8, "lg": 6, "xl": 5}


def test_pump_omits_sensor_diagnostics_and_device_sections_and_uses_muted_header():
    from buzsak_app.state.diff import SnapshotDiff
    from buzsak_app.ui.party_tab import PartyTab

    source = parse_snapshot(load_state_fixture("normal")).parties[0]
    original = device()
    source = replace(source, devices=(original,))
    tab = PartyTab(source)
    section = tab._sections["garden-plc"]
    titles = [group.controls[0].value for group in section._pump.control.controls]
    assert titles == ["Pump control", "Tank and pressure", "PLC state"]
    assert not section._cards
    assert "v4.1" in section._detail.value and "192.0.2.94" in section._detail.value
    assert section._detail.visible
    updated = replace(original, parameters=tuple(
        replace(parameter, value="v4.2", state=ValueState.STALE)
        if parameter.id == "firmware" else parameter for parameter in original.parameters
    ))
    tab.apply(replace(source, devices=(updated,)), SnapshotDiff(
        structure_changed=False, changed_devices=frozenset(),
        changed_parameters=frozenset({("garden-plc", "firmware")}),
    ))
    assert "v4.2" in section._detail.value and "Stale" in section._detail.value


def test_pump_header_omits_device_name_but_preserves_identity_and_health():
    import flet as ft
    from buzsak_app.ui.party_tab import PartyTab

    source = parse_snapshot(load_state_fixture("normal")).parties[0]
    tab = PartyTab(replace(source, devices=(device(),)))
    section = tab._sections["garden-plc"]
    heading = section.control.controls[0].content.controls[0]
    assert isinstance(heading, ft.Row)
    assert len(heading.controls) == 2
    assert heading.controls[0] is section._detail
    assert heading.controls[1] is section._health.control
    assert "garden-plc" not in section._detail.value
    assert "v4.1" in section._detail.value
    assert section.device_id == "garden-plc"


def test_offline_and_overdue_snapshot_disable_fill_but_keep_readings(clock):
    from buzsak_app.settings import Settings
    from buzsak_app.state.connection import ConnectionStatus
    from buzsak_app.state.store import Store
    from buzsak_app.ui.app_view import AppView

    class Page:
        def update(self):
            pass

    store = Store(clock)
    view = AppView(Page(), store, Settings(), clock, lambda *args: None,
                   on_command=lambda *args: None)
    source = parse_snapshot(load_state_fixture("normal"))
    source = replace(source, parties=(
        replace(source.parties[0], devices=(device(),)),))
    store.apply_snapshot(source)
    control = view._party_tabs["garden_plc"]._sections["garden-plc"]._pump
    assert not control._fill.disabled
    store.apply_failure(ConnectionStatus.OFFLINE, "offline")
    assert control._fill.disabled
    assert control._readouts["pressure_bar"]._value.value == "2.80 bar"
    store.apply_snapshot(source)
    assert not control._fill.disabled
    clock.advance(30)
    view.tick()
    assert control._fill.disabled


def test_missing_required_parameter_fails_closed():
    source = device()
    source = replace(source, parameters=tuple(
        parameter for parameter in source.parameters if parameter.id != "refill_active"))
    assert panel(source, handler=lambda *args: None)._fill.disabled


def test_double_tap_while_command_is_in_flight_submits_once():
    calls = []

    async def submit(*args):
        calls.append(args)
        await control._fill.on_click(None)
        return "confirmed"

    control = panel(handler=submit)
    asyncio.run(control._fill.on_click(None))
    assert len(calls) == 1
