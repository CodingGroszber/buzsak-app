"""Map the server's `/api/dashboard/state` JSON to domain models (SRV-01, SRV-11, NFR-04).

Tolerant of unknown fields. A malformed parameter becomes INVALID instead of
dropping the snapshot; unusable devices and parties are skipped and recorded in
`Snapshot.issues`. Only a broken top level raises.
"""

from __future__ import annotations

from collections.abc import Mapping

from buzsak_app.domain.models import (
    Capability,
    Device,
    Health,
    HealthStatus,
    LastPulse,
    Parameter,
    Party,
    Snapshot,
    ValueState,
)
from buzsak_app.domain.values import ValueParseError, parse_timestamp, parse_value


class SnapshotFormatError(ValueError):
    """The payload is unusable as a whole, so the previous snapshot must be kept."""


def parse_snapshot(payload: object) -> Snapshot:
    if not isinstance(payload, Mapping):
        raise SnapshotFormatError("payload is not a JSON object")
    generated_at = parse_timestamp(payload.get("generated_at"))
    if generated_at is None:
        raise SnapshotFormatError("generated_at missing or malformed")
    raw_parties = payload.get("parties")
    if not isinstance(raw_parties, list):
        raise SnapshotFormatError("parties missing or not a list")

    issues: list[str] = []
    parties = [
        party
        for index, raw in enumerate(raw_parties)
        if (party := _parse_party(raw, f"parties[{index}]", issues)) is not None
    ]
    return Snapshot(generated_at=generated_at, parties=tuple(parties), issues=tuple(issues))


def _text(raw: object) -> str | None:
    return raw if isinstance(raw, str) else None


def _count(raw: object) -> int:
    # bool is an int subclass; a flag is not a count.
    return raw if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0 else 0


def _parse_party(raw: object, where: str, issues: list[str]) -> Party | None:
    if not isinstance(raw, Mapping) or not (party_id := _text(raw.get("id"))):
        issues.append(f"{where}: skipped, not an object with an id")
        return None
    raw_devices = raw.get("devices")
    if not isinstance(raw_devices, list):
        issues.append(f"{where}: devices missing or not a list")
        raw_devices = []
    devices = [
        device
        for index, item in enumerate(raw_devices)
        if (device := _parse_device(item, f"{where}.devices[{index}]", issues)) is not None
    ]
    return Party(
        id=party_id,
        label=_text(raw.get("label")) or party_id,
        kind=_text(raw.get("kind")) or party_id,
        configured=raw.get("configured") is True,
        devices=tuple(devices),
        note=_text(raw.get("note")),
    )


def _parse_device(raw: object, where: str, issues: list[str]) -> Device | None:
    if not isinstance(raw, Mapping) or not (device_id := _text(raw.get("id"))):
        issues.append(f"{where}: skipped, not an object with an id")
        return None
    return Device(
        id=device_id,
        label=_text(raw.get("label")) or device_id,
        address=_text(raw.get("address")) or "",
        enabled=raw.get("enabled") is True,
        health=_parse_health(raw.get("health")),
        parameters=_parse_list(raw.get("parameters"),
                               _parse_parameter, f"{where}.parameters", issues),
        capabilities=_parse_list(
            raw.get("capabilities"), _parse_capability, f"{where}.capabilities", issues),
        last_pulse=_parse_last_pulse(raw.get("last_pulse")),
    )


def _parse_list(raw, parse_item, where: str, issues: list[str]) -> tuple:
    if not isinstance(raw, list):
        issues.append(f"{where}: missing or not a list")
        return ()
    items = []
    for index, item in enumerate(raw):
        parsed = parse_item(item, f"{where}[{index}]", issues)
        if parsed is not None:
            items.append(parsed)
    return tuple(items)


def _parse_health(raw: object) -> Health:
    data = raw if isinstance(raw, Mapping) else {}
    try:
        status = HealthStatus(data.get("status"))
    except ValueError:
        status = HealthStatus.UNKNOWN
    return Health(
        status=status,
        last_success_at=parse_timestamp(data.get("last_success_at")),
        last_error=_text(data.get("last_error")),
        consecutive_failures=_count(data.get("consecutive_failures")),
    )


def _parse_capability(raw: object, where: str, issues: list[str]) -> Capability | None:
    if not isinstance(raw, Mapping) or not (action_id := _text(raw.get("action_id"))):
        issues.append(f"{where}: skipped, not an object with an action_id")
        return None
    return Capability(
        action_id=action_id,
        params_schema=raw.get("params_schema"),
        # Absent or non-boolean means disabled: never enable a control by default (SSOT-08).
        enabled=raw.get("enabled") is True,
        disabled_reason=_text(raw.get("disabled_reason")),
    )


def _parse_last_pulse(raw: object) -> LastPulse | None:
    if not isinstance(raw, Mapping) or not (status := _text(raw.get("status"))):
        return None
    return LastPulse(
        status=status,
        requested_at=parse_timestamp(raw.get("requested_at")),
        executed_at=parse_timestamp(raw.get("executed_at")),
        error=_text(raw.get("error")),
    )


def _quality_state(quality: object, stale: object) -> tuple[ValueState, str | None]:
    if quality == "good":
        return (ValueState.STALE if stale is True else ValueState.GOOD), None
    if quality == "stale":
        return ValueState.STALE, None
    if quality == "unavailable":
        return ValueState.UNAVAILABLE, None
    if quality == "invalid":
        return ValueState.INVALID, None
    return ValueState.INVALID, f"unknown quality {quality!r}"


def _parse_parameter(raw: object, where: str, issues: list[str]) -> Parameter | None:
    if not isinstance(raw, Mapping) or not (parameter_id := _text(raw.get("id"))):
        issues.append(f"{where}: skipped, not an object with an id")
        return None

    observed_at = parse_timestamp(raw.get("observed_at"))
    has_data = raw.get("has_data")
    if not isinstance(has_data, bool):
        has_data = raw.get("observed_at") is not None

    base = {
        "id": parameter_id,
        "category": _text(raw.get("category")) or "",
        "unit": _text(raw.get("unit")),
        "value_type": _text(raw.get("value_type")),
        "observed_at": observed_at,
        "last_changed_at": parse_timestamp(raw.get("last_changed_at")),
        "revision": _count(raw.get("revision")),
    }
    if not has_data:
        return Parameter(value=None, state=ValueState.NO_DATA, **base)

    state, issue = _quality_state(raw.get("quality"), raw.get("stale"))
    value = None
    try:
        value = parse_value(raw.get("value"), raw.get("value_type"))
    except ValueParseError as error:
        issue = issue or str(error)
    if issue is None and observed_at is None:
        issue = "observed_at missing or malformed"
    if issue is None and value is None and state in (ValueState.GOOD, ValueState.STALE):
        issue = "no value"

    if issue is not None:
        issues.append(f"{where} ({parameter_id}): {issue}")
        state = ValueState.INVALID
    return Parameter(value=value, state=state, issue=issue, **base)
