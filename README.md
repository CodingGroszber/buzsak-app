# Buzsák App

Android client for the Buzsák garden telemetry and command server (Raspberry Pi 3, `https://192.168.1.95`, with a bearer token). It shows every server KPI live in a tabbed UI and, in release 1.0, controls the greenhouse valves.

Single-stack Python UI built with [Flet](https://flet.dev). The server database is the single source of truth, and the app reaches it only through the server's HTTP API.

> Status: checkpoint 1. The read-only UI runs on desktop and on the Android emulator against the live server. See [backlog.md](backlog.md).

## Quick start (Windows 11)

```powershell
uv sync
pwsh scripts/doctor.ps1      # check Flutter, JDK, Android SDK, adb
pwsh scripts/dev.ps1         # desktop window with hot reload
pwsh scripts/deploy.ps1      # build, install and launch on an emulator or phone (needs Developer Mode)
uv run pytest -q             # tests
```

## Documentation

| Document | Purpose |
|---|---|
| [requirements.md](requirements.md) | Specification (the source of authority) |
| [backlog.md](backlog.md) | Work items by milestone |
| [docs/build-and-deploy.md](docs/build-and-deploy.md) | Run, build, install, sign, troubleshoot |
| [docs/adr/](docs/adr/) | Architecture decision records |
| [CHANGELOG.md](CHANGELOG.md) | User-visible changes |
| [.github/copilot-instructions.md](.github/copilot-instructions.md) | Rules for AI assistants and contributors |

## Layout

```
src/main.py            Flet entry point
src/buzsak_app/
  api/                 HTTP client (only layer doing network I/O)
  domain/              Typed models and server-semantics rules (no Flet)
  state/               Store, polling, command tracking (no Flet)
  ui/                  Flet views, theme, strings
  settings.py          Settings and defaults
scripts/               PowerShell run/build helpers
tests/                 pytest, including architecture guard tests
```

Imports point downward only: `ui` → `state` → `domain` → `api`. `tests/test_architecture.py` enforces this.
