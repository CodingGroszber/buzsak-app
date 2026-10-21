"""Android-only delivery and bounded foreground service adapter (ADR-0009, NTF-12)."""

from __future__ import annotations

import logging
import os
from importlib import import_module

from buzsak_app.ui import strings

logger = logging.getLogger(__name__)


class AndroidNotifications:
    def __init__(self) -> None:
        self._plugin = None
        self._permission_requested = False
        self._identifier = 10000
        self._status = "unavailable"

    def _load(self):
        if self._plugin is None:
            if not os.environ.get("MAIN_ACTIVITY_HOST_CLASS_NAME"):
                return None
            plugin = import_module("jnius").autoclass(
                "hu.buzsak.monitor.MonitorPlugin")
            plugin.configure(strings.APP_TITLE, strings.ALERT_MONITOR_ACTIVE,
                             strings.ALERTS_TITLE, strings.ALERT_TRUE,
                             strings.ALERT_ACKNOWLEDGE)
            self._plugin = plugin
        return self._plugin

    def start(self) -> bool:
        try:
            plugin = self._load()
            if plugin is None:
                return False
            if not self._permission_requested:
                plugin.requestPermission()
                self._permission_requested = True
            result = bool(plugin.start())
            self._status = str(plugin.status())
            return result
        except Exception as error:
            logger.warning("Android monitoring unavailable (%s)",
                           type(error).__name__)
            self._status = "unavailable"
            return False

    def stop(self) -> None:
        if self._plugin is not None:
            self._plugin.stop()
        self._status = "stopped"

    def active(self) -> bool:
        return self._plugin is not None and bool(self._plugin.active())

    def status(self) -> str:
        return str(self._plugin.status()) if self._plugin is not None else self._status

    def permission_granted(self) -> bool:
        return self._plugin is not None and bool(self._plugin.permissionGranted())

    def notify(self, name: str) -> bool:
        if self._plugin is None:
            return False
        self._identifier += 1
        try:
            return bool(self._plugin.notifyAlert(self._identifier, name))
        except Exception as error:
            logger.warning(
                "Android notification unavailable (%s)", type(error).__name__)
            return False
