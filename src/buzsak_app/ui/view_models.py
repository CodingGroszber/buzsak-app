"""Turn domain values into display decisions, without any Flet types (DATA-02, VLV-07, UX-13).

Kept separate from the controls so the rules that decide what a user is told about a value
are unit-tested. State is always conveyed by text and an icon name, never by colour alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from buzsak_app.domain.automation import is_frozen
from buzsak_app.domain.models import Device, HealthStatus, Parameter, ValueState
from buzsak_app.domain.presentation import display_number, presentation_for
from buzsak_app.state.connection import ConnectionStatus
from buzsak_app.ui import strings


class Tone(StrEnum):
    """Semantic emphasis; the theme maps it to colours (UX-13)."""

    NEUTRAL = "neutral"
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    MUTED = "muted"


@dataclass(frozen=True)
class Badge:
    text: str
    icon: str
    tone: Tone


@dataclass(frozen=True)
class KpiView:
    parameter_id: str
    label: str
    caption: str | None
    icon: str
    value_text: str
    unit: str | None
    # Wider than a number would be, so the card uses a smaller type size (e.g. "Automatic").
    long_text: bool
    badge: Badge | None
    # The value is shown but must not look live (stale, unavailable, invalid, frozen).
    dimmed: bool
    # Full description for a long-press / tooltip (DATA-04).
    detail: str


def _bool_text(value: bool) -> str:
    return strings.VALUE_ON if value else strings.VALUE_OFF


def _value_text(parameter: Parameter) -> tuple[str, str | None]:
    """Text and unit; a missing value is a dash, never `0` or `off` (DATA-02)."""
    value = parameter.value
    if value is None:
        return strings.VALUE_MISSING, None
    if isinstance(value, bool):
        return _bool_text(value), None
    number = display_number(parameter)
    if number is not None:
        return number.text, number.unit
    return strings.mode_text(value) if parameter.id == "mode" else str(value), None


_STATE_BADGES: dict[ValueState, Badge] = {
    ValueState.STALE: Badge(strings.STATE_STALE, "history", Tone.WARNING),
    ValueState.UNAVAILABLE: Badge(strings.STATE_UNAVAILABLE, "cloud_off", Tone.ERROR),
    ValueState.INVALID: Badge(strings.STATE_INVALID, "error_outline", Tone.ERROR),
    ValueState.NO_DATA: Badge(strings.STATE_NO_DATA, "hourglass_empty", Tone.MUTED),
}
FROZEN_BADGE = Badge(strings.STATE_FROZEN, "pause_circle_outline", Tone.MUTED)
LONG_TEXT_CHARS = 6


def kpi_view(device: Device, parameter: Parameter) -> KpiView:
    frozen = parameter.is_current and is_frozen(device, parameter.id)
    badge = FROZEN_BADGE if frozen else _STATE_BADGES.get(parameter.state)
    text, unit = _value_text(parameter)
    # Without a trusted value there is nothing to dim: the dash and badge already say so.
    shows_stale_value = parameter.value is not None and not parameter.is_current
    return KpiView(
        parameter_id=parameter.id,
        label=strings.parameter_label(parameter.id),
        caption=strings.FROZEN_CAPTION if frozen else strings.parameter_caption(
            parameter.id),
        icon=presentation_for(parameter.id).icon,
        value_text=text,
        unit=unit,
        long_text=len(text) > LONG_TEXT_CHARS,
        badge=badge,
        dimmed=frozen or shows_stale_value,
        detail=_detail(parameter, frozen),
    )


def _detail(parameter: Parameter, frozen: bool) -> str:
    lines = [f"{strings.parameter_label(parameter.id)} ({parameter.id})"]
    if caption := strings.parameter_caption(parameter.id):
        lines.append(caption)  # the card clamps captions to two lines
    if parameter.issue:
        lines.append(f"{strings.DETAIL_PROBLEM}: {parameter.issue}")
    if frozen:
        lines.append(strings.FROZEN_CAPTION)
    lines.append(f"{strings.DETAIL_OBSERVED}: {_when(parameter.observed_at)}")
    lines.append(
        f"{strings.DETAIL_CHANGED}: {_when(parameter.last_changed_at)}")
    return "\n".join(lines)


def _when(moment) -> str:
    if moment is None:
        return strings.VALUE_MISSING
    return moment.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def sorted_parameters(device: Device) -> list[Parameter]:
    """Catalog order first, then unknown parameters by id so new KPIs stay stable (SSOT-07)."""
    return sorted(device.parameters, key=lambda p: (presentation_for(p.id).order, p.id))


@dataclass(frozen=True)
class HealthView:
    text: str
    icon: str
    tone: Tone
    detail: str | None


_HEALTH: dict[HealthStatus, tuple[str, str, Tone]] = {
    HealthStatus.HEALTHY: (strings.HEALTH_HEALTHY, "check_circle", Tone.OK),
    HealthStatus.DEGRADED: (strings.HEALTH_DEGRADED, "warning_amber", Tone.WARNING),
    HealthStatus.OFFLINE: (strings.HEALTH_OFFLINE, "wifi_off", Tone.ERROR),
    HealthStatus.UNKNOWN: (strings.HEALTH_UNKNOWN, "help_outline", Tone.MUTED),
}


def health_view(device: Device) -> HealthView:
    text, icon, tone = _HEALTH[device.health.status]
    detail = device.health.last_error
    if device.health.consecutive_failures:
        failures = strings.failures_text(device.health.consecutive_failures)
        detail = f"{failures}: {detail}" if detail else failures
    return HealthView(text=text, icon=icon, tone=tone, detail=detail)


def device_detail(device: Device) -> str | None:
    """One muted line under the device name: health problems, then the last pulse (read-only)."""
    parts = []
    if (health_detail := health_view(device).detail) is not None:
        parts.append(health_detail)
    if device.last_pulse is not None:
        parts.append(strings.pulse_text(
            device.last_pulse.status, device.last_pulse.error))
    return " · ".join(parts) or None


@dataclass(frozen=True)
class ConnectionView:
    text: str
    icon: str
    tone: Tone
    # A banner is shown only when the user needs to know the data may be out of date.
    show_banner: bool


_CONNECTION: dict[ConnectionStatus, ConnectionView] = {
    ConnectionStatus.CONNECTING: ConnectionView(strings.CONN_CONNECTING, "sync", Tone.MUTED, False),
    ConnectionStatus.ONLINE: ConnectionView(strings.CONN_ONLINE, "check_circle", Tone.OK, False),
    ConnectionStatus.OFFLINE: ConnectionView(strings.CONN_OFFLINE, "wifi_off", Tone.ERROR, True),
    ConnectionStatus.SERVER_UNHEALTHY: ConnectionView(strings.CONN_UNHEALTHY, "sync_problem", Tone.WARNING, True),
    ConnectionStatus.UNAUTHORIZED: ConnectionView(strings.CONN_UNAUTHORIZED, "lock", Tone.ERROR, True),
}


def connection_view(status: ConnectionStatus) -> ConnectionView:
    return _CONNECTION[status]


def duration_text(seconds: float) -> str:
    """Compact span such as "3 s", "5 min", "26 h" or "2 d"."""
    whole = int(seconds)
    if whole < 60:
        return f"{whole} s"
    if whole < 3600:
        return f"{whole // 60} min"
    if whole < 2 * 86400:
        return f"{whole // 3600} h"
    return f"{whole // 86400} d"


def freshness_text(age_s: float | None) -> str:
    """Text like "updated 3 s ago" (UX-12)."""
    if age_s is None:
        return strings.FRESHNESS_NEVER
    return strings.updated_ago(duration_text(age_s))
