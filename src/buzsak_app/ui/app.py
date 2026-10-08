"""Flet composition root: attach platform services, construct Runtime and start the app (BLD-01)."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from dataclasses import replace

import flet as ft
import flet_secure_storage as fss

from buzsak_app.settings import DEFAULT_SERVER_URL, Settings
from buzsak_app.state.settings_repo import SettingsRepository
from buzsak_app.state.token_repository import SecureTokenRepository
from buzsak_app.ui import strings, theme
from buzsak_app.ui.components import centered_message
from buzsak_app.ui.runtime import Runtime

logger = logging.getLogger(__name__)

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

    # Show something first: sending the page is what attaches each storage service.
    prefs = ft.SharedPreferences()
    secure_storage = fss.SecureStorage(
        android_options=fss.AndroidOptions(
            reset_on_error=False,
            migrate_on_algorithm_change=True,
        )
    )
    host = ft.SafeArea(expand=True, content=centered_message(strings.LOADING))
    page.add(host)

    repo = SettingsRepository(prefs)
    token_repo = SecureTokenRepository(secure_storage)
    settings = Settings()
    prefs_ready, secure_storage_ready = await asyncio.gather(
        wait_until_attached(prefs),
        wait_until_attached(secure_storage),
    )
    if prefs_ready:
        settings = await repo.load()
    else:
        logger.warning("settings storage unavailable; using defaults")
    if secure_storage_ready and not (preview_mode or live_mode):
        settings = replace(settings, token=await token_repo.load())
    elif not secure_storage_ready and not (preview_mode or live_mode):
        logger.warning(
            "secure credential storage unavailable; sign-in required")
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
        page, repo, settings, token_repo=token_repo,
        preview_mode=preview_mode, live_mode=live_mode,
    )
    page.on_app_lifecycle_state_change = runtime.on_lifecycle
    host.content = runtime.view.control
    page.update()
    runtime.start()
    runtime.ticker = asyncio.create_task(runtime.tick_forever())
