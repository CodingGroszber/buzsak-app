"""Flet application shell and snapshot-driven tab rendering (UX-01, ARC-06)."""

from __future__ import annotations

import logging
from collections.abc import Callable

import flet as ft

from buzsak_app.domain.clock import Clock
from buzsak_app.domain.staleness import stale_server_data_age_s
from buzsak_app.settings import Settings
from buzsak_app.state.connection import ConnectionStatus, age_s, is_overdue
from buzsak_app.state.diff import SnapshotDiff
from buzsak_app.state.store import AppState, Store
from buzsak_app.ui import strings, theme
from buzsak_app.ui.components import StatusChip, centered_message, muted_text
from buzsak_app.ui.garage_controls import PulseHandler, PulseLookup
from buzsak_app.ui.greenhouse_controls import CommandHandler
from buzsak_app.ui.overview_tab import OverviewTab
from buzsak_app.ui.party_tab import PartyTab
from buzsak_app.ui.system_tab import SystemTab
from buzsak_app.ui.theme import SPACING, TYPE
from buzsak_app.ui.view_models import (
    Badge,
    Tone,
    connection_view,
    duration_text,
    freshness_text,
)

logger = logging.getLogger(__name__)

_OVERVIEW, _SYSTEM = "overview", "system"


class AppView:
    """Owns the layout and renders each store update in place."""

    def __init__(
        self, page: ft.Page, store: Store, settings: Settings, clock: Clock,
        on_save, on_command: CommandHandler | None = None,
        on_check_command: Callable | None = None,
        preview_mode: bool = False,
        on_tab_selected: Callable[[str], None] | None = None,
        live_mode: bool = False,
        on_pulse: PulseHandler | None = None,
        on_check_pulse: PulseLookup | None = None,
    ) -> None:
        self._page = page
        self._store = store
        self._settings = settings
        self._clock = clock
        self._on_command = on_command
        self._on_check_command = on_check_command
        self._on_pulse = on_pulse
        self._on_check_pulse = on_check_pulse
        self._on_tab_selected = on_tab_selected
        self._simulation = StatusChip(
            strings.SIMULATION_LABEL, "science", Tone.WARNING)
        self._simulation.control.visible = preview_mode
        self._live = StatusChip(
            strings.LIVE_SERVER_LABEL, "sensors", Tone.WARNING)
        self._live.control.visible = live_mode
        self._party_tabs: dict[str, PartyTab] = {}
        self._tab_keys: list[str] = []
        self._selected_key = _OVERVIEW

        self._connection = StatusChip()
        self._freshness = StatusChip()
        self._banner_text = ft.Text(size=TYPE.caption, expand=True)
        self._banner_chip = StatusChip()
        self._banner = ft.Container(
            content=ft.Row([self._banner_chip.control,
                           self._banner_text], spacing=SPACING.sm),
            padding=ft.Padding.symmetric(
                horizontal=SPACING.md, vertical=SPACING.sm),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            visible=False,
        )
        self._overview = OverviewTab(self.select_party)
        self._system = SystemTab(settings, on_save)
        self._tabs: ft.Tabs | None = None
        self._tabs_host = ft.Container(expand=True)

        header = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(strings.APP_TITLE, size=TYPE.title + 2,
                                    weight=ft.FontWeight.BOLD, expand=True),
                            self._simulation.control,
                            self._live.control,
                            self._connection.control,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self._freshness.control,
                ],
                spacing=SPACING.xs,
            ),
            padding=ft.Padding.only(
                left=SPACING.md, right=SPACING.md, top=SPACING.sm),
        )
        self._watermark = ft.Container(
            content=ft.Image(
                src="assets/app_logo_transparent.png",
                width=300,
                height=300,
                fit=ft.BoxFit.CONTAIN,
                exclude_from_semantics=True,
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
            opacity=0.5,
            ignore_interactions=True,
        )
        self.control = ft.Stack(
            controls=[
                self._watermark,
                ft.Column(
                    [header, self._banner, self._tabs_host],
                    spacing=0,
                    expand=True,
                ),
            ],
            alignment=ft.Alignment.CENTER,
            fit=ft.StackFit.EXPAND,
            expand=True,
        )

        self._rebuild_tabs()
        self.render_status(store.state)
        self._system.refresh(store.state, clock.monotonic(), settings)
        store.subscribe(self.on_store_update)

    def set_settings(self, settings: Settings) -> None:
        self._settings = settings

    # Store updates

    def on_store_update(self, state: AppState, diff: SnapshotDiff) -> None:
        snapshot = state.snapshot
        if diff.structure_changed:
            self._rebuild_tabs()
        elif snapshot is not None:
            for party in snapshot.parties:
                tab = self._party_tabs.get(party.id)
                if tab is not None:
                    tab.apply(party, diff)
        if not diff.is_empty:
            self._overview.refresh(snapshot)
        self.render_status(state)
        self._system.refresh(state, self._clock.monotonic(), self._settings)
        self._page.update()

    def tick(self) -> None:
        """Once a second: the "updated N s ago" text moves even when no data arrives (UPD-06)."""
        state = self._store.state
        self.render_status(state)
        self._system.refresh(state, self._clock.monotonic(), self._settings)
        self._page.update()

    def render_status(self, state: AppState) -> None:
        conn = connection_view(state.connection)
        self._connection.set(conn.text, conn.icon, conn.tone)

        now = self._clock.monotonic()
        overdue = is_overdue(state.received_at, now,
                             self._settings.poll_interval_s)
        self._freshness.set(
            freshness_text(age_s(state.received_at, now)),
            "warning_amber" if overdue else "schedule",
            Tone.WARNING if overdue else Tone.MUTED,
        )

        # A connection problem outranks old server data; both warn that values are not live.
        server_age = stale_server_data_age_s(state.snapshot)
        if conn.show_banner:
            self._banner_chip.set_badge(Badge(conn.text, conn.icon, conn.tone))
            if state.snapshot is not None:
                text = strings.BANNER_STALE_DATA
            elif state.connection is ConnectionStatus.UNAUTHORIZED:
                text = strings.BANNER_UNAUTHORIZED
            else:
                text = state.error or ""
            self._banner_text.value = text
            self._banner.visible = True
        elif server_age is not None:
            self._banner_chip.set_badge(
                Badge(strings.STALE_SERVER_TITLE, "history", Tone.WARNING))
            self._banner_text.value = strings.stale_server_note(
                duration_text(server_age))
            self._banner.visible = True
        else:
            self._banner.visible = False

    # Tabs

    def _rebuild_tabs(self) -> None:
        snapshot = self._store.state.snapshot
        entries: list[tuple[str, str, ft.Control]] = [
            (_OVERVIEW, strings.TAB_OVERVIEW, self._overview.control)]
        self._party_tabs = {}
        if snapshot is not None:
            for party in snapshot.parties:
                tab = PartyTab(
                    party, page=self._page, on_command=self._on_command,
                    on_check_command=self._on_check_command,
                    on_pulse=self._on_pulse,
                    on_check_pulse=self._on_check_pulse,
                )
                self._party_tabs[party.id] = tab
                entries.append((party.id, strings.party_title(
                    party.id, party.label), tab.control))
        entries.append((_SYSTEM, strings.TAB_SYSTEM, self._system.control))

        self._tab_keys = [key for key, _, _ in entries]
        index = self._tab_keys.index(
            self._selected_key) if self._selected_key in self._tab_keys else 0
        self._selected_key = self._tab_keys[index]
        self._tabs = ft.Tabs(
            length=len(entries),
            selected_index=index,
            expand=True,
            on_change=self._on_tab_change,
            content=ft.Column(
                expand=True,
                spacing=0,
                controls=[
                    ft.TabBar(tabs=[ft.Tab(label=title)
                              for _, title, _ in entries]),
                    ft.TabBarView(expand=True, controls=[
                                  control for _, _, control in entries]),
                ],
            ),
        )
        self._tabs_host.content = self._tabs

    def _on_tab_change(self, e: ft.Event) -> None:
        try:
            self._selected_key = self._tab_keys[int(e.data)]
            if self._on_tab_selected is not None:
                self._on_tab_selected(self._selected_key)
        except (TypeError, ValueError, IndexError):
            logger.warning("unexpected tab change event")

    async def select_party(self, party_id: str) -> None:
        if self._tabs is not None and party_id in self._tab_keys:
            self._selected_key = party_id
            if self._on_tab_selected is not None:
                self._on_tab_selected(party_id)
            await self._tabs.move_to(self._tab_keys.index(party_id))
