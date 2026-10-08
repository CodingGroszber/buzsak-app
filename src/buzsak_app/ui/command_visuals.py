"""Shared command-state labels, icons and semantic tones for control buttons."""

from __future__ import annotations

from dataclasses import dataclass

from buzsak_app.domain.models import Device, HealthStatus, ValueState
from buzsak_app.ui import strings
from buzsak_app.ui.view_models import Tone


@dataclass(frozen=True)
class StateVisual:
    label: str
    icon: str
    tone: Tone
    enabled: bool


_COMMAND_TONES = {
    "pending": Tone.MUTED,
    "dispatching": Tone.WARNING,
    "sent": Tone.WARNING,
    "acknowledged": Tone.WARNING,
    "confirmed": Tone.OK,
    "failed": Tone.ERROR,
    "expired": Tone.ERROR,
    "cancelled": Tone.MUTED,
    "uncertain": Tone.WARNING,
}


def command_state_tone(status: str) -> Tone:
    return _COMMAND_TONES.get(status, Tone.NEUTRAL)


def garage_relay_visual(device: Device) -> StateVisual:
    if device.health.status is not HealthStatus.HEALTHY:
        return StateVisual(strings.GARAGE_UNREACHABLE, "wifi_off", Tone.ERROR, False)

    relay = device.parameter("on_off")
    if relay is None or relay.state is not ValueState.GOOD or not isinstance(relay.value, bool):
        label, icon, tone = {
            ValueState.STALE: (strings.STATE_STALE, "history", Tone.WARNING),
            ValueState.INVALID: (strings.STATE_INVALID, "error_outline", Tone.ERROR),
            ValueState.NO_DATA: (strings.STATE_NO_DATA, "hourglass_empty", Tone.MUTED),
            ValueState.UNAVAILABLE: (strings.STATE_UNAVAILABLE, "cloud_off", Tone.ERROR),
        }.get(relay.state if relay is not None else ValueState.UNAVAILABLE,
              (strings.STATE_UNAVAILABLE, "cloud_off", Tone.ERROR))
        return StateVisual(label, icon, tone, False)

    return StateVisual(
        strings.GARAGE_RELAY_ACTIVE if relay.value else strings.GARAGE_RELAY_INACTIVE,
        "toggle_on" if relay.value else "toggle_off",
        Tone.OK if relay.value else Tone.MUTED,
        True,
    )


def pulse_button_visual(
    device: Device,
    *,
    operation_status: str | None = None,
    busy: bool = False,
    uncertain: bool = False,
) -> StateVisual:
    relay = garage_relay_visual(device)
    if not relay.enabled:
        return StateVisual(relay.label, relay.icon, relay.tone, False)

    capability = device.capability("pulse")
    if capability is None or not capability.enabled:
        return StateVisual(strings.PULSE_DISABLED, "block", Tone.MUTED, False)

    last = device.last_pulse
    pulse_status = operation_status or (
        last.status if last is not None else None)
    if uncertain or pulse_status == "uncertain":
        return StateVisual(strings.PULSE_UNCERTAIN, "warning_amber", Tone.WARNING, False)
    if busy or pulse_status in {"pending", "sent"}:
        return StateVisual(strings.PULSE_PENDING, "hourglass_empty", Tone.WARNING, False)
    return StateVisual(strings.GARAGE_TRIGGER, "power_settings_new", Tone.OK, True)
