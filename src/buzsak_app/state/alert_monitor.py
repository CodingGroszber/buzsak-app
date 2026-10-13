"""Session-only edge triggering and per-rule cooldowns (NTF-04, NTF-08..NTF-10)."""

from __future__ import annotations

from dataclasses import dataclass

from buzsak_app.domain.alerts import AlertRule, Truth, evaluate
from buzsak_app.domain.clock import Clock
from buzsak_app.domain.models import Snapshot

COOLDOWN_S = 10.0


@dataclass
class _RuleState:
    rule: AlertRule
    last_truth: Truth = Truth.UNKNOWN
    last_trigger_at: float | None = None


class AlertMonitor:
    """Produce independent notification intents without delivering them (NTF-11)."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._rules: dict[str, _RuleState] = {}
        self._active = False

    def set_rules(self, rules: tuple[AlertRule, ...]) -> None:
        if len({rule.id for rule in rules}) != len(rules):
            raise ValueError("duplicate rule ids")
        updated: dict[str, _RuleState] = {}
        for rule in rules:
            previous = self._rules.get(rule.id)
            if previous is None:
                updated[rule.id] = _RuleState(rule)
            elif (
                previous.rule.comparisons != rule.comparisons
                or previous.rule.connective != rule.connective
            ):
                updated[rule.id] = _RuleState(
                    rule, last_trigger_at=previous.last_trigger_at)
            else:
                previous.rule = rule
                updated[rule.id] = previous
        self._rules = updated

    def start(self) -> None:
        """Start a fresh authenticated session, resetting truth and cooldown (NTF-04)."""
        for state in self._rules.values():
            state.last_truth = Truth.UNKNOWN
            state.last_trigger_at = None
        self._active = True

    def stop(self) -> None:
        """Stop evaluation without discarding rule definitions (NTF-03, NTF-04)."""
        self._active = False

    def evaluate_snapshot(
        self, snapshot: Snapshot | None, *, trustworthy: bool = True,
    ) -> tuple[AlertRule, ...]:
        """Consume TRUE edges; cached/offline inputs do not rearm rules (NTF-07..NTF-09)."""
        if not self._active:
            return ()
        now = self._clock.monotonic()
        triggered: list[AlertRule] = []
        for state in self._rules.values():
            truth = evaluate(state.rule, snapshot if trustworthy else None)
            if truth is Truth.UNKNOWN:
                continue
            rising = truth is Truth.TRUE and state.last_truth is not Truth.TRUE
            state.last_truth = truth
            if rising and (
                state.last_trigger_at is None
                or now - state.last_trigger_at >= COOLDOWN_S
            ):
                state.last_trigger_at = now
                triggered.append(state.rule)
        return tuple(triggered)
