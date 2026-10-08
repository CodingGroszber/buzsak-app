"""Application shell and wiring: header, tabs, store updates and the poller lifecycle.

One-way flow (ARC-06): the poller feeds the store, the store notifies `AppView`, and the view
updates only the controls whose data changed (UPD-07). Tab and scroll positions survive
refreshes because controls are kept, not rebuilt (UX-05).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from dataclasses import replace
from collections.abc import Callable, Mapping
from typing import Any

import flet as ft

from buzsak_app.api.client import (
    ConnectionFailed,
    ServerClient,
)
from buzsak_app.domain.clock import Clock, SystemClock
from buzsak_app.domain.staleness import stale_server_data_age_s
from buzsak_app.settings import DEFAULT_SERVER_URL, Settings
from buzsak_app.state.connection import ConnectionStatus, age_s, is_overdue
from buzsak_app.state.diff import SnapshotDiff
from buzsak_app.state.poller import Poller
from buzsak_app.state.settings_repo import SettingsRepository
from buzsak_app.state.store import AppState, Store
from buzsak_app.ui import strings, theme
from buzsak_app.ui.components import StatusChip, centered_message, muted_text
from buzsak_app.ui.overview_tab import OverviewTab
from buzsak_app.ui.party_tab import PartyTab
from buzsak_app.ui.system_tab import SystemTab
from buzsak_app.ui.theme import SPACING, TYPE
from buzsak_app.ui.view_models import Badge, Tone, connection_view, duration_text, freshness_text
from buzsak_app.ui.greenhouse_controls import CommandHandler

logger = logging.getLogger(__name__)

_OVERVIEW, _SYSTEM = "overview", "system"
_FAKE_PREVIEW_URL = "http://127.0.0.1:8765"
_FAKE_PREVIEW_TOKEN = "fake-operator"


def _preview_settings(
    settings: Settings,
    *,
    enabled: bool,
    is_windows: bool,
    port: str | int = 8765,
) -> Settings:
    if not enabled or not is_windows:
        return settings
    try:
        preview_port = int(port)
    except (TypeError, ValueError):
        preview_port = 8765
    if not 1 <= preview_port <= 65535:
        preview_port = 8765
    return replace(
        settings,
        server_url=f"http://127.0.0.1:{preview_port}",
        token=_FAKE_PREVIEW_TOKEN,
    )


def _live_settings(
    settings: Settings,
    *,
    enabled: bool,
    is_windows: bool,
    token: str | None,
) -> Settings:
    if not enabled or not is_windows:
        return settings
    if not token:
        raise ValueError("live desktop session requires an operator token")
    return replace(settings, server_url=DEFAULT_SERVER_URL, token=token)


class AppView:
    """Owns the layout and renders each store update in place."""

    def __init__(
        self, page: ft.Page, store: Store, settings: Settings, clock: Clock,
        on_save, on_command: CommandHandler | None = None,
        on_check_command: Callable | None = None,
        preview_mode: bool = False,
        on_tab_selected: Callable[[str], None] | None = None,
        live_mode: bool = False,
    ) -> None:
        self._page = page
        self._store = store
        self._settings = settings
        self._clock = clock
        self._on_command = on_command
        self._on_check_command = on_check_command
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
        self.control = ft.Column(
            [header, self._banner, self._tabs_host], spacing=0, expand=True)

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


class Runtime:
    """Owns the client and poller; restarts them when the server address changes (ARC-09)."""

    def __init__(
        self,
        page: ft.Page,
        repo: SettingsRepository,
        settings: Settings,
        *,
        preview_mode: bool = False,
        live_mode: bool = False,
    ) -> None:
        self._page = page
        self._repo = repo
        self._preview_mode = preview_mode
        self._live_mode = live_mode
        self._session_only = preview_mode or live_mode
        self.settings = settings
        self.clock = SystemClock()
        self.store = Store(self.clock)
        self.view = AppView(page, self.store, settings,
                            self.clock, self.save_connection, self.execute_command,
                            self.check_command_status, preview_mode,
                            self.refresh_selected_party, live_mode)
        self._client: ServerClient | None = None
        self._poller: Poller | None = None
        self._task: asyncio.Task | None = None
        # Kept so the task is not garbage-collected while running.
        self.ticker: asyncio.Task | None = None

    def start(self) -> None:
        self._client = ServerClient(
            self.settings.server_url, token=self.settings.token, timeout_s=self.settings.request_timeout_s
        )
        self._poller = Poller(
            self._client.fetch_state, self.store, interval_s=self.settings.poll_interval_s)
        self._task = asyncio.create_task(self._poller.run())

    def refresh_selected_party(self, party_id: str) -> None:
        if party_id == "valve_controller" and self._poller is not None:
            self._poller.poll_now()

    async def stop(self) -> None:
        if self._poller is not None:
            self._poller.stop()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=self.settings.request_timeout_s + 1)
            except (TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        if self._client is not None:
            await self._client.aclose()
        self._client = self._poller = self._task = None

    async def save_connection(self, url: str, token: str) -> str | None:
        """Validate and switch to a new address and token; returns an error message or None.

        Only the address is persisted; the token lives in memory (SEC-03, ADR-0003).
        """
        try:
            new = replace(self.settings, server_url=url.strip(),
                          token=token.strip() or None)
        except ValueError:
            return strings.ERROR_BAD_URL
        await self.stop()
        self.settings = new
        self.view.set_settings(new)
        if not self._session_only:
            await self._repo.save(new)
        self.store.reset()
        self.start()
        return None

    async def execute_command(
        self,
        device_id: str,
        action_id: str,
        params: Mapping[str, Any],
        idempotency_key: str,
        on_status: Callable[[str, str | None, str | None], None],
    ) -> str:
        """Submit once, then poll status only; never retransmit a command (CTL-01, CTL-04)."""
        client = self._client
        if client is None:
            raise ConnectionFailed("server connection is not running")
        receipt = await client.submit_command(
            device_id,
            action_id=action_id,
            params=params,
            idempotency_key=idempotency_key,
        )
        on_status(receipt.status, None, receipt.command_id)
        if receipt.status in {"confirmed", "failed", "expired", "cancelled", "uncertain"}:
            return receipt.status

        deadline = asyncio.get_running_loop().time() + self.settings.command_timeout_s
        last_status = receipt.status
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(min(1.0, max(0.0, deadline - asyncio.get_running_loop().time())))
            status = await client.command_status(receipt.command_id)
            last_status = status.status
            on_status(last_status, status.reason, receipt.command_id)
            if last_status in {"confirmed", "failed", "expired", "cancelled", "uncertain"}:
                if last_status == "confirmed" and self._poller is not None:
                    self._poller.poll_now()
                return last_status
        on_status("uncertain", "client_confirmation_timeout",
                  receipt.command_id)
        return "uncertain"

    async def check_command_status(
        self,
        command_id: str,
        on_status: Callable[[str, str | None, str | None], None],
    ) -> str:
        """Perform one explicit status GET without resubmitting the command."""
        if self._client is None:
            raise ConnectionFailed("server connection is not running")
        status = await self._client.command_status(command_id)
        on_status(status.status, status.reason, command_id)
        if status.status == "confirmed" and self._poller is not None:
            self._poller.poll_now()
        return status.status

    def on_lifecycle(self, event: ft.AppLifecycleStateChangeEvent) -> None:
        """Pause polling in the background and resume at once on return (UPD-03)."""
        poller = self._poller
        if poller is None:
            return
        state = event.state
        if state in (ft.AppLifecycleState.HIDE, ft.AppLifecycleState.PAUSE):
            poller.pause()
        elif state in (ft.AppLifecycleState.SHOW, ft.AppLifecycleState.RESUME, ft.AppLifecycleState.RESTART):
            poller.resume()

    async def tick_forever(self) -> None:
        while True:
            try:
                await self._page.wait_until_visible()
                await asyncio.sleep(1)
                self.view.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("freshness tick failed")


async def wait_until_attached(control, timeout_s: float = 5.0) -> bool:
    """Flet attaches a service to the page only after the page was sent to the client.

    Calling it earlier raises "Control must be added to the page first".
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while True:
        try:
            control.page
            return True
        except RuntimeError:
            if loop.time() >= deadline:
                return False
            await asyncio.sleep(0.05)


