# Server API contract as consumed

Covers DOC-03, SRV-01, SRV-02, SRV-07, SRV-10, SRV-11. The server's `dashboard/queries.py` is authoritative; this file records what the app reads and how it treats problems. Fixtures in `tests/fixtures/state/` are synthetic and mirror this shape.

## Transport and authentication (SRV-07, ADR-0003)

- Base URL `https://192.168.1.95` (Caddy `tls internal`). The client verifies the certificate against the pinned root CA in `api/trust.py` and nothing else. Plain `:8080` is closed on the server.
- `Authorization: Bearer <token>` is sent when a token is set. `/healthz` is open; `/api/dashboard/state` needs at least a `viewer` token; commands need `operator`.
- Token and certificate problems are told apart from "server down":

| Server / TLS result | Client error | Connection state shown |
|---|---|---|
| `401`, `403` | `Unauthorized` | Sign-in needed (banner: enter the token in System) |
| `426` (HTTPS required) | `HttpsRequired` | Server problem |
| TLS handshake rejects the certificate | `CertificateRejected` (a `ConnectionFailed`) | Server unreachable, last error "server certificate is not trusted" |
| Timeout, refused, DNS | `ConnectionFailed` | Server unreachable |
| Other non-200, bad body | `HttpStatusError`, `MalformedResponse` | Server problem |

## Command contract (server API-03, CMD §9)

Read from the server's `api/routes/commands.py`, `commands/service.py` and `dispatcher/commands.py` on 2026-10-07. Client and Runtime are tested against an in-process fake transport and the loopback-only simulated server; no command has been sent to live hardware.

- `POST /api/v1/devices/{device_id}/commands`, `operator`, JSON with exactly `action_id`, `params`, `idempotency_key` (1 to 128 characters), `client_origin` (1 to 64), and optional `expected_revisions` (`{parameter_id: int}`). Returns `202 {command_id, status, status_url, expires_at, deduplicated}`.
- `set_output` params `{name: relay1..relay4, state: bool}`; `set_mode` params `{value: manual|automatic}`.
- `GET /api/v1/commands/{id}` (`viewer`, only the submitting principal's own commands) returns `status`, `reason`, `confirmation`, `outcome`, `expires_at` and more. `DELETE` works only while `pending`.
- Statuses: `pending`, `dispatching`, `sent`, `acknowledged`, `confirmed`, `failed`, `expired`, `cancelled`, `uncertain`. Only fresh poller telemetry observed after the attempt confirms; a device `200` is only `acknowledged`.
- Failure reasons seen in the dispatcher: `device_interlock` (device `409`), `device_rejected` (other `4xx`), `ambiguous_device_response` (`5xx`), `transport_outcome_ambiguous`, `interrupted_dispatch`, `deadline_expired`, `stale_revision`, `precondition_failed`.
- **One device attempt, no server retry.** A lost submit response can be retried explicitly with the same idempotency key, returning the original command if accepted. Once a command ID is known, timeout recovery is a status-only GET. The server's same-key deduplication returns the original command even when terminal; re-dispatch of terminal failures is an open contract question (B-211).
- Error body `{"error": {"code", "message"}}`. Codes: `invalid_request`, `unauthenticated` (401), `forbidden` (403), `https_required` (426), `control_disabled` (403), `not_found`, `unsupported_action`, `idempotency_conflict`, `conflict`, `stale_telemetry`, `stale_revision`, `precondition_failed`, `device_unavailable` (503), `queue_full` (503), `clock_untrusted` (503), `unavailable` (503).
- Valve capabilities report `enabled: true` only when the server's deployment config sets `control.valve_enabled`; the app must still check the live data itself (fresh `mode == manual` unless the relay's fresh `always_manual` is true, and fresh `controllable == true`).
- Mode selection submits immediately on the user's segment tap, with the device's "closes all valves" side effect shown inline (ADR-0004); no optimistic mode update is rendered. On entering Greenhouse, the app requests an immediate snapshot; otherwise external device-page changes appear through Pi polling plus the app's foreground snapshot interval. The app never calls the ESP32 directly.
- The **SIMULATED** desktop preview uses an isolated local API, so it cannot reflect changes from the ESP32 webpage. Use the authenticated Pi API in live mode for real readings.

