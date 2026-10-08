"""Async client for the Buzsák server; the only module that does network I/O (SRV-10, SRV-11, SEC-02).

Returns the validated JSON object; mapping it to domain models is `domain/snapshot.py`'s job.
Neither the token nor response bodies are ever logged (SEC-03, SEC-05).
"""

from __future__ import annotations

import ssl
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Mapping

import httpx

from buzsak_app.api import endpoints
from buzsak_app.api.trust import server_ssl_context


class ApiError(Exception):
    """Base class; the message is safe to show to the user."""


class ConnectionFailed(ApiError):
    """The server could not be reached or did not answer in time."""


class CertificateRejected(ConnectionFailed):
    """The TLS handshake failed because the certificate is not the pinned one (SEC-02)."""


class Unauthorized(ApiError):
    """HTTP 401 or 403: the token is missing, rejected or lacks the role (SEC-02, SRV-07)."""

    def __init__(self, status_code: int) -> None:
        super().__init__(
            "access token rejected" if status_code == 403 else "access token missing or invalid")
        self.status_code = status_code


class HttpsRequired(ApiError):
    """HTTP 426: the server only accepts HTTPS (SEC-02)."""

    def __init__(self) -> None:
        super().__init__("server requires HTTPS")
        self.status_code = 426


class HttpStatusError(ApiError):
    """The server answered with an unexpected HTTP status."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"server returned HTTP {status_code}")
        self.status_code = status_code


class CommandApiError(ApiError):
    """A structured command API rejection; never includes a raw response body."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class AmbiguousCommandResult(ConnectionFailed):
    """Command submission may have reached the server; query/retry only with its same key."""


class AmbiguousPulseResult(ConnectionFailed):
    """A momentary pulse may have been accepted; never submit it again automatically."""


class PulseRejected(ApiError):
    """The server rejected the pulse before acceptance."""

    def __init__(self, status_code: int, reason: str) -> None:
        super().__init__(reason)
        self.status_code = status_code


@dataclass(frozen=True)
class PulseReceipt:
    request_id: int


@dataclass(frozen=True)
class CommandReceipt:
    command_id: str
    status: str
    status_url: str
    expires_at: str
    deduplicated: bool


@dataclass(frozen=True)
class CommandStatus:
    command_id: str
    device_id: str
    action_id: str
    params: Mapping[str, Any]
    status: str
    reason: str | None
    created_at: str
    updated_at: str
    expires_at: str
    confirmation: Mapping[str, Any] | None
    outcome: Mapping[str, Any] | None


_COMMAND_STATES = frozenset({
    "pending", "dispatching", "sent", "acknowledged", "confirmed",
    "failed", "expired", "cancelled", "uncertain",
})


class MalformedResponse(ApiError):
    """The body is not the JSON shape this client requires."""


@dataclass(frozen=True)
class Readiness:
    """Result of `/readyz`: a 503 is a valid answer, not an error (SRV-02)."""

    ok: bool
    reason: str | None = None


