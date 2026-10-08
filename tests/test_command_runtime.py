"""Runtime command lifecycle over a fake HTTP API; no device or live server is used."""

from __future__ import annotations

import asyncio

import httpx

from buzsak_app.api.client import ServerClient
from buzsak_app.settings import Settings
from buzsak_app.ui.app import Runtime


class StubPage:
    def update(self) -> None:
        pass


def test_runtime_submits_once_and_polls_until_confirmed() -> None:
    requests = []
    states = iter(["acknowledged", "confirmed"])

    def fake_server(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.method == "POST":
            return httpx.Response(202, json={
                "command_id": "c_fake", "status": "pending",
                "status_url": "/api/v1/commands/c_fake",
                "expires_at": "2026-10-07T12:00:12Z", "deduplicated": False,
            })
        status = next(states)
        return httpx.Response(200, json={
            "command_id": "c_fake", "device_id": "valve-controller",
            "action_id": "set_output", "params": {"name": "relay1", "state": False},
            "status": status, "reason": None,
            "created_at": "2026-10-07T12:00:00Z",
            "updated_at": "2026-10-07T12:00:02Z",
            "expires_at": "2026-10-07T12:00:12Z",
            "confirmation": {"observed_at": "2026-10-07T12:00:02Z"} if status == "confirmed" else None,
            "outcome": None,
        })

    runtime = Runtime(
        StubPage(), None,
        Settings(server_url="http://fake.test", command_timeout_s=4),
    )
    runtime._client = ServerClient(
        "http://fake.test", token="fake-operator",
        transport=httpx.MockTransport(fake_server),
    )
    updates = []

    async def exercise() -> str:
        try:
            return await runtime.execute_command(
                "valve-controller", "set_output",
                {"name": "relay1", "state": False}, "stable-key",
                lambda status, reason=None, command_id=None: updates.append(
                    (status, reason, command_id)),
            )
        finally:
            await runtime._client.aclose()

    assert asyncio.run(exercise()) == "confirmed"
    assert requests.count(
        ("POST", "/api/v1/devices/valve-controller/commands")) == 1
    assert requests.count(("GET", "/api/v1/commands/c_fake")) == 2
    assert [status for status, _, _ in updates] == [
        "pending", "acknowledged", "confirmed"]


def test_runtime_does_not_submit_without_a_client() -> None:
    runtime = Runtime(StubPage(), None, Settings())
    try:
        asyncio.run(runtime.execute_command(
            "valve-controller", "set_mode", {"value": "manual"}, "key",
            lambda status, reason=None, command_id=None: None,
        ))
    except Exception as error:
        assert "not running" in str(error)
    else:
        raise AssertionError("missing client must not submit")


def test_preview_connection_changes_are_not_persisted() -> None:
    class SettingsRepo:
        saves = 0

        async def save(self, settings):
            self.saves += 1
            return True

    repo = SettingsRepo()
    runtime = Runtime(StubPage(), repo, Settings(), preview_mode=True)
    runtime.start = lambda: None

    async def exercise():
        return await runtime.save_connection(
            "http://127.0.0.1:8766", "fake-operator")

    assert asyncio.run(exercise()) is None
    assert repo.saves == 0
    assert runtime.settings.server_url == "http://127.0.0.1:8766"
    assert runtime.settings.token == "fake-operator"


def test_live_connection_changes_are_not_persisted() -> None:
    class SettingsRepo:
        saves = 0

        async def save(self, settings):
            self.saves += 1
            return True

    repo = SettingsRepo()
    runtime = Runtime(StubPage(), repo, Settings(), live_mode=True)
    runtime.start = lambda: None

    async def exercise():
        return await runtime.save_connection(
            "https://192.168.1.95", "operator-token")

    assert asyncio.run(exercise()) is None
    assert repo.saves == 0
    assert runtime.settings.token == "operator-token"


def test_runtime_timeout_is_uncertain_then_status_check_confirms_without_resubmit() -> None:
    requests = []
    confirmation_available = False

    def fake_server(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.method == "POST":
            return httpx.Response(202, json={
                "command_id": "c_timeout", "status": "pending",
                "status_url": "/api/v1/commands/c_timeout",
                "expires_at": "2026-10-07T12:00:12Z", "deduplicated": False,
            })
        status = "confirmed" if confirmation_available else "acknowledged"
        return httpx.Response(200, json={
            "command_id": "c_timeout", "device_id": "valve-controller",
            "action_id": "set_mode", "params": {"value": "manual"},
            "status": status, "reason": None,
            "created_at": "2026-10-07T12:00:00Z",
            "updated_at": "2026-10-07T12:00:02Z",
            "expires_at": "2026-10-07T12:00:12Z",
            "confirmation": None, "outcome": None,
        })

    runtime = Runtime(
        StubPage(), None,
        Settings(server_url="http://fake.test", command_timeout_s=0.01),
    )
    runtime._client = ServerClient(
        "http://fake.test", token="fake-operator",
        transport=httpx.MockTransport(fake_server),
    )
    updates = []

    async def exercise():
        nonlocal confirmation_available
        try:
            first = await runtime.execute_command(
                "valve-controller", "set_mode", {
                    "value": "manual"}, "stable-key",
                lambda status, reason=None, command_id=None: updates.append(
                    (status, reason, command_id)),
            )
            confirmation_available = True
            second = await runtime.check_command_status(
                "c_timeout",
                lambda status, reason=None, command_id=None: updates.append(
                    (status, reason, command_id)),
            )
            return first, second
        finally:
            await runtime._client.aclose()

    assert asyncio.run(exercise()) == ("uncertain", "confirmed")
    assert updates[-2:] == [
        ("uncertain", "client_confirmation_timeout", "c_timeout"),
        ("confirmed", None, "c_timeout"),
    ]
    assert requests.count(
        ("POST", "/api/v1/devices/valve-controller/commands")) == 1
    assert requests.count(("GET", "/api/v1/commands/c_timeout")) >= 2
