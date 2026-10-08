"""System tab: connection facts and the server address editor (UX-04, ARC-09)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from importlib.metadata import PackageNotFoundError, version

import flet as ft

from buzsak_app.settings import Settings
from buzsak_app.state.connection import age_s
from buzsak_app.state.store import AppState
from buzsak_app.ui import strings
from buzsak_app.ui.components import muted_text, section_title
from buzsak_app.ui.theme import RADIUS, SPACING, TYPE
from buzsak_app.ui.view_models import connection_view, freshness_text

# Takes the address and the token; returns an error message to show, or None when accepted.
SaveConnection = Callable[[str, str], Awaitable[str | None]]


def app_version() -> str:
    # Not installed as a distribution inside a packaged APK; B-303 will give it a proper source.
    try:
        return version("buzsak-app")
    except PackageNotFoundError:
        return strings.VALUE_MISSING


class SystemTab:
    def __init__(self, settings: Settings, on_save: SaveConnection) -> None:
        self._on_save = on_save
        self._values: dict[str, ft.Text] = {}
        rows = [self._row(key) for key in (
            strings.SYSTEM_SERVER,
            strings.SYSTEM_STATUS,
            strings.SYSTEM_UPDATED,
            strings.SYSTEM_GENERATED,
            strings.SYSTEM_ISSUES,
            strings.SYSTEM_ERROR,
            strings.SYSTEM_POLL,
            strings.SYSTEM_VERSION,
        )]
        self._url = ft.TextField(
            label=strings.SYSTEM_SERVER,
            value=settings.server_url,
            keyboard_type=ft.KeyboardType.URL,
            dense=True,
            on_submit=self._save,
        )
        # Populated from native secure storage; never placed in ordinary preferences (SEC-03, ADR-0006).
        self._token = ft.TextField(
            label=strings.SYSTEM_TOKEN,
            value=settings.token or "",
            password=True,
            can_reveal_password=True,
            dense=True,
            on_submit=self._save,
        )
        self._message = muted_text()
        facts = ft.Container(
            content=ft.Column(rows, spacing=SPACING.sm),
            padding=ft.Padding.all(SPACING.md),
            border_radius=ft.BorderRadius.all(RADIUS.card),
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
        )
        editor = ft.Column(
            [
                section_title(strings.SYSTEM_SERVER),
                self._url,
                self._token,
                muted_text(strings.SYSTEM_TOKEN_NOTE),
                ft.Row(
                    [
                        ft.FilledButton(strings.SYSTEM_SAVE,
                                        on_click=self._save),
                        ft.TextButton(strings.SYSTEM_SIGN_OUT,
                                      on_click=self._sign_out),
                        self._message,
                    ],
                    wrap=True,
                ),
            ],
            spacing=SPACING.sm,
        )
        self.control = ft.Container(
            content=ft.Column([facts, editor], spacing=SPACING.lg,
                              scroll=ft.ScrollMode.AUTO, expand=True),
            padding=ft.Padding.all(SPACING.md),
            expand=True,
        )

    def _row(self, key: str) -> ft.Control:
        value = ft.Text(strings.VALUE_MISSING, size=TYPE.body, weight=ft.FontWeight.W_600, selectable=True,
                        text_align=ft.TextAlign.END)
        self._values[key] = value
        return ft.Row(
            [muted_text(key, TYPE.body), ft.Container(
                value, expand=True, alignment=ft.Alignment.CENTER_RIGHT)],
            spacing=SPACING.sm,
        )

    async def _save(self, _: ft.Event) -> None:
        token = self._token.value or ""
        error = await self._on_save(self._url.value or "", token)
        self._message.value = error or (
            strings.SYSTEM_SAVED if token.strip() else strings.SYSTEM_SIGNED_OUT)

    async def _sign_out(self, _: ft.Event) -> None:
        error = await self._on_save(self._url.value or "", "")
        self._message.value = error or strings.SYSTEM_SIGNED_OUT
        if error is None:
            self._token.value = ""

    def refresh(self, state: AppState, now: float, settings: Settings) -> None:
        values = self._values
        values[strings.SYSTEM_SERVER].value = settings.server_url
        values[strings.SYSTEM_STATUS].value = connection_view(
            state.connection).text
        values[strings.SYSTEM_UPDATED].value = freshness_text(
            age_s(state.received_at, now))
        snapshot = state.snapshot
        values[strings.SYSTEM_GENERATED].value = (
            snapshot.generated_at.astimezone().strftime(
                "%H:%M:%S") if snapshot else strings.VALUE_MISSING
        )
        values[strings.SYSTEM_ISSUES].value = str(
            len(snapshot.issues)) if snapshot else strings.VALUE_MISSING
        values[strings.SYSTEM_ERROR].value = state.error or strings.VALUE_MISSING
        values[strings.SYSTEM_POLL].value = strings.seconds_text(
            settings.poll_interval_s)
        values[strings.SYSTEM_VERSION].value = app_version()
