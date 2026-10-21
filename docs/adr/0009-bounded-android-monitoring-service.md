# ADR-0009: Bounded Android foreground monitoring bridge

- Status: Accepted approach (owner approval, 2026-10-09); device verification pending
- Covers: ARC-01, NTF-03, NTF-11..NTF-13

## Decision

Use a minimal local Android Flutter plugin with a Java `dataSync` foreground service. Python retains API access, numeric evaluation and session state. The bridge only owns foreground execution and Android notification delivery; it receives no credentials and performs no networking.

The owner accepted Android 15+ dataSync's six-background-hours-per-24-hours limit, reset by foreground return. Stop promptly on timeout; expose a stopped state, rather than silently restarting or misclassifying the service. As amended by ADR-0010 on 2026-10-21, active monitoring survives UI closure/task removal. No boot or sticky automatic monitoring restart is used; the boot receiver restores pending notifications only. Sign-out stops the service and preserves definitions and pending occurrences.

The ongoing monitoring notification is separate from standard alert notifications. Denied alert permission does not halt evaluation; triggers are consumed without catch-up. No Pi changes are required.

## Verification

Build the plugin into the APK through the local Flutter dependency, not manual generated-output edits. Unit tests cover Python orchestration with a fake bridge. Physical-device tests must verify permission denial/grant, browsing, task removal, auth loss, network loss and service timeout. A successful APK build is not proof of background execution on a device.

Verified 2026-10-09: Android packaging with Pyjnius 1.7.0, native plugin compilation, and merged manifest registration of dataSync, stopWithTask, non-exported service and foreground/notification/wake-lock permissions. Pyjnius 1.8.0 had no matching Android wheel in the build index. The full Python suite passes 419 tests. Device acceptance remains pending.