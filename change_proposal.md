# Change proposal for the Buzsák Pi 3 server

| | |
|---|---|
| **To** | Developer of `buzsak_pi3_server` |
| **From** | Buzsák App (Android client), `buzsak_app` |
| **Date** | 2026-10-06 |
| **Status** | Proposal. **Update 2026-10-07:** the server project has implemented most of it (see the table below) |
| **Question answered** | "If I cannot apply the control actions, what must change on the server side?" |

### Status update (2026-10-07)

Read from the server's code and docs; **not** yet confirmed on the live system, because `/api/dashboard/state` now needs a token that the app owner has not entered yet.

| CP | Item | Server code (read 2026-10-07) | Live check |
|---|---|---|---|
| CP-01 | Nested `automation.mist` / `automation.rain` | parsed | live valve health healthy/fresh (GET 2026-10-07) |
| CP-02..04 | Rain, `relayN_controllable` / `relayN_always_manual`, sensor details, firmware parameters | in `catalog.py` | live rain, sensor, firmware/IP readings rendered (GET 2026-10-07) |
| CP-05..07 | Command storage, `POST /api/v1/devices/{id}/commands`, `GET`/`DELETE` `/api/v1/commands/{id}`, one-attempt dispatcher, telemetry confirmation | implemented (migration `0003`) | relay4 LIGHT on/off confirmed live; no water relay or mode command |
| CP-08 | Capability enablement | `enabled` only when `control.valve_enabled` | relay4 `set_output` enabled and confirmed live |
| CP-09, CP-10 | Bearer tokens with viewer/operator/admin, HTTPS | **verified live**: `https://192.168.1.95` serves, state returns `401` without a token, `:8080` is closed | done |
| CP-11 | Staleness derived into health (`health.stale`) | implemented (documented) | open |
| CP-13, CP-14 | History, `/api/v1/state` | not seen | open |

Deviations from the proposal that the app must follow: the error body is `{"error": {"code", "message"}}`; the submit body requires `client_origin`; a status read is limited to the submitting principal (or admin); the dispatcher makes **one** device attempt and never retries.

Labels used below: **verified fact** (read from code or the live system on 2026-10-06, read-only GETs only), **inference**, **proposal**, **open decision**.

---

## 1. Original issue and summary

The following describes the situation when this proposal was written on 2026-10-06, before the changes recorded in the status update above. At that point the app could show a basic valve layout but could not issue commands. As of 2026-10-07, the server and app command path are implemented and one owner-approved relay4 LIGHT round trip is confirmed/restored; water-valve and mode commands remain untested, and the Android UI is not yet verified. The original gaps were:

| # | Blocker | Kind | Section |
|---|---|---|---|
| 1 | The server's valve adapter **rejects the controller's current payload**, so the valve controller is `offline` with 71 failures and no fresh data. Control is impossible while the server cannot read the device. | **Defect** | 3 (CP-01) |
| 2 | Even once readable, the server does not carry what the device exposes: the **rain automation**, per-relay `always_manual` / `controllable`, firmware, sensor error details. The app cannot mirror the device's own page. | Data gap | 4 (CP-02..CP-04) |
| 3 | There is **no command API**. Only a Sonoff `pulse` endpoint exists. `set_output` and `set_mode` are registered but permanently disabled. | Missing feature | 5 (CP-05..CP-08) |
| 4 | There is **no authentication and no HTTPS**. The server's own spec forbids anonymous command access (SEC-02, SEC-04). | Missing prerequisite | 6 (CP-09, CP-10) |
| 5 | Health says `healthy` while data is stale (OBS-01). The app cannot trust health to gate commands. | Defect | 7 (CP-11) |

Most of the design already exists in **your own `requirements.md`** (CMD-01..19, API-01..09, SEC-01..10, DB-04). This proposal does not invent a new design. It points at those requirements, adds the app-side contract details, and lists what is missing in code. Nothing in the app depends on a different design: if you choose another shape, tell the app owner and the app's API client (one module) is adapted.

---

## 2. Current state (verified facts)

### 2.1 Server

