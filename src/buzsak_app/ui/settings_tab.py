"""User-editable connection settings (UX-01, UX-04, ARC-09)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import flet as ft

from buzsak_app.settings import Settings
from buzsak_app.ui import strings
from buzsak_app.ui.components import muted_text, section_title
from buzsak_app.ui.theme import SPACING

SaveConnection = Callable[[str, str], Awaitable[str | None]]


class SettingsTab:
    def __init__(self, settings: Settings, on_save: SaveConnection) -> None:
        self._on_save = on_save
        self._url = ft.TextField(
            label=strings.SYSTEM_SERVER, value=settings.server_url,
            keyboard_type=ft.KeyboardType.URL, dense=True, on_submit=self._save,
        )
        self._token = ft.TextField(
            label=strings.SYSTEM_TOKEN, value=settings.token or "",
            password=True, can_reveal_password=True, dense=True, on_submit=self._save,
        )
        self._message = muted_text()
        self._extras = ft.Column(spacing=SPACING.md)
        self.control = ft.Container(
            content=ft.Column([
                section_title(strings.SYSTEM_SERVER), self._url, self._token,
                muted_text(strings.SYSTEM_TOKEN_NOTE),
                ft.Row([
                    ft.FilledButton(strings.SYSTEM_SAVE, on_click=self._save),
                    ft.TextButton(strings.SYSTEM_SIGN_OUT,
                                  on_click=self._sign_out),
                    self._message,
                ], wrap=True), self._extras,
            ], spacing=SPACING.sm, scroll=ft.ScrollMode.AUTO, expand=True),
            padding=ft.Padding.all(SPACING.md), expand=True,
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
