"""Authenticated evaluation and notification intents (NTF-03, NTF-11, NTF-13)."""

from __future__ import annotations

from typing import Protocol

from buzsak_app.domain.alerts import AlertRule
from buzsak_app.domain.clock import Clock
from buzsak_app.domain.models import Snapshot
from buzsak_app.state.alert_monitor import AlertMonitor


class NotificationBridge(Protocol):
    def start(self) -> bool: ...
    def stop(self) -> None: ...
    def active(self) -> bool: ...
    def status(self) -> str: ...
    def permission_granted(self) -> bool: ...
    def notify(self, name: str) -> bool: ...


class AlertSession:
    def __init__(self, clock: Clock, bridge: NotificationBridge) -> None:
        self.monitor = AlertMonitor(clock)
        self.bridge = bridge
        self.running = False
        self.blocked = False
        self.rules: tuple[AlertRule, ...] = ()

    def set_rules(self, rules: tuple[AlertRule, ...]) -> None:
        self.monitor.set_rules(rules)
        self.rules = rules

    def stop(self) -> None:
        self.monitor.stop()
        self.bridge.stop()
        self.running = False

    def foreground(self) -> None:
        self.blocked = False

    def check_service(self) -> None:
        if self.running and not self.bridge.active():
            self.monitor.stop()
            self.running = False
            self.blocked = True

    def process(
        self, snapshot: Snapshot | None, *, authenticated: bool, trusted: bool,
    ) -> tuple[AlertRule, ...]:
        if not authenticated:
            self.stop()
            return ()
        self.check_service()
        if not self.rules:
            if self.running:
                self.stop()
            return ()
        if not self.running:
            if self.blocked or not trusted:
                return ()
            if not self.bridge.start():
                self.blocked = True
                return ()
            self.monitor.start()
            self.running = True
        triggered = self.monitor.evaluate_snapshot(
            snapshot, trustworthy=trusted)
        for rule in triggered:
            self.bridge.notify(rule.name)
        return triggered
