"""Local-only, simulated Buzsák API for UI development; it never contacts hardware (BLD-08, TST-06)."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import threading
import time
import uuid
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit


_DEVICE_ID = "valve-controller"
_PULSE_COOLDOWN_S = 3.0
_RELAY_PARAMETERS = {
    "relay1": "relay1_mist",
    "relay2": "relay2_rain",
    "relay3": "relay3_drip",
    "relay4": "relay4_light",
}


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parameter(parameter_id: str, category: str, value: object, value_type: str) -> dict[str, Any]:
    now = _now()
    return {
        "id": parameter_id, "category": category, "unit": None,
        "value": str(value).lower() if isinstance(value, bool) else str(value),
        "value_type": value_type, "quality": "good", "stale": False,
        "observed_at": now, "last_changed_at": now, "revision": 1,
        "has_data": True,
    }


class FakeApi:
    def __init__(self, scenario: str = "normal") -> None:
        self.scenario = scenario
        self.lock = threading.RLock()
        fixture = Path(__file__).parent.parent / "tests" / \
            "fixtures" / "state" / "normal.json"
        self.state = json.loads(fixture.read_text(encoding="utf-8"))
        self.commands: dict[str, dict[str, Any]] = {}
        self.idempotency: dict[str, tuple[str, str]] = {}
        self._pulse_request_id = 0
        self._last_pulse_monotonic: float | None = None
        self._pulse_pending = False
        self._pulse_pending_snapshots = 0
        self._prepare_state()

    def _prepare_state(self) -> None:
        self.state["generated_at"] = _now()
        party = next(
            p for p in self.state["parties"] if p["id"] == "valve_controller")
        device = party["devices"][0]
        device["health"].update({
            "status": "healthy", "last_success_at": _now(), "last_error": None,
            "consecutive_failures": 0, "stale": False,
        })
        mode = "automatic"
        params = {item["id"]: item for item in device["parameters"]}
        params["mode"]["value"] = mode
        params["mode"]["revision"] = 1
        for relay, parameter_id in _RELAY_PARAMETERS.items():
            params[parameter_id]["value"] = "false"
            params[f"{relay}_controllable"] = _parameter(
                f"{relay}_controllable", "configuration", True, "bool")
            params[f"{relay}_always_manual"] = _parameter(
                f"{relay}_always_manual", "configuration", relay == "relay4", "bool")
        for parameter_id, value, value_type, category in (
            ("firmware", "v0.9", "string", "identity"),
            ("sensor_a_ok", True, "bool", "boolean"),
            ("sensor_b_ok", True, "bool", "boolean"),
            ("sensor_a_last_error", "", "string", "diagnostic"),
            ("sensor_b_last_error", "", "string", "diagnostic"),
            ("sensor_a_age_s", 1, "int", "diagnostic"),
            ("sensor_b_age_s", 2, "int", "diagnostic"),
            ("rain_valve_on", False, "bool", "boolean"),
            ("rain_start_hour", 5, "int", "configuration"),
            ("rain_start_minute", 0, "int", "configuration"),
            ("rain_duration_s", 1200, "int", "configuration"),
            ("rain_has_last_run", False, "bool", "boolean"),
            ("rain_time_synced", True, "bool", "boolean"),
        ):
            params[parameter_id] = _parameter(
                parameter_id, category, value, value_type)
        params["rain_last_run_duration_s"] = {
            "id": "rain_last_run_duration_s", "category": "continuous", "unit": "s",
            "value": None, "value_type": "null", "quality": "unavailable",
            "stale": False, "observed_at": None, "last_changed_at": None,
            "revision": 0, "has_data": False,
        }
        device["parameters"] = list(params.values())
        for capability in device["capabilities"]:
            capability["enabled"] = True
            capability["disabled_reason"] = None
        garage = next(
            p for p in self.state["parties"] if p["id"] == "matter")
        for sonoff in garage["devices"]:
            sonoff["health"].update({
                "status": "healthy", "last_success_at": _now(),
                "last_error": None, "consecutive_failures": 0,
                "stale": False,
            })
            for parameter in sonoff["parameters"]:
                parameter["observed_at"] = _now()
                parameter["stale"] = False
            if self.scenario == "offline":
                sonoff["health"].update(
                    status="offline", last_error="simulated offline device")
            elif self.scenario == "stale":
                sonoff["health"].update(status="degraded", stale=True)
                for parameter in sonoff["parameters"]:
                    parameter["stale"] = True
        if self.scenario == "offline":
            device["health"]["status"] = "offline"
            device["health"]["last_error"] = "simulated offline device"
        elif self.scenario == "stale":
            device["health"]["status"] = "degraded"
            device["health"]["stale"] = True
            for parameter in device["parameters"]:
                parameter["stale"] = True

    def _device(self) -> dict[str, Any]:
        return next(
            device
            for party in self.state["parties"]
            for device in party["devices"]
            if device["id"] == _DEVICE_ID
        )

    def _parameter_map(self) -> dict[str, dict[str, Any]]:
        return {item["id"]: item for item in self._device()["parameters"]}

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            self.state["generated_at"] = _now()
            if self.scenario == "normal":
                health = self._device()["health"]
                health["last_success_at"] = self.state["generated_at"]
                health["stale"] = False
            if self._pulse_pending:
                if self._pulse_pending_snapshots > 0:
                    self._pulse_pending_snapshots -= 1
                else:
                    sonoff = self._device_by_id("sonoff-2")
                    sonoff["last_pulse"].update(
                        status="succeeded", executed_at=self.state["generated_at"])
                    self._pulse_pending = False
            return copy.deepcopy(self.state)

    def pulse(self, device_id: str) -> tuple[int, dict[str, Any]]:
        with self.lock:
            try:
                device = self._device_by_id(device_id)
            except StopIteration:
                return 404, {"status": "rejected", "reason": "device not found"}
            if self.scenario in {"offline", "stale"}:
                return 503, {
                    "status": "rejected",
                    "reason": "simulated unavailable device",
                }
            on_off = next(
                (p for p in device["parameters"] if p["id"] == "on_off"), None)
            capability = next(
                (c for c in device["capabilities"]
                 if c["action_id"] == "pulse"),
                None,
            )
            if (
                device["health"].get("status") != "healthy"
                or on_off is None or on_off.get("quality") != "good"
                or on_off.get("stale") is True
            ):
                return 503, {
                    "status": "rejected",
                    "reason": "device telemetry is not fresh",
                }
            if capability is None or capability.get("enabled") is not True:
                return 409, {
                    "status": "rejected",
                    "reason": "pulse capability is disabled",
                }
            now_monotonic = time.monotonic()
            if (
                self._last_pulse_monotonic is not None
                and now_monotonic - self._last_pulse_monotonic < _PULSE_COOLDOWN_S
            ):
                return 409, {
                    "status": "rejected", "reason": "pulse cooldown is active",
                }
            self._last_pulse_monotonic = now_monotonic
            self._pulse_request_id += 1
            requested_at = _now()
            device["last_pulse"] = {
                "status": "pending", "requested_at": requested_at,
                "executed_at": None, "error": None,
            }
            if device_id == "sonoff-2":
                self._pulse_pending = True
                self._pulse_pending_snapshots = 1
            else:
                device["last_pulse"].update(
                    status="succeeded", executed_at=_now())
            return 202, {
                "status": "accepted", "request_id": self._pulse_request_id,
            }

    def _device_by_id(self, device_id: str) -> dict[str, Any]:
        return next(
            device
            for party in self.state["parties"]
            for device in party["devices"]
            if device["id"] == device_id
        )

    def submit(self, payload: object) -> tuple[int, dict[str, Any]]:
        if not isinstance(payload, dict) or set(payload) - {
            "action_id", "params", "idempotency_key", "client_origin", "expected_revisions"
        } or not {"action_id", "params", "idempotency_key", "client_origin"} <= set(payload):
            return 400, self._error("invalid_request", "invalid command fields")
        action_id = payload["action_id"]
        params = payload["params"]
        key = payload["idempotency_key"]
        if not isinstance(key, str) or not isinstance(params, dict):
            return 400, self._error("invalid_request", "invalid command fields")
        fingerprint = hashlib.sha256(json.dumps(
            [action_id, params, payload.get("expected_revisions", {})],
            sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()
        with self.lock:
            duplicate = self.idempotency.get(key)
            if duplicate is not None:
                if duplicate[0] != fingerprint:
                    return 409, self._error(
                        "idempotency_conflict", "key used for another intent")
                command_id = duplicate[1]
                return 202, self._receipt(command_id, True)
            if self.scenario in {"offline", "stale"}:
                return 503, self._error("device_unavailable", "simulated unavailable device")
            if action_id == "set_mode":
                value = params.get("value") if set(
                    params) == {"value"} else None
                if value not in {"manual", "automatic"}:
                    return 400, self._error("invalid_request", "invalid mode")
            elif action_id == "set_output":
                name, state = params.get("name"), params.get("state")
                if set(params) != {"name", "state"} or name not in _RELAY_PARAMETERS or type(state) is not bool:
                    return 400, self._error("invalid_request", "invalid output")
                mode = self._parameter_map()["mode"]["value"]
                always_manual = self._parameter_map(
                )[f"{name}_always_manual"]["value"] == "true"
                if mode != "manual" and not always_manual:
                    return 409, self._error("precondition_failed", "output requires manual mode")
            else:
                return 400, self._error("unsupported_action", "unsupported action")

            command_id = f"c_{uuid.uuid4().hex}"
            command = {
                "command_id": command_id, "device_id": _DEVICE_ID,
                "action_id": action_id, "params": copy.deepcopy(params),
                "status": "pending", "reason": None, "created_at": _now(),
                "updated_at": _now(), "expires_at": _now(),
                "confirmation": None, "outcome": None,
            }
            if self.scenario == "failure":
                command.update(status="failed", reason="device_rejected")
            elif self.scenario == "uncertain":
                command.update(status="uncertain",
                               reason="transport_outcome_ambiguous")
            elif self.scenario == "slow":
                self._apply(action_id, params)
                command.update(status="acknowledged", status_checks=0)
            else:
                self._apply(action_id, params)
                command.update(
                    status="confirmed", updated_at=_now(),
                    confirmation={"observed_at": _now(), "simulated": True},
                )
            self.commands[command_id] = command
            self.idempotency[key] = (fingerprint, command_id)
            return 202, self._receipt(command_id, False)

    def _apply(self, action_id: str, params: dict[str, Any]) -> None:
        now = _now()
        values = self._parameter_map()
        if action_id == "set_mode":
            values["mode"]["value"] = params["value"]
            for relay, parameter_id in _RELAY_PARAMETERS.items():
                if relay != "relay4":
                    values[parameter_id]["value"] = "false"
        else:
            parameter_id = _RELAY_PARAMETERS[params["name"]]
            values[parameter_id]["value"] = str(params["state"]).lower()
            if params["name"] == "relay2":
                values["rain_valve_on"]["value"] = str(params["state"]).lower()
        self.state["generated_at"] = now
        for parameter in self._device()["parameters"]:
            parameter["observed_at"] = now
            if parameter["id"] in values:
                parameter["revision"] += 1
        self._device()["health"]["last_success_at"] = now

    def command(self, command_id: str) -> dict[str, Any] | None:
        with self.lock:
            command = self.commands.get(command_id)
            if command is not None and self.scenario == "slow" and command["status"] == "acknowledged":
                command["status_checks"] += 1
                if command["status_checks"] >= 3:
                    command.update(
                        status="confirmed", updated_at=_now(),
                        confirmation={
                            "observed_at": _now(), "simulated": True},
                    )
            return copy.deepcopy(command) if command else None

    def _receipt(self, command_id: str, deduplicated: bool) -> dict[str, Any]:
        return {
            "command_id": command_id, "status": "pending",
            "status_url": f"/api/v1/commands/{command_id}",
            "expires_at": self.commands.get(command_id, {}).get("expires_at", _now()),
            "deduplicated": deduplicated,
        }

    @staticmethod
    def _error(code: str, message: str) -> dict[str, Any]:
        return {"error": {"code": code, "message": message}}


class Handler(BaseHTTPRequestHandler):
    server_version = "BuzsakFake/1.0"

    @property
    def api(self) -> FakeApi:
        return self.server.api  # type: ignore[attr-defined]

    def _authorize(self, operator: bool = False) -> bool:
        token = self.headers.get("Authorization", "").removeprefix("Bearer ")
        roles = {
            "fake-viewer": "viewer",
            "fake-operator": "operator",
            "fake-admin": "admin",
        }
        role = roles.get(token)
        if role is None:
            self._unauthorized()
            return False
        if operator and role == "viewer":
            self._send(403, FakeApi._error(
                "forbidden", "operator role required"))
            return False
        return True

    def _send(self, status: int, body: object) -> None:
        encoded = json.dumps(body, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(encoded)

    def _unauthorized(self) -> None:
        self._send(401, FakeApi._error(
            "unauthenticated", "fake token required"))

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/healthz":
            self._send(200, {"status": "ok"})
        elif path == "/readyz":
            self._send(200, {"status": "ok"})
        elif path == "/api/dashboard/state":
            if not self._authorize():
                return
            if self.api.scenario == "malformed":
                self._send(
                    200, {"generated_at": "broken", "parties": "broken"})
            else:
                self._send(200, self.api.snapshot())
        elif path.startswith("/api/v1/commands/"):
            if not self._authorize():
                return
            command_id = unquote(path.rsplit("/", 1)[-1])
            if self.api.scenario == "slow":
                time.sleep(2)
            command = self.api.command(command_id)
            self._send(200, command) if command else self._send(
                404, FakeApi._error("not_found", "command not found"))
        else:
            self._send(404, FakeApi._error("not_found", "not found"))

    def do_POST(self) -> None:
        if not self._authorize(operator=True):
            return
        path = urlsplit(self.path).path
        if path.startswith("/api/dashboard/devices/") and path.endswith("/pulse"):
            device_id = unquote(path.split("/")[-2])
            status, result = self.api.pulse(device_id)
            self._send(status, result)
            return
        if not path.startswith("/api/v1/devices/") or not path.endswith("/commands"):
            self._send(404, FakeApi._error("not_found", "not found"))
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size > 8192:
                self._send(413, FakeApi._error(
                    "invalid_request", "body too large"))
                return
            payload = json.loads(self.rfile.read(size))
        except (ValueError, json.JSONDecodeError):
            self._send(400, FakeApi._error("invalid_request", "invalid JSON"))
            return
        segments = [unquote(part)
                    for part in urlsplit(self.path).path.split("/")]
        if len(segments) < 6 or segments[4] != _DEVICE_ID:
            self._send(404, FakeApi._error("not_found", "device not found"))
            return
        status, result = self.api.submit(payload)
        self._send(status, result)

    def do_DELETE(self) -> None:
        if not self._authorize(operator=True):
            return
        command_id = unquote(urlsplit(self.path).path.rsplit("/", 1)[-1])
        command = self.api.commands.get(command_id)
        if command is None:
            self._send(404, FakeApi._error("not_found", "command not found"))
        elif command["status"] != "pending":
            self._send(409, FakeApi._error(
                "conflict", "only pending commands can be cancelled"))
        else:
            command["status"] = "cancelled"
            self._send(200, {"command_id": command_id, "status": "cancelled"})

    def log_message(self, format: str, *args: object) -> None:
        print("fake-api:", format % args)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--scenario", choices=("normal", "stale", "offline", "malformed", "failure", "uncertain", "slow"),
        default="normal",
    )
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.api = FakeApi(args.scenario)  # type: ignore[attr-defined]
    print(
        f"Simulated API only: http://{args.host}:{args.port} ({args.scenario}); no hardware access")
    print("App URL: http://10.0.2.2:%d (Android emulator); token: fake-operator" % args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
