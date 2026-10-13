"""Numeric, phone-local alert definitions and evaluation (NTF-02, NTF-05..NTF-07)."""

from __future__ import annotations

import math
import operator
from dataclasses import dataclass
from enum import StrEnum

from buzsak_app.domain.models import Parameter, Snapshot, ValueState


class Truth(StrEnum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


def finite_number(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


@dataclass(frozen=True)
class ValueReference:
    device_id: str
    parameter_id: str
    unit: str

    def __post_init__(self) -> None:
        if not self.device_id or not self.parameter_id or not self.unit.strip():
            raise ValueError(
                "telemetry requires device, parameter and explicit unit")


@dataclass(frozen=True)
class Constant:
    value: float
    unit: str

    def __post_init__(self) -> None:
        if not finite_number(self.value) or not self.unit.strip():
            raise ValueError(
                "constant requires a finite number and explicit unit")


Operand = ValueReference | Constant
_OPERATORS = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
}


@dataclass(frozen=True)
class Comparison:
    left: Operand
    relation: str
    right: Operand

    def __post_init__(self) -> None:
        if not isinstance(self.left, (ValueReference, Constant)) or not isinstance(
            self.right, (ValueReference, Constant)
        ):
            raise ValueError("unsupported operand")
        if self.relation not in _OPERATORS:
            raise ValueError("unsupported numeric relation")
        if isinstance(self.left, Constant) and isinstance(self.right, Constant):
            raise ValueError("at least one telemetry operand is required")
        if self.left.unit != self.right.unit:
            raise ValueError("operand units must match exactly")


@dataclass(frozen=True)
class AlertRule:
    id: str
    name: str
    comparisons: tuple[Comparison, ...]
    connective: str = "AND"

    def __post_init__(self) -> None:
        if not self.id or not self.name.strip():
            raise ValueError("rule requires an id and a name")
        if self.connective not in {"AND", "OR"}:
            raise ValueError("unsupported connective")
        if not isinstance(self.comparisons, tuple) or not self.comparisons:
            raise ValueError("rule requires a nonempty tuple of comparisons")
        if any(not isinstance(item, Comparison) for item in self.comparisons):
            raise ValueError("rule contains an invalid comparison")


def selectable_parameter(parameter: Parameter) -> bool:
    """Offer only explicitly unit-bearing numeric telemetry (NTF-02, NTF-06)."""
    return (
        parameter.value_type in {"int", "float"}
        and bool(parameter.unit and parameter.unit.strip())
        and (parameter.value is None or finite_number(parameter.value))
    )


def _resolve(operand: Operand, snapshot: Snapshot) -> float | int | None:
    if isinstance(operand, Constant):
        return operand.value
    device = next(
        (device for party in snapshot.parties for device in party.devices
         if device.id == operand.device_id), None,
    )
    if device is None:
        return None
    parameter = device.parameter(operand.parameter_id)
    if (
        parameter is None or parameter.state is not ValueState.GOOD
        or parameter.unit != operand.unit
        or not selectable_parameter(parameter)
        or not finite_number(parameter.value)
    ):
        return None
    return parameter.value


def evaluate(rule: AlertRule, snapshot: Snapshot | None) -> Truth:
    """UNKNOWN dominates both AND and OR, never treating missing data as FALSE (NTF-07)."""
    if snapshot is None:
        return Truth.UNKNOWN
    results: list[bool] = []
    for comparison in rule.comparisons:
        left = _resolve(comparison.left, snapshot)
        right = _resolve(comparison.right, snapshot)
        if left is None or right is None:
            return Truth.UNKNOWN
        results.append(_OPERATORS[comparison.relation](left, right))
    result = all(results) if rule.connective == "AND" else any(results)
    return Truth.TRUE if result else Truth.FALSE