class ServerClient:
    """One reusable HTTP session. Use as `async with`, or call `aclose()`."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout_s: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
        verify: ssl.SSLContext | None = None,
    ) -> None:
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if verify is None and base_url.lower().startswith("https://"):
            verify = server_ssl_context()
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout_s,
            transport=transport,
            verify=verify if verify is not None else True,
        )

    async def __aenter__(self) -> ServerClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def fetch_state(self) -> dict[str, Any]:
        """GET the dashboard snapshot (SRV-01)."""
        response = await self._get(endpoints.STATE_PATH)
        if response.status_code in (401, 403):
            raise Unauthorized(response.status_code)
        if response.status_code == 426:
            raise HttpsRequired()
        if response.status_code != 200:
            raise HttpStatusError(response.status_code)
        body = _json_object(response)
        if not isinstance(body.get("generated_at"), str) or not isinstance(body.get("parties"), list):
            raise MalformedResponse("state is missing generated_at or parties")
        return body

    async def is_alive(self) -> bool:
        """GET `/healthz`: True only for HTTP 200 (SRV-02)."""
        return (await self._get(endpoints.HEALTHZ_PATH)).status_code == 200

    async def readiness(self) -> Readiness:
        """GET `/readyz`: 200 is ready, 503 is not ready with a reason (SRV-02)."""
        response = await self._get(endpoints.READYZ_PATH)
        if response.status_code == 200:
            return Readiness(ok=True)
        if response.status_code == 503:
            try:
                reason = _json_object(response).get("reason")
            except MalformedResponse:
                reason = None  # e.g. an HTML error page from a proxy
            return Readiness(ok=False, reason=reason if isinstance(reason, str) else None)
        raise HttpStatusError(response.status_code)

    async def submit_command(
        self,
        device_id: str,
        *,
        action_id: str,
        params: Mapping[str, Any],
        idempotency_key: str,
        client_origin: str = "android-app",
        expected_revisions: Mapping[str, int] | None = None,
    ) -> CommandReceipt:
        """Submit one explicit command intent; this method never retries (CTL-01, SRV-04)."""
        body: dict[str, Any] = {
            "action_id": action_id,
            "params": dict(params),
            "idempotency_key": idempotency_key,
            "client_origin": client_origin,
        }
        if expected_revisions is not None:
            body["expected_revisions"] = dict(expected_revisions)
        try:
            response = await self._http.post(
                endpoints.COMMANDS_PATH.format(device_id=device_id), json=body)
        except httpx.TimeoutException:
            raise AmbiguousCommandResult(
                "command response was not received; check its status before retrying") from None
        except httpx.TransportError as error:
            if _caused_by_tls(error):
                raise CertificateRejected(
                    "server certificate is not trusted") from None
            raise AmbiguousCommandResult(
                "command outcome is unknown; check its status before retrying") from None
        if response.status_code != 202:
            raise _command_error(response)
        payload = _json_object(response)
        command_id = payload.get("command_id")
        status = payload.get("status")
        status_url = payload.get("status_url")
        expires_at = payload.get("expires_at")
        deduplicated = payload.get("deduplicated", False)
        if (
            not isinstance(command_id, str) or not command_id
            or status not in _COMMAND_STATES
            or not isinstance(status_url, str) or not status_url.startswith("/api/v1/commands/")
            or not isinstance(expires_at, str)
            or not isinstance(deduplicated, bool)
        ):
            raise MalformedResponse(
                "command acceptance response is incomplete")
        return CommandReceipt(command_id, status, status_url, expires_at, deduplicated)

    async def command_status(self, command_id: str) -> CommandStatus:
        """Read one command's lifecycle state (SRV-05)."""
        response = await self._get(endpoints.COMMAND_STATUS_PATH.format(command_id=command_id))
        if response.status_code != 200:
            raise _command_error(response)
        payload = _json_object(response)
        fields = ("command_id", "device_id", "action_id", "status",
                  "created_at", "updated_at", "expires_at")
        if any(not isinstance(payload.get(key), str) or not payload[key] for key in fields):
            raise MalformedResponse("command status response is incomplete")
        if payload["status"] not in _COMMAND_STATES:
            raise MalformedResponse("command status is unknown")
        params = payload.get("params")
        reason = payload.get("reason")
        confirmation = payload.get("confirmation")
        outcome = payload.get("outcome")
        if not isinstance(params, dict) or (reason is not None and not isinstance(reason, str)):
            raise MalformedResponse("command status fields have invalid types")
        if confirmation is not None and not isinstance(confirmation, dict):
            raise MalformedResponse(
                "command confirmation must be an object or null")
        if outcome is not None and not isinstance(outcome, dict):
            raise MalformedResponse(
                "command outcome must be an object or null")
        return CommandStatus(
            command_id=payload["command_id"], device_id=payload["device_id"],
            action_id=payload["action_id"], params=params, status=payload["status"],
            reason=reason, created_at=payload["created_at"],
            updated_at=payload["updated_at"], expires_at=payload["expires_at"],
            confirmation=confirmation, outcome=outcome,
        )

    async def cancel_command(self, command_id: str) -> str:
        """Cancel a command only while pending; cancellation is never retried."""
        try:
            response = await self._http.delete(
                endpoints.COMMAND_STATUS_PATH.format(command_id=command_id))
        except httpx.TimeoutException:
            raise ConnectionFailed(
                "command cancellation response was not received") from None
        except httpx.TransportError:
            raise ConnectionFailed(
                "command cancellation outcome is unknown") from None
        if response.status_code != 200:
            raise _command_error(response)
        payload = _json_object(response)
        if payload.get("command_id") != command_id or payload.get("status") != "cancelled":
            raise MalformedResponse("command cancellation response is invalid")
        return "cancelled"

    async def request_pulse(self, device_id: str) -> PulseReceipt:
        """Enqueue one server-controlled 0.5 s pulse; never retry (CTL-11)."""
        try:
            response = await self._http.post(
                endpoints.PULSE_PATH.format(device_id=device_id))
        except httpx.TimeoutException:
            raise AmbiguousPulseResult(
                "pulse acceptance is unknown; check Garage status before another request") from None
        except httpx.TransportError as error:
            if _caused_by_tls(error):
                raise CertificateRejected(
                    "server certificate is not trusted") from None
            raise AmbiguousPulseResult(
                "pulse outcome is unknown; check Garage status before another request") from None
        if response.status_code in (401, 403):
            raise Unauthorized(response.status_code)
        if response.status_code == 426:
            raise HttpsRequired()
        if response.status_code in (409, 503):
            try:
                payload = _json_object(response)
                reason = payload.get("reason")
            except MalformedResponse:
                reason = None
            safe_reason = (
                reason if isinstance(reason, str) and reason
                else "pulse was refused by the server"
            )
            raise PulseRejected(response.status_code, safe_reason[:200])
        if response.status_code != 202:
            raise HttpStatusError(response.status_code)
        try:
            payload = _json_object(response)
        except MalformedResponse:
            raise AmbiguousPulseResult(
                "pulse acceptance response was malformed; check Garage status before another request") from None
        request_id = payload.get("request_id")
        if payload.get("status") != "accepted" or type(request_id) is not int or request_id <= 0:
            raise AmbiguousPulseResult(
                "pulse acceptance response was incomplete; check Garage status before another request")
        return PulseReceipt(request_id)

    async def _get(self, path: str) -> httpx.Response:
        try:
            return await self._http.get(path)
        except httpx.TimeoutException:
            raise ConnectionFailed("server did not answer in time") from None
        except (httpx.TransportError, httpx.InvalidURL) as error:
            if _caused_by_tls(error):
                raise CertificateRejected(
                    "server certificate is not trusted") from None
            raise ConnectionFailed("server unreachable") from None


