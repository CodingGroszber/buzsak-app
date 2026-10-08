# Architecture

Covers ARC-04..ARC-10, ARC-06, SRV-10, DOC-02.

## Module boundaries

```mermaid
flowchart TD
    Server["Buzsák HTTP API"] --> Client["api/client.py\nHTTP, auth, response validation"]
    Client --> Poller["state/poller.py\nsequential fetch + parse"]
    Poller --> Domain["domain/snapshot.py\nvalidated immutable models"]
    Domain --> Store["state/store.py + diff.py\nreplace snapshot + notify"]
    Store --> View["ui/app_view.py\nrender snapshot"]
    View --> Runtime["ui/runtime.py\nhandle UI intents"]
    Runtime --> Client
    Boot["ui/app.py\ncomposition root"] --> Runtime
    Boot --> Settings["state/settings_repo.py\nordinary preferences"]
    Boot --> Token["state/token_repository.py\nsecure credential port"]
```

`ui/app.py` is the composition root: it attaches Flet services, loads settings, selects fake/live session configuration, constructs `Runtime`, and starts it. `Runtime` owns the API client, poller, store and `AppView`; it also coordinates command and pulse lifecycles and restarts the connection when settings change. `AppView` is presentation-only: it builds tabs, subscribes to store updates, applies diffs and forwards user intents through callbacks.

`api/` is the only package that performs HTTP (`SRV-10`). It returns validated JSON objects and typed transport errors; `domain/` parses snapshots into frozen dataclasses and represents value quality explicitly. `state/` owns the immutable application snapshot, diffs, serialized polling, ordinary settings persistence and the secure-token repository protocol. `ui/runtime.py` is the UI-layer orchestrator for commands because its workflows are initiated and rendered by controls; it never mutates reported physical state optimistically.

## Data and command flows

```mermaid
sequenceDiagram
    participant P as Poller
    participant A as API client
    participant D as Domain parser
    participant S as Store
    participant V as AppView
    P->>A: fetch_state()
    A-->>P: validated JSON
    P->>D: parse_snapshot(payload)
    D-->>P: immutable Snapshot
    P->>S: apply_snapshot(snapshot)
    S-->>V: AppState + SnapshotDiff
    V->>V: update changed controls
```

Controls dispatch intents to `Runtime`. Idempotent valve commands use the server command API and its status endpoint; the garage pulse is a single non-idempotent POST, then GET-only snapshot observation. `Runtime` never retransmits a pulse. In both cases, server-reported snapshots/status remain authoritative.

## Security and settings

URL, poll interval and timeouts use Flet `SharedPreferences`; the serialized `Settings` intentionally excludes the token. After an authenticated state snapshot validates, the token is stored through `SecureTokenRepository` backed by Flet Secure Storage / Android Keystore (ADR-0006). Sign out removes it. Fake/live launcher credentials are session-only. Server-side expiry and revocation remain authoritative.

## Guardrails and tests

`tests/test_architecture.py` enforces downward package imports, keeps Flet out of `api/`, `domain/` and `state/`, ensures HTTP client imports remain within `api/`, and checks that the composition root, view and Runtime stay in separate modules. Behavior and lifecycle contracts are tested in the domain, state, API, UI and loopback fake-server suites. The fake server binds to loopback and never contacts real devices.
