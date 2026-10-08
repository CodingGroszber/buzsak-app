"""Exercise the bundled fake API over HTTP on loopback only; never contacts a device."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import threading
from types import SimpleNamespace
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from buzsak_app.api.client import (
    CommandApiError,
    MalformedResponse,
    PulseRejected,
    ServerClient,
)
from buzsak_app.domain.clock import SystemClock
from buzsak_app.domain.snapshot import parse_snapshot
from buzsak_app.settings import Settings
from buzsak_app.state.poller import Poller
from buzsak_app.state.store import Store
from buzsak_app.ui.runtime import Runtime

_SPEC = importlib.util.spec_from_file_location(
    "buzsak_fake_server_test",
    Path(__file__).resolve().parents[1] / "scripts" / "fake_server.py",
)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("cannot load fake server test module")
_FAKE_SERVER = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _FAKE_SERVER
_SPEC.loader.exec_module(_FAKE_SERVER)
FakeApi = _FAKE_SERVER.FakeApi
Handler = _FAKE_SERVER.Handler


class StubPage:
    def update(self) -> None:
        pass


class FakeSettingsRepository:
    async def save(self, settings: Settings) -> bool:
        return True


class FakeTokenRepository:
    def __init__(self, token: str | None = None) -> None:
        self.token = token

    async def save(self, token: str) -> bool:
        self.token = token
        return True

    async def clear(self) -> bool:
        self.token = None
        return True


class FakeTestHttpServer(ThreadingHTTPServer):
    api: FakeApi


@pytest.fixture
def fake_api_server():
    api = FakeApi()
    server = FakeTestHttpServer(("127.0.0.1", 0), Handler)
    server.api = api
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", api
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_fake_server_state_and_mode_command_update_only_simulated_values(fake_api_server) -> None:
    url, _ = fake_api_server

    async def exercise():
        async with ServerClient(url, token="fake-operator") as client:
            before = parse_snapshot(await client.fetch_state())
            device = before.parties[1].devices[0]
            assert device.health.status.value == "healthy"
            mode_capability = device.capability("set_mode")
            assert mode_capability is not None and mode_capability.enabled
            rain_last_run = device.parameter("rain_last_run_duration_s")
            assert rain_last_run is not None and rain_last_run.state.value == "no_data"

            receipt = await client.submit_command(
                device.id, action_id="set_mode", params={"value": "manual"},
                idempotency_key="mode-manual-1")
            status = await client.command_status(receipt.command_id)
            after = parse_snapshot(await client.fetch_state()).parties[1].devices[0]
            return receipt, status, after

    receipt, status, after = asyncio.run(exercise())
    assert receipt.status == "pending"
    assert status.status == "confirmed"
    mode = after.parameter("mode")
    assert mode is not None and mode.value == "manual"
    for index, name in ((1, "mist"), (2, "rain"), (3, "drip")):
        relay = after.parameter(f"relay{index}_{name}")
        assert relay is not None and relay.value is False


def test_fake_server_enforces_automatic_interlock_and_light_exception(fake_api_server) -> None:
    url, _ = fake_api_server

    async def exercise():
        async with ServerClient(url, token="fake-operator") as client:
            with pytest.raises(CommandApiError) as rejected:
                await client.submit_command(
                    "valve-controller", action_id="set_output",
                    params={"name": "relay1", "state": True},
                    idempotency_key="mist-auto")
            accepted = await client.submit_command(
                "valve-controller", action_id="set_output",
                params={"name": "relay4", "state": True},
                idempotency_key="light-auto")
            status = await client.command_status(accepted.command_id)
            return rejected.value, status

    rejected, status = asyncio.run(exercise())
    assert rejected.code == "precondition_failed"
    assert status.status == "confirmed"


def test_fake_server_requires_operator_for_commands_but_viewer_can_read(fake_api_server) -> None:
    url, _ = fake_api_server

    async def exercise():
        async with ServerClient(url, token="fake-viewer") as client:
            await client.fetch_state()
            with pytest.raises(CommandApiError) as rejected:
                await client.submit_command(
                    "valve-controller", action_id="set_mode",
                    params={"value": "manual"}, idempotency_key="viewer-mode")
            return rejected.value

    assert asyncio.run(exercise()).code == "forbidden"


def test_fake_server_pulse_is_simulated_and_reports_status_without_changing_relay(
    fake_api_server,
) -> None:
    url, _ = fake_api_server

    async def exercise():
        async with ServerClient(url, token="fake-operator") as client:
            before = parse_snapshot(await client.fetch_state())
            garage = next(
                party for party in before.parties if party.kind == "matter")
            left = next(
                device for device in garage.devices if device.id == "sonoff-2")
            receipt = await client.request_pulse(left.id)
            pending = parse_snapshot(await client.fetch_state())
            latest_garage = next(
                party for party in pending.parties if party.kind == "matter")
            latest_left = next(
                device for device in latest_garage.devices if device.id == "sonoff-2")
            assert latest_left.last_pulse is not None
            assert latest_left.last_pulse.status == "pending"
            with pytest.raises(PulseRejected, match="cooldown"):
                await client.request_pulse(left.id)
            after = parse_snapshot(await client.fetch_state())
            latest_garage = next(
                party for party in after.parties if party.kind == "matter")
            latest_left = next(
                device for device in latest_garage.devices if device.id == "sonoff-2")
            return receipt, left, latest_left

    receipt, before, after = asyncio.run(exercise())
    assert receipt.request_id == 1
    assert before.parameter("on_off").value is False
    assert after.parameter("on_off").value is False
    assert after.last_pulse is not None
    assert after.last_pulse.status == "succeeded"


@pytest.mark.parametrize("device_id,expected_statuses", [
    ("sonoff-1", ["sent", "succeeded"]),
    ("sonoff-2", ["sent", "pending", "succeeded"]),
])
def test_runtime_submits_one_pulse_and_observes_completion_through_poller(
    fake_api_server, device_id: str, expected_statuses: list[str],
) -> None:
    url, api = fake_api_server

    async def exercise():
        async with ServerClient(url, token="fake-operator") as client:
            runtime = object.__new__(Runtime)
            runtime._client = client
            runtime.settings = SimpleNamespace(
                command_timeout_s=2, request_timeout_s=2)
            runtime.store = Store(SystemClock())
            runtime._poller = Poller(
                client.fetch_state, runtime.store, interval_s=30)
            poll_task = asyncio.create_task(runtime._poller.run())
            statuses: list[str] = []
            try:
                result = await asyncio.wait_for(
                    runtime.execute_pulse(
                        device_id, None,
                        lambda status, _reason, _request_id: statuses.append(
                            status),
                    ),
                    timeout=4,
                )
                snapshot = runtime.store.state.snapshot
                left = next(
                    device for party in snapshot.parties
                    for device in party.devices if device.id == device_id)
                return result, statuses, left
            finally:
                runtime._poller.stop()
                await poll_task

    result, statuses, left = asyncio.run(exercise())
    assert result == "succeeded"
    assert statuses == expected_statuses
    assert api._pulse_request_id == 1
    assert left.last_pulse is not None and left.last_pulse.status == "succeeded"


def test_runtime_saves_token_only_after_server_authentication(fake_api_server) -> None:
    url, _ = fake_api_server
    credentials = FakeTokenRepository()
    runtime = Runtime(
        StubPage(), FakeSettingsRepository(), Settings(),
        token_repo=credentials,
    )
    runtime.start = lambda: None

    error = asyncio.run(runtime.save_connection(url, "fake-operator"))

    assert error is None
    assert credentials.token == "fake-operator"
    assert runtime.settings.token == "fake-operator"
    assert "token" not in runtime.settings.to_storage()


def test_runtime_does_not_save_a_rejected_token(fake_api_server) -> None:
    url, _ = fake_api_server
    credentials = FakeTokenRepository()
    runtime = Runtime(
        StubPage(), FakeSettingsRepository(), Settings(),
        token_repo=credentials,
    )
    runtime.start = lambda: None

    error = asyncio.run(runtime.save_connection(url, "not-a-token"))

    assert error is not None
    assert credentials.token is None
    assert runtime.settings.token is None


def test_runtime_sign_out_clears_token_without_server_access() -> None:
    credentials = FakeTokenRepository("saved-token")
    runtime = Runtime(
        StubPage(), FakeSettingsRepository(), Settings(token="saved-token"),
        token_repo=credentials,
    )
    runtime.start = lambda: None

    error = asyncio.run(runtime.save_connection(
        "https://unreachable.invalid", ""))

    assert error is None
    assert credentials.token is None
    assert runtime.settings.token is None


@pytest.mark.parametrize("scenario", ["stale", "offline"])
def test_fake_server_refuses_garage_pulse_without_fresh_healthy_telemetry(
    scenario: str,
) -> None:
    api = FakeApi(scenario)
    status, body = api.pulse("sonoff-2")
    assert status == 503
    assert body["status"] == "rejected"
    assert "unavailable" in body["reason"]


def test_fake_server_same_key_deduplicates_and_rejects_changed_payload(fake_api_server) -> None:
    url, _ = fake_api_server

    async def exercise():
        async with ServerClient(url, token="fake-operator") as client:
            first = await client.submit_command(
                "valve-controller", action_id="set_output",
                params={"name": "relay4", "state": True}, idempotency_key="light-key")
            repeated = await client.submit_command(
                "valve-controller", action_id="set_output",
                params={"name": "relay4", "state": True}, idempotency_key="light-key")
            with pytest.raises(CommandApiError) as conflict:
                await client.submit_command(
                    "valve-controller", action_id="set_output",
                    params={"name": "relay4", "state": False}, idempotency_key="light-key")
            return first, repeated, conflict.value

    first, repeated, conflict = asyncio.run(exercise())
    assert first.command_id == repeated.command_id
    assert repeated.deduplicated
    assert conflict.code == "idempotency_conflict"


@pytest.mark.parametrize("scenario", ["stale", "offline"])
def test_fake_server_unavailable_scenarios_refuse_commands(scenario) -> None:
    api = FakeApi(scenario)
    status, body = api.submit({
        "action_id": "set_mode", "params": {"value": "manual"},
        "idempotency_key": "key", "client_origin": "test",
    })
    assert status == 503
    assert body["error"]["code"] == "device_unavailable"


def test_fake_server_malformed_scenario_is_a_malformed_snapshot(fake_api_server) -> None:
    api = FakeApi("malformed")
    server = FakeTestHttpServer(("127.0.0.1", 0), Handler)
    server.api = api
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        async def read_state():
            async with ServerClient(
                    f"http://127.0.0.1:{server.server_port}", token="fake-viewer") as client:
                return await client.fetch_state()

        with pytest.raises(MalformedResponse, match="generated_at or parties"):
            asyncio.run(read_state())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_fake_server_slow_scenario_waits_for_post_attempt_observation() -> None:
    api = FakeApi("slow")
    status, receipt = api.submit({
        "action_id": "set_output", "params": {"name": "relay4", "state": True},
        "idempotency_key": "slow-light", "client_origin": "test",
    })
    assert status == 202
    command_id = receipt["command_id"]
    statuses = []
    for _ in range(3):
        command = api.command(command_id)
        assert command is not None
        statuses.append(command["status"])
    assert statuses == ["acknowledged", "acknowledged", "confirmed"]
