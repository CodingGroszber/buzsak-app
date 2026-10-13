"""Versioned phone-local rule persistence, excluding session state (NTF-01, NTF-04)."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict

from buzsak_app.domain.alerts import AlertRule, Comparison, Constant, Operand, ValueReference
from buzsak_app.state.settings_repo import KeyValueStore, STORAGE_TIMEOUT_S

logger = logging.getLogger(__name__)
RULES_KEY = "buzsak.alert-rules"


def _operand(raw: object) -> Operand:
    if not isinstance(raw, dict):
        raise ValueError("operand must be an object")
    if set(raw) == {"value", "unit"}:
        if not isinstance(raw["unit"], str):
            raise ValueError("unit must be text")
        return Constant(raw["value"], raw["unit"])
    if set(raw) == {"device_id", "parameter_id", "unit"}:
        if any(not isinstance(value, str) for value in raw.values()):
            raise ValueError("reference fields must be text")
        return ValueReference(**raw)
    raise ValueError("unsupported operand fields")


def decode_rules(raw: object) -> tuple[AlertRule, ...]:
    """Reject corrupt or unsupported rule formats instead of inventing defaults (NTF-04)."""
    if not isinstance(raw, dict) or type(raw.get("version")) is not int or raw["version"] != 1:
        raise ValueError("unsupported rule schema")
    items = raw.get("rules")
    if not isinstance(items, list):
        raise ValueError("rules must be a list")
    result: list[AlertRule] = []
    for item in items:
        if not isinstance(item, dict) or set(item) != {"id", "name", "connective", "comparisons"}:
            raise ValueError("invalid rule fields")
        if any(not isinstance(item[key], str) for key in ("id", "name", "connective")):
            raise ValueError("invalid rule text")
        if not isinstance(item["comparisons"], list):
            raise ValueError("comparisons must be a list")
        comparisons: list[Comparison] = []
        for comparison in item["comparisons"]:
            if not isinstance(comparison, dict) or set(comparison) != {"left", "relation", "right"}:
                raise ValueError("invalid comparison fields")
            if not isinstance(comparison["relation"], str):
                raise ValueError("relation must be text")
            comparisons.append(Comparison(
                _operand(comparison["left"]), comparison["relation"],
                _operand(comparison["right"]),
            ))
        result.append(AlertRule(item["id"], item["name"], tuple(
            comparisons), item["connective"]))
    if len({rule.id for rule in result}) != len(result):
        raise ValueError("duplicate rule ids")
    return tuple(result)


class AlertRepository:
    def __init__(self, store: KeyValueStore, *, timeout_s: float = STORAGE_TIMEOUT_S) -> None:
        self._store = store
        self._timeout_s = timeout_s

    async def load(self) -> tuple[AlertRule, ...]:
        """Load definitions only; callers must distinguish failure from an empty catalog (NTF-04)."""
        raw = await asyncio.wait_for(self._store.get(RULES_KEY), self._timeout_s)
        if raw is None:
            return ()
        if not isinstance(raw, str):
            raise ValueError("stored rule payload must be JSON text")
        return decode_rules(json.loads(raw))

    async def save(self, rules: tuple[AlertRule, ...]) -> bool:
        """Validate before writing; never serialize credentials or runtime state (NTF-04)."""
        payload = {"version": 1, "rules": [asdict(rule) for rule in rules]}
        serialized = json.dumps(payload, ensure_ascii=True, allow_nan=False)
        decode_rules(json.loads(serialized))
        try:
            return bool(await asyncio.wait_for(
                self._store.set(RULES_KEY, serialized), self._timeout_s))
        except Exception as error:
            logger.warning(
                "could not save alert definitions (%s)", type(error).__name__)
            return False
