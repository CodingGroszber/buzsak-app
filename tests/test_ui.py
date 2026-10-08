"""Controls build and update in place against the pinned Flet (UPD-07, UX-01, UX-05, ARC-02)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import flet as ft
from conftest import load_state_fixture

from buzsak_app.domain.snapshot import parse_snapshot
from buzsak_app.settings import DEFAULT_SERVER_URL, Settings
from buzsak_app.state.connection import ConnectionStatus
from buzsak_app.state.store import Store
from buzsak_app.ui import strings, theme
from buzsak_app.ui.app import AppView, _live_settings, _preview_settings
from buzsak_app.ui.components import KpiCard
from buzsak_app.ui.command_visuals import pulse_button_visual
from buzsak_app.ui.party_tab import PartyTab
from buzsak_app.ui.view_models import Tone, kpi_view


class StubPage:
    """The only page API AppView uses."""

    def __init__(self) -> None:
        self.updates = 0

    def update(self) -> None:
        self.updates += 1


async def _no_save(url: str, token: str) -> str | None:
    return None


def _snapshot(name="normal"):
    return parse_snapshot(load_state_fixture(name))


def _view(clock):
    store = Store(clock)
    page = StubPage()
    return AppView(page, store, Settings(), clock, _no_save), store, page


def test_fake_preview_settings_are_seeded_only_when_explicitly_enabled() -> None:
    real_settings = Settings(token="real-token")
    assert _preview_settings(real_settings, enabled=False,
                             is_windows=True) == real_settings
    assert _preview_settings(real_settings, enabled=True,
                             is_windows=False) == real_settings

    preview = _preview_settings(real_settings, enabled=True, is_windows=True)
    assert preview.server_url == "http://127.0.0.1:8765"
    assert preview.token == "fake-operator"
    assert "token" not in preview.to_storage()
    assert real_settings.token == "real-token"


def test_preview_mode_is_visibly_marked_as_simulated(clock) -> None:
    view = AppView(
        StubPage(), Store(clock), Settings(), clock, _no_save,
        preview_mode=True,
    )
    assert view._simulation.control.visible
    assert view._simulation._text.value == strings.SIMULATION_LABEL


def test_live_session_uses_operator_token_only_in_memory_and_is_badged(clock) -> None:
    base = Settings(server_url="http://127.0.0.1:8766")
    live = _live_settings(
        base, enabled=True, is_windows=True, token="operator-token")
    assert live.server_url == DEFAULT_SERVER_URL
    assert live.token == "operator-token"
    assert "token" not in live.to_storage()

    view = AppView(
        StubPage(), Store(clock), live, clock, _no_save, live_mode=True)
    assert view._live.control.visible
    assert view._live._text.value == strings.LIVE_SERVER_LABEL


def test_live_session_is_not_enabled_without_explicit_windows_flag() -> None:
    settings = Settings()
    assert _live_settings(
        settings, enabled=False, is_windows=True, token="secret") == settings
    assert _live_settings(
        settings, enabled=True, is_windows=False, token="secret") == settings


def test_fake_preview_uses_selected_available_port() -> None:
    preview = _preview_settings(
        Settings(), enabled=True, is_windows=True, port="8766")
    assert preview.server_url == "http://127.0.0.1:8766"


def test_invalid_fake_preview_port_falls_back_to_default() -> None:
    preview = _preview_settings(
        Settings(), enabled=True, is_windows=True, port="65536")
    assert preview.server_url == "http://127.0.0.1:8765"


def _tab_titles(view: AppView) -> list[str]:
    bar = view._tabs.content.controls[0]
    return [t.label for t in bar.tabs]


def _cards(party_tab: PartyTab) -> dict[str, KpiCard]:
    """Cards of the first device of a party tab, keyed by parameter id."""
    return next(iter(party_tab._sections.values()))._cards


def _with_pressure(**changes) -> object:
    payload = load_state_fixture("normal")
    payload["parties"][0]["devices"][0]["parameters"][1].update(**changes)
    return parse_snapshot(payload)


def test_themes_are_material3_with_the_accent_and_distinct_warning_colours() -> None:
    light, dark = theme.app_theme(dark=False), theme.app_theme(dark=True)
    assert light.use_material3 and dark.use_material3
    assert light.color_scheme_seed == dark.color_scheme_seed == theme.ACCENT
    assert light.color_scheme.tertiary == theme.WARNING_LIGHT
    assert dark.color_scheme.tertiary == theme.WARNING_DARK


def test_every_tone_has_a_colour() -> None:
    assert all(theme.tone_color(t) for t in Tone)


def test_kpi_card_updates_in_place() -> None:
    device = _snapshot().parties[0].devices[0]
    card = KpiCard()
    card.update_from(kpi_view(device, device.parameter("pressure_bar")))
    assert card._value.value == "2.80"
    assert card._unit.value == "bar"
    assert card._label.value == "PRESSURE"
    assert card._body.opacity == 1.0

    degraded = _snapshot("degraded").parties[0].devices[0]
    card.update_from(kpi_view(degraded, degraded.parameter("pressure_bar")))
    assert card._badge.control.visible
    assert card._body.opacity == theme.DIMMED_OPACITY
    assert card.control.tooltip  # long-press details (DATA-04)


def test_kpi_card_hides_empty_unit_badge_and_caption() -> None:
    device = _snapshot().parties[1].devices[0]
    card = KpiCard()
    card.update_from(kpi_view(device, device.parameter("relay2_rain")))
    assert card._value.value == strings.VALUE_OFF
    assert not card._value_row.controls[1].visible
    assert not card._badge.control.visible
    assert not card._caption.visible


def test_app_shows_only_overview_and_system_before_any_data(clock) -> None:
    view, _, _ = _view(clock)
    assert _tab_titles(view) == [strings.TAB_OVERVIEW, strings.TAB_SYSTEM]


def test_tabs_follow_the_servers_parties_in_order(clock) -> None:
    view, store, page = _view(clock)
    store.apply_snapshot(_snapshot())
    assert _tab_titles(view) == ["Overview", "Pump",
                                 "Greenhouse", "Garage", "System"]
    assert page.updates == 1


def test_entering_greenhouse_requests_an_immediate_snapshot(clock) -> None:
    selected = []
    store = Store(clock)
    view = AppView(
        StubPage(), store, Settings(), clock, _no_save,
        on_tab_selected=selected.append,
    )
    store.apply_snapshot(_snapshot())

    view._on_tab_change(SimpleNamespace(
        data=str(view._tab_keys.index("valve_controller"))))

    assert selected == ["valve_controller"]


def test_selecting_greenhouse_requests_an_immediate_server_snapshot(clock) -> None:
    calls = []
    store = Store(clock)
    view = AppView(
        StubPage(), store, Settings(), clock, _no_save,
        on_tab_selected=calls.append,
    )
    store.apply_snapshot(_snapshot())

    view._on_tab_change(SimpleNamespace(
        data=str(view._tab_keys.index("valve_controller"))))

    assert calls == ["valve_controller"]


def test_a_party_tab_has_a_card_for_every_parameter(clock) -> None:
    view, store, _ = _view(clock)
    store.apply_snapshot(_snapshot())
    pump = _cards(view._party_tabs["garden_plc"])
    assert set(pump) == {
        p.id for p in _snapshot().parties[0].devices[0].parameters}


def test_value_change_updates_the_existing_card_not_a_new_one(clock) -> None:
    view, store, _ = _view(clock)
    store.apply_snapshot(_snapshot())
    before = _cards(view._party_tabs["garden_plc"])["pressure_bar"]
    assert before._value.value == "2.80"

    store.apply_snapshot(_with_pressure(value="3.10", revision=1524))

    after = _cards(view._party_tabs["garden_plc"])["pressure_bar"]
    assert after is before
    assert after._value.value == "3.10"


def test_unchanged_cards_are_left_alone(clock) -> None:
    view, store, _ = _view(clock)
    store.apply_snapshot(_snapshot())
    cards = _cards(view._party_tabs["garden_plc"])
    # would be overwritten by a refresh
    cards["tank_pump"]._value.value = "sentinel"

    store.apply_snapshot(_with_pressure(value="3.10", revision=1524))
    assert cards["tank_pump"]._value.value == "sentinel"


def test_mode_change_refreshes_the_automation_cards(clock) -> None:
    view, store, _ = _view(clock)
    store.apply_snapshot(_snapshot())
    readings = view._party_tabs["valve_controller"]._sections[
        "valve-controller"]._greenhouse._readings
    assert not readings._mode_badge.control.visible
    assert readings._mist_panel.opacity == 1.0

    payload = load_state_fixture("normal")
    mode = next(p for p in payload["parties"][1]
                ["devices"][0]["parameters"] if p["id"] == "mode")
    mode.update(value="manual", revision=2)
    store.apply_snapshot(parse_snapshot(payload))

    assert readings._mode_badge.control.visible
    assert readings._mist_panel.opacity < 1.0
    assert readings._rain_panel.opacity < 1.0


def test_selected_tab_survives_a_structure_change(clock) -> None:
    view, store, _ = _view(clock)
    store.apply_snapshot(_snapshot())
    view._selected_key = "valve_controller"
    payload = load_state_fixture("normal")
    # a device disappears: structure changes
    payload["parties"][2]["devices"].pop()
    store.apply_snapshot(parse_snapshot(payload))
    assert view._tabs.selected_index == view._tab_keys.index(
        "valve_controller")


def test_selected_tab_falls_back_to_overview_after_a_reset(clock) -> None:
    view, store, _ = _view(clock)
    store.apply_snapshot(_snapshot())
    view._selected_key = "matter"
    store.reset()
    assert view._selected_key == "overview"
    assert _tab_titles(view) == [strings.TAB_OVERVIEW, strings.TAB_SYSTEM]


def test_offline_shows_a_banner_and_keeps_the_data_on_screen(clock) -> None:
    view, store, _ = _view(clock)
    store.apply_snapshot(_snapshot())
    assert not view._banner.visible
    store.apply_failure(ConnectionStatus.OFFLINE, "server unreachable")
    assert view._banner.visible
    assert view._banner_text.value == strings.BANNER_STALE_DATA
    assert "pressure_bar" in _cards(view._party_tabs["garden_plc"])
    store.apply_snapshot(_snapshot())
    assert not view._banner.visible


def test_offline_before_any_data_shows_the_error(clock) -> None:
    view, store, _ = _view(clock)
    store.apply_failure(ConnectionStatus.OFFLINE, "server unreachable")
    assert view._banner.visible
    assert view._banner_text.value == "server unreachable"


def test_a_missing_token_before_any_data_tells_the_user_where_to_enter_it(clock) -> None:
    view, store, _ = _view(clock)
    store.apply_failure(ConnectionStatus.UNAUTHORIZED,
                        "access token missing or invalid")
    assert view._banner.visible
    assert view._banner_text.value == strings.BANNER_UNAUTHORIZED


def test_the_token_field_is_masked_and_saved_with_the_address(clock) -> None:
    saved = []

    async def save(url: str, token: str) -> str | None:
        saved.append((url, token))
        return None

    store = Store(clock)
    view = AppView(StubPage(), store, Settings(token="s3cret"), clock, save)
    field = view._system._token
    assert field.password and field.can_reveal_password
    assert field.value == "s3cret"

    field.value = "new-token"
    asyncio.run(view._system._save(None))
    assert saved == [(Settings().server_url, "new-token")]


def test_sign_out_clears_the_token_field_and_reports_removal(clock) -> None:
    saved = []

    async def save(url: str, token: str) -> str | None:
        saved.append((url, token))
        return None

    view = AppView(
        StubPage(), Store(clock), Settings(token="saved-token"), clock, save)
    asyncio.run(view._system._sign_out(None))

    assert saved == [(Settings().server_url, "")]
    assert view._system._token.value == ""
    assert view._system._message.value == strings.SYSTEM_SIGNED_OUT


def test_freshness_moves_with_the_clock_and_warns_when_overdue(clock) -> None:
    view, store, _ = _view(clock)
    store.apply_snapshot(_snapshot())
    assert view._freshness._text.value == "Updated 0 s ago"
    clock.advance(5)
    view.tick()
    assert view._freshness._text.value == "Updated 5 s ago"
    assert view._freshness._icon.icon != ft.Icons.WARNING_AMBER
    clock.advance(2)  # 7 s is more than 3 x the 2 s poll interval
    view.tick()
    assert view._freshness._icon.icon == ft.Icons.WARNING_AMBER


def test_overview_has_a_card_per_party_and_system_shows_the_connection(clock) -> None:
    view, store, _ = _view(clock)
    store.apply_snapshot(_snapshot())
    assert len(view._overview._column.controls) == 3
    values = view._system._values
    assert values[strings.SYSTEM_STATUS].value == strings.CONN_ONLINE
    assert values[strings.SYSTEM_SERVER].value == Settings().server_url
    assert values[strings.SYSTEM_ISSUES].value == "0"


def test_overview_tapping_a_party_selects_its_tab(clock) -> None:
    view, store, _ = _view(clock)
    store.apply_snapshot(_snapshot())
    calls = []

    async def fake_move_to(index):
        calls.append(index)

    view._tabs.move_to = fake_move_to
    asyncio.run(view.select_party("valve_controller"))
    assert view._selected_key == "valve_controller"
    assert calls == [view._tab_keys.index("valve_controller")]
    asyncio.run(view.select_party("nope"))  # unknown party is ignored
    assert len(calls) == 1


def test_unconfigured_party_tab_explains_itself() -> None:
    party = _snapshot("matter_unconfigured").parties[2]
    assert PartyTab(party).control.content.value == party.note


def test_a_party_without_devices_says_so() -> None:
    tab = PartyTab(_snapshot("matter_unconfigured").parties[0])
    assert tab.control.content.value == strings.PARTY_NO_DEVICES


def test_garage_has_compact_trigger_rows_for_both_devices() -> None:
    party = next(p for p in _snapshot().parties if p.kind == "matter")
    left = next(device for device in party.devices if device.id == "sonoff-2")
    right = next(device for device in party.devices if device.id == "sonoff-1")

    async def pulse(_device_id, _baseline, _on_status):
        return "succeeded"

    tab = PartyTab(party, on_pulse=pulse, on_check_pulse=pulse)
    left_control = tab._garage_controls["sonoff-2"]
    right_control = tab._garage_controls["sonoff-1"]

    assert pulse_button_visual(left).label == strings.GARAGE_TRIGGER
    assert pulse_button_visual(right).label == strings.GARAGE_TRIGGER
    assert left_control._label.value == strings.GARAGE_LEFT
    assert right_control._label.value == strings.GARAGE_RIGHT
    assert left_control._button.content == strings.GARAGE_TRIGGER
    assert right_control._button.content == strings.GARAGE_TRIGGER
    assert not left_control._button.disabled
    assert not right_control._button.disabled
    assert left_control._relay._text.value == strings.GARAGE_RELAY_INACTIVE
    assert right_control._relay._text.value == strings.GARAGE_RELAY_INACTIVE
    assert not left_control._message.visible
    assert not right_control._message.visible


def test_garage_triggers_are_disabled_without_handlers() -> None:
    party = next(p for p in _snapshot().parties if p.kind == "matter")
    tab = PartyTab(party)

    assert tab._garage_controls["sonoff-1"]._button.disabled
    assert tab._garage_controls["sonoff-2"]._button.disabled