def _caused_by_tls(error: BaseException) -> bool:
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        if isinstance(current, ssl.SSLError):
            return True
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return False


def _command_error(response: httpx.Response) -> CommandApiError | HttpStatusError:
    try:
        error = response.json().get("error")
        if not isinstance(error, dict):
            raise ValueError
        code = error.get("code")
        message = error.get("message")
        if not isinstance(code, str) or not isinstance(message, str):
            raise ValueError
    except (ValueError, AttributeError):
        return HttpStatusError(response.status_code)
    safe_messages = {
        "unauthenticated": "access token missing or invalid",
        "forbidden": "this account cannot control the device",
        "https_required": "server requires HTTPS",
        "control_disabled": "valve control is disabled by the server",
        "device_unavailable": "device is unavailable or its data is stale",
        "device_interlock": "device safety interlock rejected the action",
        "device_rejected": "device rejected the action",
        "stale_telemetry": "device data is stale; refresh before trying again",
        "stale_revision": "device state changed; refresh before trying again",
        "precondition_failed": "device state does not allow this action",
        "device_interlock": "device rejected the action because of its safety interlock",
        "conflict": "another command is unresolved",
        "queue_full": "command queue is full",
        "idempotency_conflict": "this action key was already used for a different request",
        "unsupported_action": "server does not support this action",
        "invalid_request": "server rejected the command format",
        "not_found": "device or command was not found",
        "clock_untrusted": "server clock is not trusted; command was not accepted",
        "unavailable": "command service is unavailable",
    }
    return CommandApiError(response.status_code, code, safe_messages.get(code, "command was rejected"))


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        raise MalformedResponse("response is not valid JSON") from None
    if not isinstance(body, dict):
        raise MalformedResponse("response is not a JSON object")
    return body
