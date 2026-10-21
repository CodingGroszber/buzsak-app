# ADR-0008: Settings and phone-local custom alerts

- **Status:** Accepted owner decisions (2026-10-09); implementation feasibility pending
- **Covers:** UX-01, UX-04, ARC-09, UPD-03, NTF-01..NTF-12

## Context

The owner requested custom numeric conditions and notifications while using another app. Evaluation must happen on the phone, not the Pi. This is current Git-session work; historical release milestones are not gates.

## Decisions

- Add Settings after System. Move user-editable configuration and authentication there; System becomes read-only diagnostics.
- Persist named rules locally on this phone, supporting emojis. Do not synchronize rules or require a push provider/server evaluator.
- Use numeric telemetry/constant comparisons with compatible units and operators `<`, `<=`, `>`, `>=`, `==`, `!=`. Start with flat AND or OR rules; nested groups are deferred.
- Any unknown comparison makes the whole rule UNKNOWN. UNKNOWN neither fires nor rearms.
- Start automatically after successful authentication. As amended by ADR-0010, active monitoring continues while another app is foregrounded and across UI closure/task removal, within Android limits; sign-out or rejected authentication stops it. Reopening the same process preserves the session; a fresh process starts a fresh session. Saved rules and pending occurrences survive.
- First valid TRUE triggers. Further alerts require FALSE then TRUE. Enforce per-rule 10-second cooldown; discard edges within cooldown instead of delivering them later.
- Condition edits reset truth state while preserving session cooldown. Renaming resets neither. Truth/cooldown state is not persisted across sessions.
- Deliver separate standard Android notifications for concurrent rules, including rule names. Android permissions/channel preferences remain authoritative.

## Feasibility Gate and Open Decisions

Reliable background execution is not yet verified. Research pinned Flet integration and Android foreground-service type, time limits, permissions and stop-on-task-removal behavior. Native integration needs a further ADR; no Pi changes are required.

Owner follow-up decisions: units must match exactly, with no conversions or unitless values and at least one telemetry operand. If notification permission is denied, evaluation continues and triggers are consumed without later catch-up. A minimal native bridge is permitted if required, but the particular Android service type and integration still need a further ADR and verification.

## Implementation Progress

The pure numeric evaluator, session edge/cooldown monitor, versioned local repository and Settings rule editor are implemented and unit-tested. URL/token/sign-out and polling/timeouts have moved into Settings; System is read-only. Runtime connects evaluation to a native adapter via a testable protocol. The ADR-0009 native plugin compiled successfully into an APK on 2026-10-09 with Android Pyjnius 1.7.0; the merged manifest confirms the non-exported dataSync service, stopWithTask and required permissions. Physical-device behavior is NOT yet verified. Desktop shows monitoring unavailable and does not claim to deliver Android alerts.

Verified platform constraint: Android's official foreground-service timeout documentation limits `dataSync` background execution to six hours per 24 hours for apps targeting Android 15+, with foreground return resetting the budget. The owner accepted that bounded behavior; see ADR-0009 and NTF-14. Native compilation and physical-device validation are still pending.

Sources: [Android service types](https://developer.android.com/develop/background-work/services/fgs/service-types), [Android service timeouts](https://developer.android.com/develop/background-work/services/fgs/timeout), [Flet extensions](https://flet.dev/docs/extend/user-extensions/).

## Acceptance Checks

- Reopen with a valid remembered token: rules restore and first valid TRUE alerts; sign-out works offline without deleting rules.
- In a simulated telemetry sequence: TRUE stays quiet after its first alert; FALSE then TRUE rearms; UNKNOWN does not rearm; any UNKNOWN dominates both AND and OR.
- Suppressed cooldown edges do not become delayed notifications. Condition edits retain cooldown, renames retain all state, and sessions reset runtime state.
- Two rules firing together produce separate notifications with intact emoji names.
- On a physical phone, browsing another app and task removal/closure preserve active monitoring within Android limits (ADR-0010). Verify separate acknowledgment, reboot restoration, permission denial, auth rejection, network loss and recovery without touching real hardware.