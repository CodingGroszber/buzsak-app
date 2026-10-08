# ADR-0002: Allow cleartext HTTP on Android for the LAN server

- **Status:** Accepted (pending owner confirmation). Partly superseded by [ADR-0003](0003-https-pinned-ca-memory-token.md): the server now serves HTTPS; the cleartext permission remains for the fake server
- **Date:** 2026-10-05
- **Covers:** SEC-01, SEC-02, SRV-07

## Context

The server answers plain `http://` on the home LAN (`http://192.168.1.95:8080`) and has no TLS or authentication yet (SRV-07 is open). Android 9 and later block cleartext traffic by default, so without a manifest flag the packaged app reports "server unreachable" while the desktop run works.

SEC-01 asks for the cleartext permission to be scoped as narrowly as the toolchain allows.

## Options considered

| Option | Verdict |
|---|---|
| `usesCleartextTraffic="true"` on `<application>` | Chosen. Supported by `flet build` through `[tool.flet.android.manifest_application]` |
| A network security config limited to the server host | Not available. `flet build` documents no way to ship a custom `network_security_config.xml`, and the template cannot be extended without maintaining a fork of it |
| Run the server behind TLS now | Out of scope. That is a server change (SRV-07) and the owner has not asked for it |

## Decision

Set in `pyproject.toml`:

```toml
[tool.flet.android.manifest_application]
usesCleartextTraffic = "true"
```

Verified in the generated project: `build/flutter/android/app/src/main/AndroidManifest.xml` contains `android:usesCleartextTraffic="true"` and the `INTERNET` permission.

## Consequences

- The app can talk plain HTTP to any host, not only the Pi. The server address is user-editable, so a user could point it at an untrusted network. Accepted for a single-owner LAN tool.
- This must be revisited when the server gains TLS and authentication (SRV-07, backlog B-403): switch the server URL to `https://`, send the bearer token (already supported by the client), and remove the flag.
- The app sends no credentials today, and its only requests so far are read-only `GET`s.
