# ADR-0006: Persist the bearer token with platform secure storage

- **Status:** Accepted (owner request, 2026-10-08)
- **Covers:** SEC-02, SEC-03, ADR-0003, B-302

## Context

The app previously kept the access token in memory, requiring re-entry after every launch. Flet 1.0.3 has a compatible Secure Storage extension backed by Android Keystore. Its documented Android defaults encrypt key material with RSA-OAEP and values with AES-GCM; biometric enforcement is not enabled.

## Decision

- Use pinned `flet-secure-storage==1.0.3` for the bearer token. Never place it in ordinary `SharedPreferences`, settings JSON, logs, URLs or diagnostics.
- Load the token at startup. Save a newly entered token only after the server accepts an authenticated `/api/dashboard/state` request and the response validates.
- Retain the encrypted token until explicit **Sign out**, app uninstall or OS credential-store loss. The app does not refresh, extend or bypass server expiry/revocation.
- Sign out removes the secure entry and clears the in-memory token. Fake/live launcher credentials remain session-only.
- Disable Android app backup so an encrypted entry is not restored without its Keystore key. Do not reset secure data automatically on storage errors.

## Consequences

- The user enters a valid token once; subsequent launches reuse it. A server-rejected token remains stored until the user signs out or replaces it, and the app shows the normal authentication failure.
- Secure-storage failure prevents claiming the token was saved. The user may retry after resolving device storage issues.
- Validate persistence, app restart, and sign-out on a physical Android device before marking B-302 fully verified.
