# ADR-0003: HTTPS with a pinned root CA; the token is kept in memory only

- **Status:** Accepted (owner choices, 2026-10-07)
- **Date:** 2026-10-07
- **Covers:** SEC-01, SEC-02, SEC-03, SRV-07, B-302, B-403
- **Supersedes in part:** ADR-0002 (cleartext HTTP to the server)

## Context

The server project deployed trusted HTTPS and authentication (verified 2026-10-07 by read-only requests):

- `https://192.168.1.95` is served by Caddy with `tls internal`. `http://192.168.1.95:8080` refuses connections.
- `GET /api/dashboard/state` returns `401 unauthenticated` without a bearer token. `/healthz` stays open.
- Commands need an `operator` token and are enabled only by the server's deployment config (`control.valve_enabled`).

Caddy's CA is private, so neither the public web CAs nor Android's system store vouch for it. Python on Android also does not read the Android user certificate store.

## Decisions

| Topic | Decision | Alternatives rejected |
|---|---|---|
| CA trust | Embed the server's **public** root CA in `api/trust.py` and verify against it **only**. No other server is accepted | Pasting the PEM in Settings (awkward on a phone); disabling verification (defeats HTTPS) |
| Token storage | **Memory only.** Entered on the System tab, never written to storage, never logged. It must be entered again after each app start | `flet-secure-storage` (Keystore): deferred; the owner preferred no new native dependency for now (B-302 stays open) |
| Default address | `https://192.168.1.95`. The retired default `http://192.168.1.95:8080` saved by older builds is replaced by it on load | Keeping the old value, which would leave a phone stuck on a dead address |
| Cleartext | The Android cleartext permission from ADR-0002 stays for now: it is needed for the fake server on the emulator (`http://10.0.2.2`) and for any non-HTTPS address. Remove it once the fake server also speaks TLS | Removing it now, which would break the fake-server workflow |

## Consequences

- If Caddy's CA is regenerated (for example its data directory is lost), the app shows "server certificate is not trusted". Fix: replace `SERVER_ROOT_CA_PEM` and rebuild.
- The certificate is public. It is not a secret and may live in the repo. No token, private key or password may.
- A wrong or revoked token shows "Sign-in needed" and a banner; reads recover without a restart once a valid token is entered.
- SEC-03 asks for Keystore-backed storage. Until B-302 is done, "memory only" is the documented fallback that SEC-03 allows.
