"""API client against an in-process mock transport; no network (SRV-01, SRV-02, SRV-11, SEC-02)."""

from __future__ import annotations

import asyncio
import ssl

import httpx
import pytest
from conftest import load_state_fixture

from buzsak_app.api.client import (
    AmbiguousCommandResult,
    CertificateRejected,
    CommandApiError,
    CommandReceipt,
    CommandStatus,
    ConnectionFailed,
    HttpsRequired,
    HttpStatusError,
    MalformedResponse,
    Readiness,
    ServerClient,
    Unauthorized,
)


def _run(handler, call, **client_kwargs):
    async def go():
        async with ServerClient(
            "http://server.test:8080/", transport=httpx.MockTransport(handler), **client_kwargs
        ) as client:
            return await call(client)

    return asyncio.run(go())


def _json(status, body):
    return lambda request: httpx.Response(status, json=body)


def test_fetch_state_returns_the_json_object() -> None:
    payload = load_state_fixture("normal")
    assert _run(_json(200, payload), lambda c: c.fetch_state()) == payload


def test_requests_the_state_path_under_the_base_url() -> None:
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json=load_state_fixture("normal"))

    _run(handler, lambda c: c.fetch_state())
    assert seen == ["http://server.test:8080/api/dashboard/state"]


def test_bearer_token_is_sent_when_configured() -> None:
    seen = []

    def handler(request):
        seen.append(request.headers.get("authorization"))
        return httpx.Response(200, json=load_state_fixture("normal"))

    _run(handler, lambda c: c.fetch_state(), token="s3cret")
    assert seen == ["Bearer s3cret"]


def test_no_authorization_header_without_token() -> None:
    seen = []

    def handler(request):
        seen.append("authorization" in request.headers)
        return httpx.Response(200, json=load_state_fixture("normal"))

    _run(handler, lambda c: c.fetch_state())
    assert seen == [False]


@pytest.mark.parametrize("status", [404, 500, 503])
def test_fetch_state_non_200_is_an_http_error(status) -> None:
    with pytest.raises(HttpStatusError) as info:
        _run(_json(status, {"error": "x"}), lambda c: c.fetch_state())
    assert info.value.status_code == status


@pytest.mark.parametrize("status", [401, 403])
def test_missing_or_rejected_token_is_unauthorized(status) -> None:
    body = {"error": {"code": "unauthenticated", "message": "x"}}
    with pytest.raises(Unauthorized) as info:
        _run(_json(status, body), lambda c: c.fetch_state())
    assert info.value.status_code == status


def test_https_required_is_its_own_error() -> None:
    with pytest.raises(HttpsRequired):
        _run(_json(426, {"error": {"code": "https_required"}}),
             lambda c: c.fetch_state())


def test_a_failed_tls_handshake_is_reported_as_an_untrusted_certificate() -> None:
    def handler(request):
        try:
            raise ssl.SSLCertVerificationError(
                "unable to get local issuer certificate")
        except ssl.SSLError as cause:
            raise httpx.ConnectError("handshake failed") from cause

    with pytest.raises(CertificateRejected) as info:
        _run(handler, lambda c: c.fetch_state())
    assert isinstance(info.value, ConnectionFailed)
    assert "not trusted" in str(info.value)


def test_a_plain_connect_error_stays_unreachable() -> None:
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(ConnectionFailed) as info:
        _run(handler, lambda c: c.fetch_state())
    assert not isinstance(info.value, CertificateRejected)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>nope</html>"),
        httpx.Response(200, json=[1, 2]),
        httpx.Response(200, json={"parties": []}),
        httpx.Response(200, json={"generated_at": "2026-10-05T12:00:00Z"}),
        httpx.Response(200, json={"generated_at": 5, "parties": []}),
        httpx.Response(
            200, json={"generated_at": "2026-10-05T12:00:00Z", "parties": {}}),
    ],
)
def test_fetch_state_rejects_malformed_bodies(response) -> None:
    with pytest.raises(MalformedResponse):
        _run(lambda request: response, lambda c: c.fetch_state())


def test_unknown_extra_fields_pass_through() -> None:
    payload = load_state_fixture("normal") | {"future": 1}
    assert _run(_json(200, payload), lambda c: c.fetch_state())["future"] == 1


def test_timeout_becomes_connection_failed() -> None:
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ConnectionFailed, match="in time"):
        _run(handler, lambda c: c.fetch_state())


def test_connect_error_becomes_connection_failed() -> None:
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ConnectionFailed, match="unreachable"):
        _run(handler, lambda c: c.fetch_state())


def test_error_messages_never_contain_the_token() -> None:
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ConnectionFailed) as info:
        _run(handler, lambda c: c.fetch_state(), token="s3cret")
    assert "s3cret" not in str(info.value)


