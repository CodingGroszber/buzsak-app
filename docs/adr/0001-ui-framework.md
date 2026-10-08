# ADR-0001: UI framework — Flet

- **Status:** Accepted (pending owner confirmation)
- **Date:** 2026-10-05
- **Covers:** ARC-01, ARC-02, ARC-03, BLD-10

## Context

The app must be Android-only, single-stack Python (ARC-01), look modern and clean (UX-10..UX-15), and build and deploy from Windows 11 with Android Studio tooling (BLD-01..BLD-07).

## Options considered

| Option | Verdict |
|---|---|
| **Flet** (Python on Flutter) | Chosen. Material 3 widgets, `flet build apk/aab` works on Windows, hot reload on desktop and on a device |
| BeeWare (Toga + Briefcase) | Rejected. Native widgets give limited control over the custom card and typography style |
| Kivy / KivyMD (Buildozer) | Rejected. Buildozer needs Linux or WSL, which breaks the Windows 11 build requirement |
| Kotlin + Jetpack Compose | Rejected. Violates the single-stack goal (ARC-01) |

## Decision

Use **Flet 1.0.3**, pinned exactly with Python **>=3.11,<3.13**, so dev runs and the bundled APK use Python 3.12.

Verified against the Flet docs on 2026-10-05:

- `flet build` bundles the highest supported Python allowed by `[project].requires-python`. Android supports 3.12, 3.13 and 3.14; 3.11 is not supported. The `<3.13` cap keeps the dev and APK interpreters identical.
- `flet build` reads dependencies from `[project].dependencies` and **ignores `uv.lock`**. Runtime dependencies are therefore pinned with `==` in `pyproject.toml`. `flet-cli` and `flet-desktop` are dev-only and are not packaged.
- Flet 1.0.3 requires Flutter 3.44.8. The Flutter on this machine is 3.41.7, so Flet downloads the matching SDK into `~/flutter/<version>` on the first build.
- Entry point is `src/main.py` (`[tool.flet.app] path = "src"`), calling `ft.run(main)`.
- Tabs use `ft.Tabs` + `ft.TabBar` + `ft.TabBarView`, which gives swipe navigation (UX-01).

## Consequences

- Python runs on a background thread inside a Flutter shell. A built app terminates immediately, so nothing may rely on `atexit` or finalizers (persist state eagerly).
- Only pure-Python or Android-wheel dependencies are allowed in `[project].dependencies`. `httpx` is pure Python.
- The packaged app is large, and the first Android launch unpacks the Python runtime. NFR-01 (cold start) must be measured on a real device (backlog B-305).
- `importlib.metadata` is not reliable in the packaged app because the project is not installed there. The version shown in the app (backlog B-303) needs a different source than package metadata.
- Native Kotlin/Java remains allowed only through a further ADR (ARC-01).
- Keystore-backed token storage uses Flet Secure Storage; see [ADR-0006](0006-keystore-token-persistence.md) (SEC-03, B-302).
