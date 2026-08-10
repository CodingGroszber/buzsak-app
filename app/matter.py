"""Matter websocket client and door command helpers."""

from __future__ import annotations

import json
import time
from typing import Any

import websocket


class MatterClientError(RuntimeError):
    """Raised when Matter websocket transport or protocol operations fail."""


class MatterClient:
    """Small wrapper around Matter websocket RPC commands."""

    def __init__(
        self,
        urls: tuple[str, ...],
        connect_retries: int,
        timeout: float,
        endpoint_id: int,
        onoff_cluster: int,
    ) -> None:
        self.urls = urls
        self.connect_retries = connect_retries
        self.timeout = timeout
        self.endpoint_id = endpoint_id
        self.onoff_cluster = onoff_cluster
        self.last_url = urls[0]

    def _ordered_urls(self) -> list[str]:
        return [self.last_url] + [url for url in self.urls if url != self.last_url]

    def call(self, command: str, args: dict[str, Any]) -> tuple[dict[str, Any], int]:
        """Execute a command and return result payload and latency in ms."""
        errors: list[str] = []

        for url in self._ordered_urls():
            for attempt in range(1, self.connect_retries + 1):
                t0 = time.monotonic()
                ws = None
                try:
                    ws = websocket.create_connection(url, timeout=self.timeout)
                    ws.settimeout(self.timeout)
                    ws.recv()
                    ws.send(
                        json.dumps(
                            {"message_id": "1", "command": command, "args": args})
                    )
                    while True:
                        data = json.loads(ws.recv())
                        if data.get("message_id") != "1":
                            continue
                        if data.get("error_code") is not None:
                            raise MatterClientError(
                                data.get(
                                    "details") or f"Matter error {data['error_code']}"
                            )
                        self.last_url = url
                        latency_ms = round((time.monotonic() - t0) * 1000)
                        return data.get("result", {}), latency_ms
                except (
                    MatterClientError,
                    TimeoutError,
                    OSError,
                    ValueError,
                    websocket.WebSocketException,
                ) as ex:
                    errors.append(
                        f"{url} try {attempt}/{self.connect_retries}: {ex}")
                    if attempt < self.connect_retries:
                        time.sleep(0.15 * attempt)
                finally:
                    if ws is not None:
                        ws.close()

        raise MatterClientError("Matter ws failed: " + " | ".join(errors[-4:]))

    def device_command(self, node_id: int, command_name: str) -> None:
        """Send an On/Off cluster command to a node."""
        self.call(
            "device_command",
            {
                "node_id": node_id,
                "endpoint_id": self.endpoint_id,
                "cluster_id": self.onoff_cluster,
                "command_name": command_name,
                "payload": {},
            },
        )

    def read_on_state(self, node_id: int) -> tuple[bool, int]:
        """Read door OnOff state and return bool state with latency."""
        result, latency_ms = self.call(
            "read_attribute",
            {
                "node_id": node_id,
                "attribute_path": f"{self.endpoint_id}/{self.onoff_cluster}/0",
            },
        )
        state_key = f"{self.endpoint_id}/{self.onoff_cluster}/0"
        return bool(result.get(state_key)), latency_ms

    def pulse_door(self, node_id: int, pulse_seconds: float) -> None:
        """Generate a short Off-On-Off pulse to trigger a garage opener."""
        self.device_command(node_id, "Off")
        time.sleep(0.05)
        self.device_command(node_id, "On")
        time.sleep(pulse_seconds)
        self.device_command(node_id, "Off")

    def enforce_off_defaults(self, node_ids: list[int]) -> dict[int, bool]:
        """Try to reset doors to Off once during startup."""
        result: dict[int, bool] = {}
        for node_id in node_ids:
            try:
                self.device_command(node_id, "Off")
                result[node_id] = True
            except MatterClientError:
                result[node_id] = False
        return result
