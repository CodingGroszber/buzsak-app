"""Own server, polling, and credential lifecycles for the Flet application (ARC-06, CTL-01..CTL-11)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

import flet as ft

from buzsak_app.api.client import (
    ApiError,
    ConnectionFailed,
    ServerClient,
    Unauthorized,
)
from buzsak_app.domain.clock import SystemClock
from buzsak_app.domain.alerts import AlertRule
from buzsak_app.domain.models import Device, LastPulse, Snapshot
from buzsak_app.domain.snapshot import SnapshotFormatError, parse_snapshot
from buzsak_app.settings import DEFAULT_SERVER_URL, Settings
from buzsak_app.state.poller import Poller
from buzsak_app.state.settings_repo import SettingsRepository
from buzsak_app.state.store import Store
from buzsak_app.state.token_repository import SecureTokenRepository
from buzsak_app.state.alert_repository import AlertRepository
from buzsak_app.state.alert_session import AlertSession, NotificationBridge
from buzsak_app.state.connection import ConnectionStatus, is_overdue
from buzsak_app.domain.staleness import stale_server_data_age_s
from buzsak_app.ui.android_notifications import AndroidNotifications
from buzsak_app.ui import strings
from buzsak_app.ui.app_view import AppView

logger = logging.getLogger(__name__)


def _device_from_snapshot(snapshot: Snapshot | None, device_id: str) -> Device | None:
    if snapshot is None:
        return None
    for party in snapshot.parties:
        for device in party.devices:
            if device.id == device_id:
                return device
    return None


def _is_new_pulse(pulse: LastPulse | None, baseline: datetime | None) -> bool:
    return (
        pulse is not None
        and pulse.requested_at is not None
        and (baseline is None or pulse.requested_at != baseline)
    )


class Runtime:
    """Owns the client and poller; restarts them when the server address changes (ARC-09)."""

    def __init__(
        self,
        page: ft.Page,
        repo: SettingsRepository,
        settings: Settings,
        *,
        token_repo: SecureTokenRepository | None = None,
        alert_repo: AlertRepository | None = None,
        alert_rules: tuple[AlertRule, ...] = (),
        notifications: NotificationBridge | None = None,
        preview_mode: bool = False,
        live_mode: bool = False,
    ) -> None:
        self._page = page
        self._repo = repo
        self._token_repo = token_repo
        self._alert_repo = alert_repo
        self._preview_mode = preview_mode
        self._live_mode = live_mode
        self._session_only = preview_mode or live_mode
        self.settings = settings
        self.clock = SystemClock()
        self.alert_session = AlertSession(
            self.clock, notifications or AndroidNotifications())
        self.alert_session.set_rules(alert_rules)
        self.store = Store(self.clock)
        self._create_view()
        self.store.subscribe(self._evaluate_alerts)
        self._client: ServerClient | None = None
        self._poller: Poller | None = None
        self._task: asyncio.Task | None = None
        # Kept so the task is not garbage-collected while running.
        self.ticker: asyncio.Task | None = None

    def _create_view(self) -> None:
        self.view = AppView(self._page, self.store, self.settings,
                            self.clock, self.save_connection, self.execute_command,
                            self.check_command_status, self._preview_mode,
                            self.refresh_selected_party, self._live_mode,
                            on_pulse=self.execute_pulse,
                            on_check_pulse=self.check_pulse_status,
                            on_rules=self.save_rules if self._alert_repo is not None else None)
        self.view._alerts.set_rules(self.alert_session.rules)
        self.view._alerts.refresh(self.store.state.snapshot)
        self.view._overview.refresh(self.store.state.snapshot)

    def reattach(
        self, page: ft.Page, repo: SettingsRepository,
        token_repo: SecureTokenRepository, alert_repo: AlertRepository | None,
    ) -> None:
        """Bind a new Android page without duplicating polling or rearming (NTF-03/08)."""
        self.view.dispose()
        self._page = page
        self._repo = repo
        self._token_repo = token_repo
        self._alert_repo = alert_repo
        self._create_view()
        self.alert_session.foreground()
        if self._poller is not None:
            self._poller.resume()

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
        self.alert_session.stop()
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
        """Verify and switch credentials; persist tokens only in secure storage (SEC-03, ADR-0006)."""
        try:
            token = token.strip()
            new = replace(
                self.settings, server_url=url.strip(), token=token or None)
        except ValueError:
            return strings.ERROR_BAD_URL
        await self.stop()

        if not self._session_only and token:
            if self._token_repo is None:
                self.start()
                return strings.ERROR_SECURE_STORAGE_UNAVAILABLE
            verifier = ServerClient(
                new.server_url, token=token,
                timeout_s=new.request_timeout_s,
            )
            try:
                parse_snapshot(await verifier.fetch_state())
            except Unauthorized:
                await verifier.aclose()
                self.start()
                return strings.ERROR_TOKEN_REJECTED
            except (ApiError, SnapshotFormatError):
                await verifier.aclose()
                self.start()
                return strings.ERROR_TOKEN_VERIFY
            except Exception as error:
                logger.warning(
                    "token verification failed (%s)", type(error).__name__)
                await verifier.aclose()
                self.start()
                return strings.ERROR_TOKEN_VERIFY
            await verifier.aclose()
            if not await self._token_repo.save(token):
                self.start()
                return strings.ERROR_SECURE_STORAGE_UNAVAILABLE
        elif not self._session_only and self._token_repo is not None:
            if not await self._token_repo.clear():
                self.start()
                return strings.ERROR_SECURE_STORAGE_UNAVAILABLE

        self.settings = new
        self.view.set_settings(new)
        if not self._session_only:
            await self._repo.save(new)
        self.store.reset()
        self.start()
        return None

    async def save_rules(self, rules: tuple[AlertRule, ...]) -> bool:
        """Persist definitions before applying them; delivery remains gated by NTF-12."""
        if self._alert_repo is None:
            return False
        if not await self._alert_repo.save(rules):
            return False
        self.alert_session.set_rules(rules)
        self._evaluate_alerts(self.store.state, None)
        return True

    def _evaluate_alerts(self, state, _diff) -> None:
        authenticated = bool(
            self.settings.token) and state.connection is not ConnectionStatus.UNAUTHORIZED
        trusted = (
            state.connection is ConnectionStatus.ONLINE
            and not is_overdue(state.received_at, self.clock.monotonic(), self.settings.poll_interval_s)
            and stale_server_data_age_s(state.snapshot) is None
        )
        self.alert_session.process(
            state.snapshot, authenticated=authenticated, trusted=trusted)
        self._show_monitor_status()

    def _show_monitor_status(self) -> None:
        session = self.alert_session
        status = session.bridge.status()
        if session.running:
            message = (strings.ALERT_MONITOR_ACTIVE if session.bridge.permission_granted()
                       else strings.ALERT_MONITOR_DENIED)
        elif status == "timeout":
            message = strings.ALERT_MONITOR_TIMEOUT
        elif session.blocked:
            message = strings.ALERT_MONITOR_PENDING
        else:
            message = strings.ALERT_MONITOR_STOPPED
        self.view._alerts.status.value = message

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

    async def execute_pulse(
        self,
        device_id: str,
        baseline: datetime | None,
        on_status: Callable[[str, str | None, str | None], None],
    ) -> str:
        """Submit one pulse, then observe server snapshots without retransmission (CTL-11)."""
        client = self._client
        if client is None:
            raise ConnectionFailed("server connection is not running")
        receipt = await client.request_pulse(device_id)
        request_id = str(receipt.request_id)
        on_status("sent", None, request_id)
        pulse = await self._wait_for_pulse(
            device_id, baseline, self.settings.command_timeout_s,
            on_status=on_status, request_id=request_id)
        if _is_new_pulse(pulse, baseline):
            status = pulse.status
            if status in {"succeeded", "failed", "expired"}:
                return status
            if status in {"pending", "dispatching", "sent"}:
                return status
        on_status("uncertain", "client_confirmation_timeout", request_id)
        return "uncertain"

    async def check_pulse_status(
        self,
        device_id: str,
        baseline: datetime | None,
        on_status: Callable[[str, str | None, str | None], None],
    ) -> str:
        """Explicit GET-only status check after an ambiguous pulse result (CTL-11)."""
        if self._client is None or self._poller is None:
            raise ConnectionFailed("server connection is not running")
        pulse = await self._wait_for_pulse(
            device_id, baseline, self.settings.request_timeout_s,
            on_status=on_status)
        if not _is_new_pulse(pulse, baseline):
            return "uncertain"
        return pulse.status

    async def _wait_for_pulse(
        self,
        device_id: str,
        baseline: datetime | None,
        timeout_s: float,
        *,
        on_status: Callable[[str, str | None, str | None], None] | None = None,
        request_id: str | None = None,
    ) -> LastPulse | None:
        poller = self._poller
        if poller is None:
            raise ConnectionFailed("server connection is not running")
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        last_received_at = self.store.state.received_at
        last_status: str | None = None
        first_poll_requested = False
        while loop.time() < deadline:
            event = asyncio.Event()
            unsubscribe = self.store.subscribe(
                lambda _state, _diff: event.set())
            try:
                if not first_poll_requested:
                    poller.poll_now()
                    first_poll_requested = True
                state = self.store.state
                device = _device_from_snapshot(state.snapshot, device_id)
                pulse = device.last_pulse if device is not None else None
                if _is_new_pulse(pulse, baseline):
                    if pulse.status in {"succeeded", "failed", "expired"}:
                        if on_status is not None:
                            on_status(pulse.status, pulse.error, request_id)
                        return pulse
                    if pulse.status != last_status:
                        last_status = pulse.status
                        if on_status is not None:
                            on_status(pulse.status, pulse.error, request_id)
                    if state.received_at != last_received_at:
                        last_received_at = state.received_at
                        poller.poll_now()
                elif state.received_at != last_received_at:
                    last_received_at = state.received_at
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    await asyncio.wait_for(event.wait(), min(remaining, 1.0))
                except TimeoutError:
                    pass
            finally:
                unsubscribe()
        device = _device_from_snapshot(self.store.state.snapshot, device_id)
        return device.last_pulse if device is not None else None

    def on_lifecycle(self, event: ft.AppLifecycleStateChangeEvent) -> None:
        """Keep active monitoring across UI detachment (UPD-03, NTF-03)."""
        poller = self._poller
        if poller is None:
            return
        state = event.state
        if state in (ft.AppLifecycleState.HIDE, ft.AppLifecycleState.PAUSE):
            self.view.visible = False
            if not self.alert_session.running:
                poller.pause()
        elif state in (ft.AppLifecycleState.SHOW, ft.AppLifecycleState.RESUME, ft.AppLifecycleState.RESTART):
            self.view.visible = True
            self.alert_session.foreground()
            poller.resume()
        elif state is ft.AppLifecycleState.DETACH:
            self.view.visible = False
            if not self.alert_session.running:
                poller.pause()

    async def tick_forever(self) -> None:
        while True:
            try:
                await asyncio.sleep(1)
                self.alert_session.check_service()
                self._show_monitor_status()
                if not self.view.visible and not self.alert_session.running and self._poller is not None:
                    self._poller.pause()
                if self.view.visible:
                    self.view.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("freshness tick failed")
