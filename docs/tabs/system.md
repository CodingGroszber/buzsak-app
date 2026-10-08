# System Tab

Covers UX-04, ARC-09, SRV-02, SEC-02..SEC-03, BLD-303, ADR-0006.

## Content

- Current server URL, connection status, snapshot freshness and generation time, tolerated issue count, latest error, polling interval and app version.
- Editable server URL and masked bearer-token field.

## Authentication and settings

- Save verifies the token by fetching and validating an authenticated `/api/dashboard/state` snapshot before storing it.
- Ordinary settings use Flet `SharedPreferences`; the bearer token is excluded and stored with platform Secure Storage backed by Android Keystore.
- Sign out removes the secure token and clears the field. Fake/live desktop launcher credentials are session-only.
- A remembered token remains on-device until sign-out, uninstall or secure-store loss. Server expiry or revocation still applies.

## Edge cases

- Invalid credentials are not saved; storage failure is reported without logging token contents.
- Missing/revoked credentials produce the sign-in-needed connection state.
- `/readyz`, per-device health table and session command log are not currently rendered here; see the backlog/specification for remaining System-tab scope.