async def main(page: ft.Page) -> None:
    page.title = strings.APP_TITLE
    page.padding = 0
    page.theme = theme.app_theme(dark=False)
    page.dark_theme = theme.app_theme(dark=True)
    page.theme_mode = ft.ThemeMode.SYSTEM

    # Show something first: sending the page is what attaches the storage service.
    prefs = ft.SharedPreferences()
    host = ft.SafeArea(expand=True, content=centered_message(strings.LOADING))
    page.add(host)

    repo = SettingsRepository(prefs)
    settings = Settings()
    if await wait_until_attached(prefs):
        settings = await repo.load()
    else:
        logger.warning("settings storage unavailable; using defaults")
    preview_mode = (
        os.environ.get("BUZSAK_FAKE_SERVER_PREVIEW") == "1"
        and sys.platform == "win32"
    )
    live_mode = (
        os.environ.get("BUZSAK_LIVE_SERVER_SESSION") == "1"
        and sys.platform == "win32"
    )
    if preview_mode and live_mode:
        raise RuntimeError("fake and live desktop sessions cannot be combined")
    settings = _preview_settings(
        settings,
        enabled=preview_mode,
        is_windows=sys.platform == "win32",
        port=os.environ.get("BUZSAK_FAKE_SERVER_PORT", "8765"),
    )
    settings = _live_settings(
        settings,
        enabled=live_mode,
        is_windows=sys.platform == "win32",
        token=os.environ.get("BUZSAK_LIVE_SERVER_TOKEN"),
    )
    runtime = Runtime(
        page, repo, settings, preview_mode=preview_mode, live_mode=live_mode,
    )
    page.on_app_lifecycle_state_change = runtime.on_lifecycle
    host.content = runtime.view.control
    page.update()
    runtime.start()
    runtime.ticker = asyncio.create_task(runtime.tick_forever())
