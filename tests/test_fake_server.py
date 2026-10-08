"""Exercise the bundled fake API over HTTP on loopback only; never contacts a device."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from buzsak_app.api.client import CommandApiError, MalformedResponse, ServerClient
from buzsak_app.domain.snapshot import parse_snapshot

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
