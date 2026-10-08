"""Strict parsing of the server's string-encoded values and timestamps (DATA-01, DATA-02, DATA-06)."""

from __future__ import annotations

import math
from datetime import UTC, datetime

PrimitiveValue = bool | int | float | str | None


class ValueParseError(ValueError):
    """A server value does not match its declared type; never defaulted silently (DATA-02)."""


def parse_value(raw: object, value_type: object) -> PrimitiveValue:
    """Convert the server's string `value` using `value_type`.

    `None` means "no value" and is returned as-is, so a missing value can never
    turn into `0` or `False`.
    """
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueParseError(
            f"value must be a string, got {type(raw).__name__}")

    if value_type == "string":
        return raw
    if value_type == "bool":
        lowered = raw.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        raise ValueParseError(f"not a bool: {raw!r}")
    if value_type == "int":
        try:
            return int(raw)
        except ValueError:
            raise ValueParseError(f"not an int: {raw!r}") from None
    if value_type == "float":
        try:
            number = float(raw)
        except ValueError:
            raise ValueParseError(f"not a float: {raw!r}") from None
        if not math.isfinite(number):
            raise ValueParseError(f"non-finite float: {raw!r}")
        return number
    raise ValueParseError(
        f"value {raw!r} has unusable value_type {value_type!r}")


def parse_timestamp(raw: object) -> datetime | None:
    """Parse a server timestamp to aware UTC, or `None` if absent or malformed.

    The server writes `YYYY-MM-DDTHH:MM:SSZ`; naive values are taken as UTC.
    """
    if not isinstance(raw, str):
        return None
    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)