- Three processes (poller, dispatcher, web). Endpoints: `GET /healthz`, `GET /readyz`, `GET /`, `GET /api/dashboard/state`, `POST /api/dashboard/devices/<id>/pulse` (Sonoff only).
- Migrations: `0001_core_telemetry.sql`, `0002_pulse_requests.sql`. The only command table is `pulse_requests`. There are no tables for general commands, attempts, audit events or idempotency keys (DB-04, DB-10).
- `dispatcher/pulse.py` executes Sonoff pulses only. `dashboard/commands.py` only enqueues pulses. Its docstring states it intentionally skips CMD-01..19.
- `dashboard/queries.py`: `_ENABLED_CAPABILITIES = {("sonoff_minid", "pulse")}`; every other capability is reported with `enabled: false` and `disabled_reason: "Read-only initial release (UI-06); command dispatch is not implemented yet."`.
- No authentication, no TLS, no CSRF, no rate limit on any endpoint.
- No history endpoint and no `/api/v1`.

### 2.2 Valve controller (ESP32, firmware v0.9, `http://192.168.1.109/`)

Read with `GET /api/state` only. Top-level keys: `firmware`, `ip`, `mode`, `outputs[]`, `sensors[]`, `automation`.

- `outputs[]` items have the keys `name`, `label`, `state`, `controllable`, **`always_manual`**.
- `automation` is **nested**: `automation.mist{valve, target_pct, duty, valve_on, period_s, elapsed_s, sensor_valid, time_synced}` and `automation.rain{valve, valve_on, start_hour, start_minute, duration_s, has_last_run, last_run_duration_s, time_synced}`.
- `POST /api/mode?value=manual|automatic` closes **all valves first**, then switches.
- `POST /api/control?name=<relay>&state=0|1` returns `409` in automatic mode unless the output is `always_manual` (the LIGHT relay stays operable in automatic mode), `403` if not controllable, `404` if unknown, `400` if malformed.
- No authentication on `/api/*`.

### 2.3 Live symptom on the Pi (GET `/api/dashboard/state`, 2026-10-06 15:30)

```
garden-plc        health=healthy  fails=0
valve-controller  health=offline  fails=71  last_ok=14:41:12
                  err=automation: missing required field 'valve'
sonoff-1 / sonoff-2  health=healthy
```

---

## 3. CP-01: Fix the valve adapter (defect, prerequisite for everything else)

**Verified fact.** `adapters/valve_controller.py::_parse_automation` expects a *flat* `automation` object with `valve`, `target_pct`, … The device now returns `automation.mist` and `automation.rain`. I fed the live device payload to the server's own `parse_state()` and got:

```
AdapterParseError: automation: missing required field 'valve'
```

Every poll therefore fails, `device_health` goes to `offline` after 5 failures, and the last good values (from the older firmware) are shown as stale. `docs/adapters/valve_controller.md` describes the old shape (it also says `period_s = 600`; the device now reports 300, so the app must not assume a constant).

**Proposal**

1. Update `valve_controller.parse_state`, `extraction.extract_valve_controller`, `catalog.py` and `docs/adapters/valve_controller.md` for the nested `automation.mist` / `automation.rain` shape.
2. Keep DEV-05: a missing or mistyped field makes **that parameter** `invalid`, not the whole device. Today one bad field takes down all 20+ parameters (including the relay states). Parse sections independently (`outputs`, `sensors`, `automation.mist`, `automation.rain`) so a firmware change in one section degrades only that section.
3. Rename mist parameters consistently (suggestion): keep the existing `automation_*` ids for mist so the app keeps working, and add the rain ones in CP-02. If you prefer `mist_*` ids, tell the app owner: ids are presentation keys on the app side.
4. Add a fixture test from a real v0.9 payload (sanitised, no addresses of other systems) and keep the old shape as a second fixture (firmware compatibility, DEV-06).
5. Optional hardening: add a periodic adapter-version check so a future firmware change shows as "adapter incompatible" in `health.last_error` instead of a generic offline.

**Acceptance.** With the device untouched, `valve-controller` returns to `healthy` within one poll interval and all relay and sensor parameters have fresh `observed_at`.

