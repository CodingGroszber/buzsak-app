"""Persist the bearer token only through the platform's secure credential store (SEC-03)."""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

logger = logging.getLogger(__name__)

TOKEN_KEY = "buzsak.operator-token"
TOKEN_STORAGE_TIMEOUT_S = 5.0


class SecureTokenStore(Protocol):
    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str) -> None: ...

    async def remove(self, key: str) -> None: ...


class SecureTokenRepository:
    def __init__(
        self,
        store: SecureTokenStore,
        *,
        timeout_s: float = TOKEN_STORAGE_TIMEOUT_S,
    ) -> None:
        self._store = store
        self._timeout_s = timeout_s

    async def load(self) -> str | None:
        try:
            token = await asyncio.wait_for(
                self._store.get(TOKEN_KEY), self._timeout_s)
        except Exception as error:
            logger.warning(
                "could not read saved credential (%s)", type(error).__name__)
            return None
        return token if isinstance(token, str) and token.strip() else None

    async def save(self, token: str) -> bool:
        token = token.strip()
        if not token:
            return False
        try:
            await asyncio.wait_for(
                self._store.set(TOKEN_KEY, token), self._timeout_s)
            return True
        except Exception as error:
            logger.warning(
                "could not save credential securely (%s)", type(error).__name__)
            return False

    async def clear(self) -> bool:
        try:
            await asyncio.wait_for(
                self._store.remove(TOKEN_KEY), self._timeout_s)
            return True
        except Exception as error:
            logger.warning(
                "could not remove saved credential (%s)", type(error).__name__)
            return False
