"""Application settings and their defaults (ARC-09).

Pure data: persistence (Flet client storage) belongs to a higher layer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_SERVER_URL = "https://192.168.1.95"
# Saved by earlier builds; the server no longer listens there (ADR-0003).
RETIRED_SERVER_URLS = (
    "http://192.168.1.95:8080",
    "http://127.0.0.1:8765",
)

POLL_INTERVAL_MIN_S = 1.0
POLL_INTERVAL_MAX_S = 30.0

# The token is deliberately absent: it needs Keystore-backed storage (SEC-03, B-302).
_PERSISTED_NUMBERS = (
    "poll_interval_s", "request_timeout_s", "command_timeout_s")


@dataclass(frozen=True)
class Settings:
    """User-editable configuration (UPD-01, CTL-06, SEC-02)."""

    server_url: str = DEFAULT_SERVER_URL
    poll_interval_s: float = 2.0
    request_timeout_s: float = 5.0
    command_timeout_s: float = 10.0
    # Never log or display in full (SEC-03).
    token: str | None = None

    def __post_init__(self) -> None:
        if not POLL_INTERVAL_MIN_S <= self.poll_interval_s <= POLL_INTERVAL_MAX_S:
            raise ValueError(
                f"poll_interval_s must be within "
                f"{POLL_INTERVAL_MIN_S}..{POLL_INTERVAL_MAX_S}, got {self.poll_interval_s}"
            )
        if self.request_timeout_s <= 0 or self.command_timeout_s <= 0:
            raise ValueError("timeouts must be positive")
        if not self.server_url.startswith(("http://", "https://")):
            raise ValueError("server_url must start with http:// or https://")

    def to_storage(self) -> dict[str, str | float]:
        """Values safe to persist in plain storage; never includes the token."""
        return {
            "server_url": self.server_url,
            "poll_interval_s": self.poll_interval_s,
            "request_timeout_s": self.request_timeout_s,
            "command_timeout_s": self.command_timeout_s,
        }

    @classmethod
    def from_storage(cls, raw: Mapping[str, object]) -> Settings:
        """Rebuild settings, replacing each missing or invalid stored field with its default."""
        accepted: dict[str, object] = {}
        for key in ("server_url", *_PERSISTED_NUMBERS):
            value = raw.get(key)
            if key == "server_url":
                if not isinstance(value, str) or value.rstrip("/") in RETIRED_SERVER_URLS:
                    continue
            elif isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            try:
                cls(**accepted, **{key: value})
            except ValueError:
                continue
            accepted[key] = value
        return cls(**accepted)

    def __repr__(self) -> str:
        token = "<set>" if self.token else "None"
        return (
            f"Settings(server_url={self.server_url!r}, poll_interval_s={self.poll_interval_s}, "
            f"request_timeout_s={self.request_timeout_s}, "
            f"command_timeout_s={self.command_timeout_s}, token={token})"
        )