---

## 4. Data parity: what the app needs from the state payload

The app builds its UI from `/api/dashboard/state` only (it never talks to the ESP32: app rule SSOT-03). To show the same information as the device's own page, the payload needs the following. All are **proposals**.

### CP-02: Rain automation parameters

New parameters (extraction from `automation.rain`):

| parameter_id | category | type | unit | note |
|---|---|---|---|---|
| `rain_valve_on` | boolean | bool | | rain valve commanded state |
| `rain_start_hour` | configuration | int | | 0..23 |
| `rain_start_minute` | configuration | int | | 0..59 |
| `rain_duration_s` | configuration | int | s | |
| `rain_has_last_run` | boolean | bool | | |
| `rain_last_run_duration_s` | continuous | int | s | `null`/`unavailable` when `rain_has_last_run` is false (never `0`, DEV-05) |
| `rain_time_synced` | boolean | bool | | |

Same freezing rule as mist: while `mode == manual` these are frozen, not live (device behaviour, already documented for `automation_*`).

### CP-03: Per-relay `controllable` and `always_manual`

**Why.** The device lets the LIGHT relay (`relay4`) be switched in automatic mode (`always_manual: true`) and returns `409` for valves in automatic mode. A client that gates only on `mode == manual` would wrongly lock the light in automatic mode, or (worse, for other firmware) offer a control the device will reject.

New configuration parameters, one pair per relay: `relayN_controllable`, `relayN_always_manual` (N = 1..4). The status LED stays read-only.

### CP-04: Sensor detail and firmware identity

| parameter_id | category | note |
|---|---|---|
| `sensor_a_ok`, `sensor_b_ok` | boolean | today `ok=false` only appears as `quality: invalid` on the values |
| `sensor_a_last_error`, `sensor_b_last_error` | diagnostic | `"" \| "timeout" \| "noframe"` |
| `sensor_a_age_s`, `sensor_b_age_s` | diagnostic | seconds since last good frame, `0` if never (the app renders "never", not `0`) |
| `firmware` | identity | e.g. `v0.9` |
| `ip` | identity | informational |

Not needed by the app: `raw`, `errors` counters, RS485 data (commissioning only; keep them out of the payload, DEV-06).

**Acceptance for CP-02..CP-04.** A new unit test per parameter, the `parameters` + `capabilities` seeds in `catalog.py` updated (one source of truth), a migration only if a schema change is needed (none expected: `parameters` are rows), and `docs/adapters/valve_controller.md` updated.

---

## 5. Command API and valve dispatch (the main work)

The design is already specified in your `requirements.md` Section 9 and 10. What is missing is the implementation. The app proposal (app spec SRV-04/SRV-05) matches it.

### CP-05: General command storage (DB-04, DB-10, DB-08)

New migration `0003_commands.sql` (with the pre-migration backup of DB-07), tables for: `commands` (identity, actor, client origin, device, action, params JSON, idempotency key and request fingerprint, acceptance sequence, state, timestamps, deadline, preconditions, attempt count, confirmation evidence, outcome JSON), `command_attempts`, `command_audit_events` (append-only), and idempotency records retained for the client retry window (DB-10). `pulse_requests` may stay as is for now, or be migrated later; the DEV-10 exception is not affected.

### CP-06: Submission and status API (API-01..05, CMD-01..04)