def test_command_fake_server_accepts_exact_request_and_returns_receipt() -> None:
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path,
                    request.headers.get("authorization"), request.read()))
        return httpx.Response(202, json={
            "command_id": "c_123", "status": "pending",
            "status_url": "/api/v1/commands/c_123",
            "expires_at": "2026-10-07T12:00:12Z", "deduplicated": False,
        })

    result = _run(
        handler,
        lambda client: client.submit_command(
            "valve-controller", action_id="set_output",
            params={"name": "relay1", "state": True},
            idempotency_key="same-intent-key", expected_revisions={"mode": 4}),
        token="operator-token",
    )

    assert result == CommandReceipt(
        "c_123", "pending", "/api/v1/commands/c_123",
        "2026-10-07T12:00:12Z", False)
    method, path, auth, raw = seen[0]
    assert method == "POST"
    assert path == "/api/v1/devices/valve-controller/commands"
    assert auth == "Bearer operator-token"
    assert __import__("json").loads(raw) == {
        "action_id": "set_output", "params": {"name": "relay1", "state": True},
        "idempotency_key": "same-intent-key", "client_origin": "android-app",
        "expected_revisions": {"mode": 4},
    }


def test_command_fake_server_status_and_cancel() -> None:
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200, json={
                "command_id": "c_123", "device_id": "valve-controller",
                "action_id": "set_output", "params": {"name": "relay1", "state": True},
                "status": "confirmed", "reason": None,
                "created_at": "2026-10-07T12:00:00Z",
                "updated_at": "2026-10-07T12:00:02Z",
                "expires_at": "2026-10-07T12:00:12Z",
                "confirmation": {"observed_at": "2026-10-07T12:00:02Z"}, "outcome": None,
            })
        return httpx.Response(200, json={"command_id": "c_123", "status": "cancelled"})

    async def calls(client):
        status = await client.command_status("c_123")
        cancelled = await client.cancel_command("c_123")
        return status, cancelled

    status, cancelled = _run(handler, calls)
    assert isinstance(status, CommandStatus)
    assert status.status == "confirmed"
    assert status.confirmation == {"observed_at": "2026-10-07T12:00:02Z"}
    assert cancelled == "cancelled"
    assert seen == [
        ("GET", "/api/v1/commands/c_123"),
        ("DELETE", "/api/v1/commands/c_123"),
    ]


def test_command_fake_server_rejection_uses_stable_safe_error() -> None:
    def handler(request):
        return httpx.Response(409, json={
            "error": {"code": "precondition_failed", "message": "raw detail"}})

    with pytest.raises(CommandApiError) as info:
        _run(lambda request: handler(request), lambda client: client.submit_command(
            "valve-controller", action_id="set_output",
            params={"name": "relay1", "state": True}, idempotency_key="k"))
    assert info.value.code == "precondition_failed"
    assert "does not allow" in str(info.value)
    assert "raw detail" not in str(info.value)


def test_command_submit_timeout_is_ambiguous_and_never_retried() -> None:
    calls = []

    def handler(request):
        calls.append(request.method)
        raise httpx.ReadTimeout("lost response", request=request)

    with pytest.raises(AmbiguousCommandResult):
        _run(handler, lambda client: client.submit_command(
            "valve-controller", action_id="set_mode", params={"value": "manual"},
            idempotency_key="same-key"))
    assert calls == ["POST"]


@pytest.mark.parametrize("payload", [
    {"command_id": "c", "status": "unrecognized", "status_url": "/api/v1/commands/c",
     "expires_at": "x", "deduplicated": False},
    {"command_id": "c", "status": "pending", "status_url": "/unsafe/c",
     "expires_at": "x", "deduplicated": False},
])
def test_command_acceptance_rejects_invalid_response(payload) -> None:
    with pytest.raises(MalformedResponse):
        _run(_json(202, payload), lambda client: client.submit_command(
            "valve-controller", action_id="set_mode", params={"value": "manual"},
            idempotency_key="k"))


def test_is_alive() -> None:
    assert _run(_json(200, {"status": "ok"}), lambda c: c.is_alive()) is True
    assert _run(_json(500, {}), lambda c: c.is_alive()) is False


def test_readiness_ok() -> None:
    assert _run(_json(200, {"status": "ok"}),
                lambda c: c.readiness()) == Readiness(ok=True)


def test_readiness_503_is_not_ready_with_reason_not_an_error() -> None:
    body = {"status": "unavailable", "reason": "database unreachable"}
    assert _run(_json(503, body), lambda c: c.readiness()
                ) == Readiness(False, "database unreachable")


def test_readiness_503_with_non_json_body_is_still_not_ready() -> None:
    result = _run(lambda r: httpx.Response(
        503, text="<html>bad gateway</html>"), lambda c: c.readiness())
    assert result == Readiness(ok=False, reason=None)


def test_readiness_other_status_is_an_http_error() -> None:
    with pytest.raises(HttpStatusError):
        _run(_json(404, {}), lambda c: c.readiness())