## Endpoints in use

| Endpoint | Status on server | Client method | Result |
|---|---|---|---|
| `GET /api/dashboard/state` (SRV-01) | available; viewer bearer required | `ServerClient.fetch_state()` | JSON object, then `parse_snapshot()` |
| `GET /healthz` (SRV-02) | available | `is_alive()` | True only for HTTP 200 |
| `GET /readyz` (SRV-02) | available | `readiness()` | 200 ready; 503 not ready with optional reason |

Paths are defined only in `api/endpoints.py`. The app command client implements SRV-04/05; history (SRV-06) and versioned state (SRV-03) remain unavailable. Authentication is implemented (SRV-07); the app sends `Authorization: Bearer <token>` when a token is configured.

## State payload

```
generated_at          UTC "YYYY-MM-DDTHH:MM:SSZ"                      required
parties[]             in server order                                 required
  id, label, kind     GARAGE has kind "matter"
  configured          false only for the GARAGE placeholder
  note                present on the placeholder
  devices[]
    id, label, address, enabled
    health            {status, last_success_at, last_error, consecutive_failures, stale?}
    parameters[]      {id, category, unit, value, value_type, quality, stale,
                       observed_at, last_changed_at, revision, has_data}
    capabilities[]    {action_id, params_schema, enabled, disabled_reason}
    last_pulse        {status, requested_at, executed_at, error} or null
```

Facts that shape the code (verified in `queries.py`):
- `value` is a string; `value_type` is `bool`, `int`, `float`, `string` or `null`.
- A parameter with no observation has `has_data: false`, null `value`/`value_type`/`observed_at`, and quality `unavailable`. The client distinguishes it as **no data**.
- `stale` is computed by the server at read time and is set only when quality is `good`.
- An invalid or unavailable poll keeps the last value, so `value` can be present while quality is not `good`.
- `params_schema` is a parsed object, or the raw string if the server could not parse it.
- Valve catalogs include `relayN_controllable`, `relayN_always_manual`, rain automation, sensor diagnostics and firmware; the app treats unknown/missing values as unavailable and fails controls closed.
- `automation_*` values freeze while `mode == manual` but keep quality `good` (see `domain/automation.py`).

## Value states

| App state | Server input | Rendered as |
|---|---|---|
| `GOOD` | quality `good`, `stale` false, valid value | live value |
| `STALE` | quality `good` with `stale` true, or quality `stale` | last value, marked stale |
| `UNAVAILABLE` | quality `unavailable` | last value (if any), marked unavailable |
| `INVALID` | quality `invalid`, an unknown quality, or malformed data | no trusted value |
| `NO_DATA` | `has_data` false | "no data", never `0` or off |

`false` and `0` are ordinary `GOOD` values.

## Error handling

| Situation | Behavior |
|---|---|
| Timeout, connection refused, bad URL | `ConnectionFailed`, with a message that never contains the token |
| Unexpected HTTP status on state | `HttpStatusError(status_code)` |
| Body is not JSON, not an object, or lacks `generated_at`/`parties` | `MalformedResponse` |
| Unparseable `generated_at`, or `parties` not a list | `SnapshotFormatError`; the caller keeps the previous snapshot |
| Parameter has a malformed value, bad `observed_at`, unknown quality, or a good quality with no value | Parameter kept as `INVALID` with `issue` text, and an entry in `Snapshot.issues` |
| Party, device, parameter or capability without an id | Skipped, with an entry in `Snapshot.issues` |
| Capability `enabled` is not literally `true` (missing, `"true"`, `1`) | Disabled (SSOT-08) |
| Unknown fields, categories, parameters or health statuses | Tolerated; unknown parameters use the generic presentation |
