"""Immutable domain models of one server snapshot (ARC-07, DATA-02, DATA-05, SSOT-08)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from buzsak_app.domain.values import PrimitiveValue


class ValueState(StrEnum):
    """How far a parameter value can be trusted; each state renders differently (DATA-02)."""

    GOOD = "good"
    STALE = "stale"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"
    NO_DATA = "no_data"


class HealthStatus(StrEnum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"


@dataclass(frozen=True)
class Parameter:
    """One KPI. `value` is the last known value, so it is meaningful only when `state` is GOOD."""

    id: str
    category: str
    unit: str | None
    value: PrimitiveValue
    value_type: str | None
    state: ValueState
    observed_at: datetime | None
    last_changed_at: datetime | None
    revision: int
    # Set when the app itself found the data malformed (as opposed to server-reported invalid).
    issue: str | None = None

    @property
    def is_current(self) -> bool:
        return self.state is ValueState.GOOD


@dataclass(frozen=True)
class Health:
    status: HealthStatus
    last_success_at: datetime | None
    last_error: str | None
    consecutive_failures: int


@dataclass(frozen=True)
class Capability:
    """A control signal. `enabled` is true only if the server says so (SSOT-08)."""

    action_id: str
    params_schema: object
    enabled: bool
    disabled_reason: str | None


@dataclass(frozen=True)
class LastPulse:
    status: str
    requested_at: datetime | None
    executed_at: datetime | None
    error: str | None


@dataclass(frozen=True)
class Device:
    id: str
    label: str
    address: str
    enabled: bool
    health: Health
    parameters: tuple[Parameter, ...]
    capabilities: tuple[Capability, ...]
    last_pulse: LastPulse | None

    def parameter(self, parameter_id: str) -> Parameter | None:
        return next((p for p in self.parameters if p.id == parameter_id), None)

    def capability(self, action_id: str) -> Capability | None:
        return next((c for c in self.capabilities if c.action_id == action_id), None)


@dataclass(frozen=True)
class Party:
    """A group of devices shown as one tab (UX-02)."""

    id: str
    label: str
    kind: str
    configured: bool
    devices: tuple[Device, ...]
    note: str | None = None


@dataclass(frozen=True)
class Snapshot:
    """One validated server response. `issues` lists non-fatal problems that were tolerated."""

    generated_at: datetime
    parties: tuple[Party, ...]
    issues: tuple[str, ...] = ()
