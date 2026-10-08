"""Load and save settings through any async key-value store (ARC-09, SEC-03).

Flet's `SharedPreferences` fits `KeyValueStore`, so the UI layer passes it in and this
module stays free of Flet. Storage problems fall back to defaults and never crash startup.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Protocol

from buzsak_app.settings import Settings

logger = logging.getLogger(__name__)

SETTINGS_KEY = "buzsak.settings"
# A store that never answers must not block startup or saving; Flet's own wait is 10 s.
STORAGE_TIMEOUT_S = 3.0


class KeyValueStore(Protocol):
    async def get(self, key: str) -> object: ...

    async def set(self, key: str, value: str) -> bool: ...


class SettingsRepository:
    def __init__(self, store: KeyValueStore, *, timeout_s: float = STORAGE_TIMEOUT_S) -> None:
        self._store = store
        self._timeout_s = timeout_s

    async def load(self) -> Settings:
        try:
            raw = await asyncio.wait_for(self._store.get(SETTINGS_KEY), self._timeout_s)
            if raw is None:
                return Settings()
            data = json.loads(raw) if isinstance(raw, str) else None
        except Exception as error:
            # Storage errors never carry server data, so the message is safe to log and aids diagnosis.
            logger.warning("could not read stored settings: %r", error)
            return Settings()
        return Settings.from_storage(data) if isinstance(data, dict) else Settings()

    async def save(self, settings: Settings) -> bool:
        """Persist everything except the token; returns whether the write succeeded."""
        try:
            payload = json.dumps(settings.to_storage())
            return bool(await asyncio.wait_for(self._store.set(SETTINGS_KEY, payload), self._timeout_s))
        except Exception as error:
            logger.warning("could not store settings: %r", error)
            return False
