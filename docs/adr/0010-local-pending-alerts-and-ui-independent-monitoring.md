# ADR-0010: Local pending alerts and UI-independent monitoring

## Status

Accepted by the owner on 2026-10-21. Supersedes ADR-0008/0009 task-removal behavior. Native unit compilation/tests and Python lifecycle tests pass; full APK rebuild and device acceptance remain pending.

Covers UPD-03, NTF-03/04, NTF-11..NTF-16, SEC-04.

## Context

The owner wants monitoring to continue after closing/swiping away the UI, and each fired alert to remain pending until separately acknowledged. Pending alerts belong to this phone; the Pi is not their persistence owner. The owner retains the accepted Android dataSync execution budget and force-stop/OS-termination limitations.

## Decision

- Keep the existing authenticated Python poller, evaluator and session alive inside the foreground-service process after UI detach/task removal. Android's manifest uses `stopWithTask=false`; neither task removal nor Flutter-engine detach requests a service stop. The installed SeriousPython 5.0.0 implementation does not terminate its interpreter on engine detach; Flet's embedded loop remains alive until host teardown.
- Reattach recreated Android pages to the existing Runtime. Unsubscribe the replaced view and retain the same poller, rules, truth and cooldown state. Sign-out/authentication rejection, service timeout and OS process termination still stop monitoring; no automatic sticky/boot restart is introduced.
- Before posting a deliverable alert, synchronously commit its name, message, display labels, original firing time and a monotonic notification identifier to private Android preferences. No credentials or server snapshots are stored there. A separate occurrence is created for every qualifying firing, including repeated firings of the same rule.
- Use an ongoing, non-auto-cancel alert notification with an explicit immutable broadcast action named Acknowledge. Opening the app is not acknowledgment. Only successful removal of that occurrence from storage cancels its notification. No evaluation or rearming happens in the acknowledgment receiver.
- A non-exported receiver handles acknowledgment and BOOT_COMPLETED. Boot restores pending notifications, not monitoring. Engine attachment also restores pending notifications. Records need no server synchronization or API changes. Sign-out, rule deletion/recovery and service shutdown do not clear them.
- Denied notification permission still consumes triggers without saving a deferred occurrence (NTF-13). Android notification settings remain authoritative.

## Consequences

Pending occurrences survive process closure and phone reboot; clearing app data/uninstall removes them. Unacknowledged records accumulate until the user acknowledges them; no automatic age/count eviction silently acknowledges an alert.

Android 14+ may allow users/system UI to dismiss even ongoing notifications. This does not erase the pending record; app relaunch or reboot reposts it when permitted. This is durable local persistence, not a promise that a notification can never be hidden by Android. Force-stop can suppress execution and boot delivery until the user launches the app again.

Android 15+ still limits dataSync background execution to six hours per 24 hours, reset by foreground return. Monitoring is not guaranteed after OS termination, Force Stop, timeout or connectivity loss. Already-pending alerts are independent of those monitoring limits.

## Verification

Robolectric checks separate IDs (including identical names), persistence/restore, ongoing/non-auto-cancel flags, selective acknowledgment, boot restoration, identifier non-reuse and unrelated broadcasts. Python tests cover UI-detach polling and reattachment without duplicate polling or truth reset.

Physical-device acceptance using only the fake API remains required: trigger simultaneous alerts, swipe away the app, change synthetic telemetry and observe a new firing; reopen without duplicate firing; acknowledge one without clearing another; reboot and verify only pending occurrences return. Also check denied permission, sign-out, timeout and OS dismissal. A successful compile/test run is not evidence of device background reliability.