Proposed contract (the app's client is written against exactly this, paths in one place):

```
POST /api/v1/devices/{device_id}/commands
Authorization: Bearer <token>
Content-Type: application/json

{ "action_id": "set_output",
  "params": { "name": "relay1", "state": true },
  "idempotency_key": "2b9c0b0e-...-uuid4",
  "client_origin": "android-app",
  "expected_revisions": { "mode": 41 } }          // optional, CMD-15
```

```
202 Accepted
{ "command_id": "c_0192", "status": "pending",
  "status_url": "/api/v1/commands/c_0192", "expires_at": "2026-10-06T15:31:10Z" }
```

```
GET /api/v1/commands/{command_id}
200 { "command_id": "c_0192", "device_id": "valve-controller",
      "action_id": "set_output", "params": {...},
      "status": "pending|dispatching|sent|acknowledged|confirmed|failed|expired|cancelled|uncertain",
      "reason": null | "device_rejected" | "precondition_failed" | "timeout" | ...,
      "created_at": "...", "updated_at": "...", "expires_at": "...",
      "confirmation": { "rule": "outputs[relay1].state==true && mode==manual",
                        "evidence_observed_at": "..." } | null }

DELETE /api/v1/commands/{command_id}        // pending only, CMD-16
```

Error codes (API-05, stable `error.code` strings in a JSON body): `400 invalid_request`, `401 unauthenticated`, `403 forbidden`, `404 not_found`, `409 conflict` / `idempotency_conflict` / `precondition_failed` / `stale_revision`, `429 rate_limited`, `503 unavailable` (queue full, DB unhealthy, API-08). A repeated key with the same request returns the **original** `command_id` (CMD-03); same key with different content returns `409 idempotency_conflict`.

**App needs, in summary:** durable acceptance before returning the id (CMD-02), a server-authoritative deadline that restarts do not reset (CMD-04), no automatic server-side resend of an ambiguous command except where CMD-09 allows it (section below), and a status endpoint cheap enough to poll every 1 to 2 s.

### CP-07: Dispatcher support for the valve controller (CMD-01, 05, 06, 07, 09, 10, 13..15, 18, 19)

Add a valve-controller executor to the dispatcher, using the device calls documented in `docs/adapters/valve_controller.md`:

| Action | Device call | Preconditions, **rechecked immediately before sending** (CMD-05) | Confirmation (CMD-07) |
|---|---|---|---|
| `set_output` (`relay1..relay4`, `state`) | `POST /api/control?name=&state=` | device health `healthy`; **fresh** `mode == manual`, **or** the relay is `always_manual` (CP-03); relay `controllable`; no conflicting active command on the device | A fresh `GET /api/state` observed **after** the attempt shows `outputs[name].state == requested` **and**, for non-`always_manual` relays, `mode == manual` |
| `set_mode` (`manual \| automatic`) | `POST /api/mode?value=` | device `healthy`; fresh telemetry | Fresh `GET /api/state` shows `mode == requested`. Recommended extra evidence: all four relays `false` (the device closes all valves first) |

Outcome mapping for the device's replies:

| Device reply | Command outcome |
|---|---|
| `200` | `acknowledged` (never `confirmed` by itself, CMD-06), then wait for confirmation telemetry |
| `409` | `failed`, reason `device_interlock` (device was in automatic mode: the dispatcher's mode view was stale. **Do not route around it**, it is the intended interlock) |
| `403`, `404`, `400` | `failed`, reason `device_rejected` with the status code |
| timeout, connection reset, response lost after possible transmission | reconcile by a fresh `GET /api/state` first (CMD-10); satisfied → `confirmed`, contradicted → `failed`; unreadable → `uncertain` |
| confirmation window elapses (`acknowledged` but no matching state) | `uncertain` (CMD-10, CMD-11) |

Retry rule (CMD-09). `set_output` and `set_mode` are **idempotent level writes** (repeating the same value is harmless, documented in the adapter doc), so the server **may** retry transmission within the command deadline with a small bound (suggest 2 attempts). The app itself will **never** auto-retry; a user retry reuses the same idempotency key and returns the same command.

Safety (CMD-18, CMD-19):

- Hardware interlocks and firmware limits remain authoritative. The server cannot guarantee a maximum valve-on time while the Pi or network is down: say so in the docs and in the capability metadata.
- `confirmed` means "relay coil is in the commanded position", **not** "water is flowing" (there is no flow or valve-position sensor). Expose this in the capability metadata (CP-08) so the app can word the result correctly.
- Recommend a **per-action lifetime** of 10 to 15 s for relay commands (a late irrigation command must never fire minutes later) and a per-device FIFO with queue depth of a few entries (CMD-13/14). `set_mode` conflicts with any active relay command on the same device.
- A command that finishes as `uncertain` blocks further conflicting commands until reconciled (CMD-14).

### CP-08: Capability enablement and metadata (DEV-04, CMD-19, SSOT-08)

`dashboard/queries.py` currently hard-codes `_ENABLED_CAPABILITIES`. Proposal:

1. Enable `("valve_controller", "set_output")` and `("valve_controller", "set_mode")` **only when** CP-05..CP-07 and the security gate (CP-09/CP-10) are deployed. Until then keep the accurate current reason; the app shows it verbatim and keeps the controls disabled.
2. Make `disabled_reason` specific, not generic: `"device offline"`, `"data stale"`, `"authentication not configured"`, `"read-only mode"` (deployment flag, API-03).
3. Add capability metadata the app can render without hard-coding device knowledge (DEV-04: "declare ... safety preconditions, retry safety, expiry bounds, confirmation predicate"):

```json
{ "action_id": "set_output",
  "enabled": true, "disabled_reason": null,
  "params_schema": { "name": ["relay1","relay2","relay3","relay4"], "state": "bool" },
  "requires": { "parameter_id": "mode", "equals": "manual", "fresh": true,
                "except_when_true": "relay{n}_always_manual" },
  "effect": "relay_state_only",            // CMD-19: not water flow
  "retry_safe": true,
  "lifetime_s": 12,
  "confirmation": "outputs[name].state == state && (mode == manual || always_manual)" }
{ "action_id": "set_mode",
  "params_schema": { "value": ["manual","automatic"] },
  "side_effects": ["closes_all_valves"],  // the app shows a confirmation dialog
  "retry_safe": true, "lifetime_s": 12,
  "confirmation": "mode == value" }
```

The `requires` / `side_effects` fields are a proposal; any machine-readable equivalent is fine. The app additionally enforces its own rule independently (fresh `mode == manual`, never an optimistic state), so these fields are belt and braces, not the only guard.

### CP-12: Readiness of confirmation telemetry

CMD-07 needs a **fresh** observation after the attempt. The poller interval for the valve controller (default 1 s, POL-01) is fine, but the dispatcher should be able to request an immediate out-of-band read of `GET /api/state` for confirmation (ARC-02 allows the dispatcher to contact devices) instead of waiting for the next poll, and must write that observation through the normal observation path so the app sees it.

---

## 6. Security prerequisite (do before enabling any actuation)

**Verified fact.** There is no authentication or TLS anywhere, and the ESP32's `/api/*` has none either. Your spec already says command access shall never be anonymous (SEC-02, SEC-04). The Sonoff pulse is a documented, narrow exception (DEV-10); the valves are a different risk class: an unattended irrigation or mist valve left open.

### CP-09: Authentication and roles (SEC-04, SEC-05, SEC-06, SEC-07, SEC-10)

- Bearer tokens for API clients; at least `viewer` and `operator`; attributable per client (the app will hold one token for the owner's phone). Tokens stored hashed, rotatable and revocable, never in logs or responses. Commands require `operator`; `GET /api/dashboard/state` may stay anonymous read-only **if the owner decides so** (SEC-04 allows an explicit configuration).
- The app already sends `Authorization: Bearer …` when a token is configured (app SEC-02). The token is entered by the user, never committed.

### CP-10: HTTPS (SEC-02, SEC-09)

Terminate TLS on the Pi (reverse proxy or gunicorn) with a certificate the phone can trust (self-signed is acceptable only with explicit client trust: tell the app owner which CA or pin to import). When done, the app removes its cleartext allowance (app ADR-0002 follow-up). Also: request size and rate limits (SEC-09), no broad CORS, CSRF only where cookie authentication is used.

### Open decision OD-S1 (owner)

Whether the valve controls may go live on the LAN **without** CP-09/CP-10, as the Sonoff pulse does today. The app owner's current position, recorded in the app's rules: valve control is not enabled against hardware until the server reports the capability enabled and the owner explicitly approves. Recommended: authentication first (CP-09), HTTPS second (CP-10), and allow the capability to be enabled once CP-09 is in.

---

## 7. Health and freshness accuracy

### Live follow-up (2026-10-08)

An authenticated read-only GET at 10:26Z reported `valve-controller` as `degraded`, `stale=true`, `consecutive_failures=0`, and no `last_error`. Mode, relay and capability parameters were `quality=good` but `stale=true`, and controls correctly disabled. A later GET at 10:30Z was healthy/fresh; the owner-approved relay4 LIGHT UI round trip then confirmed and restored the light. Track the transient gap as OBS-04 and investigate its recurrence on the server; the app will not bypass stale telemetry by contacting the ESP32 directly.

### CP-11: Derive staleness into health (POL-04, POL-11, OBS-01)

**Verified facts.**

- On 2026-10-05 every parameter was 26 to 51 h old while every device reported `healthy` (OBS-01). Health only changes on poll success/failure; it is not derived from observation age.
- The CP-01 defect shows the opposite failure: the device answers HTTP but is reported `offline`, and the error text is only visible in `health.last_error`.

**Proposal.**

1. `health.status` should become `degraded`/`offline` when the newest observation is older than the stale threshold, even if the poller thread has silently stopped (a heartbeat per device thread, ARC-06, API-07).
2. `/readyz` should fail (or report degraded) when any enabled device has been failing longer than a configurable window.
3. Keep `consecutive_failures` and `last_error` in the payload (the app already shows them and warns when server data is old).
4. Command acceptance must refuse when health is not `healthy` **and** telemetry is fresh (the Sonoff path already refuses on non-healthy; apply the same to valves, CMD-12 for "device offline before transmission" is the alternative of staying pending until expiry: choose one and document it).

**Why it matters for commands.** The app gates relays on "fresh `mode == manual`". If the server reports `healthy` with 26 h old data, the app (correctly) refuses to enable the control; but the server's own pre-send recheck (CMD-05) must not rely on the same broken health signal either.

---

## 8. Remaining items

### CP-13: History endpoint (SRV-06, API-02, DB-04..DB-09)

`GET /api/v1/history?device_id=&parameter_id=&from=&to=&limit=&cursor=`, bounded range and page size, deterministic ordering (API-04), UTC timestamps, retention configurable per data class (DB-08). Needed only for the app's charts and deltas; **not** a blocker for control. Until then the app shows in-session sparklines labelled "this session only".

### CP-14: Versioned state endpoint (SRV-03, API-01)

`GET /api/v1/state` with the same payload as `/api/dashboard/state`. Optional; the app keeps the dashboard path and has one place to change it.

### CP-15: Documentation correction

`docs/dashboard.md` and `docs/adapters/valve_controller.md` are partly outdated (nested automation, `always_manual`, `period_s`). The app treats `dashboard/queries.py` as the truth for the payload.

---

## 9. Phasing

| Phase | Content | Unblocks in the app |
|---|---|---|
| **0** | CP-01 (adapter fix), CP-11.1 (health from staleness) | Live, correct valve-controller data (today it is stale/offline) |
| **1** | CP-02, CP-03, CP-04 (data parity), CP-15 | Full mirror of the device page: rain panel, per-relay rules, sensor errors, firmware. The app replaces its "not reported by the server" placeholder |
| **2** | CP-09, CP-10 (authentication, HTTPS), CP-05 (tables) | Safe to offer controls; app can drop the cleartext allowance |
| **3** | CP-06, CP-07, CP-08, CP-12 (commands, dispatch, capabilities), tested against a **simulated** valve controller | App enables controls (B-307), still behind the owner's explicit approval for the first real actuation |
| **4** | CP-13, CP-14 | Charts, deltas, `/api/v1` |

Phase 0 and 1 are read-only and low risk. The app does not need to wait for phase 3 to be useful.

---

## 10. Test and acceptance criteria

Server side (suggested, mapped to your AT list):

- **AT-02 / AT-05:** fixtures for both firmware payload shapes; one malformed section degrades only its own parameters.
- **AT-07 Command confirmation:** acknowledgment alone never confirms; `confirmed` only with fresh matching telemetry; `set_mode` confirmation reads back `mode`.
- **AT-08 Failure and ambiguity:** device `409`, `403`, `404`, timeout after possible transmission, acknowledged-but-unconfirmed → the expected `failed` / `uncertain` outcomes.
- **AT-09 Deduplication:** concurrent same-key/same-payload returns one command; same key with a different payload returns `409`.
- **AT-10, AT-11, AT-12:** FIFO and conflicts, stale revision and stale telemetry rejection, expiry, crash windows at claim/send/persist.
- **AT-13:** anonymous or `viewer` token cannot submit commands; tokens absent from logs and responses.
- **All command tests run against a simulated valve controller** (an in-process HTTP stub honouring the device's `200/400/403/404/409` and the `mode` interlock). **No test and no verification may switch a real relay without the owner's explicit approval.**

App side (already planned, no server work): the app has its own fake server (B-141) mirroring this contract, so controls are built and tested there first.

---

## 11. Open questions for the server developer / owner

| # | Question | Needed for |
|---|---|---|
| Q1 | Are `mist_*` / `rain_*` parameter ids acceptable, or do you prefer to keep `automation_*` for mist? (App maps by id; either works.) | CP-01, CP-02 |
| Q2 | Is `GET /api/dashboard/state` allowed to stay anonymous read-only while commands need a token (SEC-04)? | CP-09 |
| Q3 | Certificate approach for HTTPS and how the phone gets the trust anchor (SEC-02) | CP-10 |
| Q4 | Per-action lifetime, attempt limit, confirmation timeout for valve actions (your Section 17 "Command policy") | CP-07 |
| Q5 | Should `set_mode` confirmation also require all relays `false`? | CP-07 |
| Q6 | If a valve device is offline at submit time: refuse immediately, or stay `pending` until expiry (CMD-12)? App prefers refuse-immediately for valves | CP-07, CP-11 |
| Q7 | Who may reconcile an `uncertain` command (admin only, SEC-05) and where? | CP-07 |
| Q8 | Can the dispatcher do the immediate confirmation read described in CP-12? | CP-12 |

---

## 12. App-side progress (2026-10-07)

- The app has the server's HTTPS and bearer-token connection, typed command client, Greenhouse mode/relay controls, fresh-state/capability/schema gates, mode confirmation, and status polling.
- All controls remain disabled whenever the server capability is disabled; the app does not send commands in unit or fake-server tests.
- A timeout is shown as uncertain. Once a command ID is known, recovery is a status-only GET. A lost submission response exposes a same-key retry.
- On 2026-10-07, after explicit owner approval, one `relay4` LIGHT command was sent through the authenticated server API, confirmed by fresh telemetry, and restored to its original off state with a second confirmed command. The server's `control.valve_enabled` gate was therefore active for relay4. No water-valve relay or mode command was sent. Authenticated live readings now render through `GreenhouseReadings`; Android Developer Mode remains off, so the app UI itself is not yet visually verified.
- Terminal retry semantics remain open: the server deduplicates a repeated key to the original command, while the app spec requires same-key retries (B-211).
- The app keeps working read-only against a server that provides only `GET /api/dashboard/state` (app SRV-12).

---

## 13. Traceability

| This proposal | Server spec | App spec | App backlog |
|---|---|---|---|
| CP-01 | DEV-01, DEV-05, DEV-06, POL-04 | SRV-01, SRV-11 | OBS-03 |
| CP-02..04 | DEV-02, DEV-03, DEV-05 | UX-02, VLV-* | SRV-13 |
| CP-05..08, CP-12 | CMD-01..19, API-01..05, DB-04, DB-10, DEV-04 | SRV-04, SRV-05, CTL-*, VLV-02, VLV-03 | SRV-04, SRV-05, B-201, B-307 |
| CP-09, CP-10 | SEC-01..10 | SRV-07, SEC-02 | SRV-07, B-403 |
| CP-11 | POL-04, POL-11, API-07 | UPD-05 | OBS-01 |
| CP-13, CP-14 | API-01, API-02, API-04, DB-08 | SRV-03, SRV-06 | SRV-03, SRV-06 |

Device credentials (OTA login, firmware secrets) are deliberately **not** referenced in this document and must not be copied into either repository.
