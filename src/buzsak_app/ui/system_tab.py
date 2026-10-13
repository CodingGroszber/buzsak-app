"""System tab: read-only connection diagnostics (UX-04)."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

import flet as ft

from buzsak_app.settings import Settings
from buzsak_app.state.connection import age_s
from buzsak_app.state.store import AppState
from buzsak_app.ui import strings
from buzsak_app.ui.components import muted_text
from buzsak_app.ui.theme import RADIUS, SPACING, TYPE
from buzsak_app.ui.view_models import connection_view, freshness_text


def app_version() -> str:
    # Not installed as a distribution inside a packaged APK; B-303 will give it a proper source.
    try:
        return version("buzsak-app")
    except PackageNotFoundError:
        return strings.VALUE_MISSING


class SystemTab:
    def __init__(self) -> None:
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
        facts = ft.Container(
            content=ft.Column(rows, spacing=SPACING.sm),
            padding=ft.Padding.all(SPACING.md),
            border_radius=ft.BorderRadius.all(RADIUS.card),
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
        )
        self.control = ft.Container(
            content=ft.Column([facts], spacing=SPACING.lg,
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
