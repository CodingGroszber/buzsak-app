# Build and deploy

Covers BLD-01..BLD-12 and ENV-01..ENV-05 from [requirements.md](../requirements.md). Status of each option is marked **verified** (run on this machine) or **planned** (script not yet written, see [backlog.md](../backlog.md)).

## 1. Toolchain (Windows 11)

| Tool | Needed for | Verified on dev machine |
|---|---|---|
| PowerShell 7 (`pwsh`) | All scripts | 7.6.6 |
| [uv](https://docs.astral.sh/uv/) | Python, venv, locking, running everything | 0.12.5 |
| Python 3.12 | Dev runs and the APK (see ADR-0001) | uv-managed, 3.12 via `.python-version` |
| Flet 1.0.3 (pinned) | UI and `flet build` | from `uv.lock` |
| Flutter SDK | Android build | Flet 1.0.3 wants 3.44.8; Flet downloads it on the first build if the one on `PATH` (3.41.7) does not match |
| JDK 17 | Android build | Zulu 17 |
| Android Studio SDK + `adb` | Emulator, device, install, logs | SDK under `%LOCALAPPDATA%\Android\Sdk` |

Run the environment check first:

```powershell
pwsh scripts/doctor.ps1
```

It is read-only. `FAIL` blocks the build; `WARN` is informational (for example, no device attached).

First-time setup from a clean clone:

```powershell
uv sync
pwsh scripts/doctor.ps1
```

## 2. Run options

Status: **verified** = run on this machine; **written** = script exists and parses but has not been run end to end; **planned** = not written.

| ID | Option | Command | Status |
|---|---|---|---|
| BLD-01 | Desktop with hot reload | `pwsh scripts/dev.ps1` (add `-Web` for a browser) | verified |
| BLD-02 | Start an emulator and wait for boot | `pwsh scripts/emulator.ps1` (`-List`, `-Avd <name>`) | verified (`Medium_Phone_API_36.1`) |
| BLD-03 | Live run on a device or emulator | `pwsh scripts/device.ps1` (`-Serial <id>`) | written |
| BLD-04 | APK for local testing | `pwsh scripts/build-debug.ps1` | verified (128 MB APK; first run about 7 min for Gradle, later runs reuse its caches) |
| BLD-05 | Signed release APK/AAB | `scripts/build-release.ps1` | planned (B-301) |
| BLD-06 | Install and launch | `pwsh scripts/install.ps1` (`-Serial`, `-Apk`, `-NoLaunch`) | verified |
| BLD-07 | App logs | `pwsh scripts/logs.ps1` (`-Clear`, `-Dump`, `-Serial`) | runs, but shows no Python output yet (B-149) |
| BLD-08 | Fake server | `scripts/fake-server.ps1` | planned (B-141) |
| BLD-09 | Environment check | `pwsh scripts/doctor.ps1` | verified |
| – | Build + install + launch in one step | `pwsh scripts/deploy.ps1` (`-SkipBuild`, `-Logs`) | written |

Every script has a VS Code task (`Terminal > Run Task`, prefix `buzsak:`). The scripts never prompt: with more than one device attached they stop and ask for `-Serial`, so they behave the same from tasks and from a terminal.

### See the app on a device (the usual loop)

```powershell
pwsh scripts/doctor.ps1                      # everything OK except "device" is fine
pwsh scripts/emulator.ps1                    # or plug in a phone with USB debugging on
pwsh scripts/deploy.ps1 -Logs                # build, install, launch, follow the log
```

After the first build, later builds reuse the generated Flutter project in `build/flutter` and are much faster. `scripts/deploy.ps1 -SkipBuild` reinstalls the last APK. For quick UI iteration prefer `dev.ps1` on the desktop, and use the device to check touch behaviour and real Android networking.

On a physical phone: enable Developer options, turn on USB debugging, plug it in, and accept the "Allow USB debugging" prompt. `adb devices` must show it as `device`, not `unauthorized`.

The phone must be on the same network as the server (`https://192.168.1.95`). The emulator reaches the LAN through the host. Change the address on the app's System tab if needed. The app reads the server snapshot only; ESP32 webpage changes reach it through the Pi poller, and app commands reach the device through the Pi dispatcher.

The server needs a bearer token. An administrator issues one on the Pi (`manage_credentials.py issue <principal-id> viewer|operator`; see the server README, "Connecting a Client"). Type it into the System tab; it is kept in memory only, so enter it again after each app start (ADR-0003). Never paste it into chat, the repo or a URL. The server's root CA is already built into the app, so nothing needs installing on the phone.

### Simulated command testing (BLD-08, TST-06)

Never use the real server to test a control. For desktop preview, run one command; it starts the loopback simulator, fills the fake URL/token in memory, and opens Flet:

```powershell
pwsh -NoProfile -File scripts/dev.ps1 -FakeServer
```

The preview does not persist the fake token or replace normal app settings; even **Save** in the System tab is session-only in preview mode. It picks the next free local port starting at 8765, then stops the simulator when the desktop app exits. The VS Code task **buzsak: preview (fake server + desktop app)** does the same.

For Android/emulator or standalone testing, start the simulated API separately:

```powershell
pwsh -NoProfile -File scripts/fake-server.ps1
```

In the emulator's System tab, set the URL to `http://10.0.2.2:8765` and token to `fake-operator`. On a physical phone, use the development PC's LAN address instead of `10.0.2.2`. This server changes only in-memory simulated values and contains no device adapter or code that sends requests to the Pi or ESP32. It starts in Automatic mode; tap Manual to submit (the inline warning notes that all valves close). The Light relay is available in Automatic mode, matching the device firmware.

Scenarios: `-Scenario stale`, `offline`, `malformed`, `failure`, `uncertain` or `slow`. For example:

```powershell
pwsh -NoProfile -File scripts/fake-server.ps1 -Scenario uncertain
```

Return the System tab URL to `https://192.168.1.95` before reconnecting to the real server. A real command still requires a valid operator token, server-side `control.valve_enabled`, and separate owner approval.

### Desktop run notes (BLD-01)

- `dev.ps1` runs `uv run flet run -d -r src/main.py`: `-d` watches the script's directory and `-r` watches it recursively, so edits under `src/` reload the app.
- For a zero-entry local preview, run `pwsh -NoProfile -File scripts/dev.ps1 -FakeServer` or the VS Code task **buzsak: preview (fake server + desktop app)**. It starts a loopback-only fake API on the next available port from 8765, seeds its URL and `fake-operator` in memory, and stops the fake API when the desktop app exits. Neither value is saved; normal app launches still use the configured server and require its credential.
- For live desktop readings and commands, run `pwsh -NoProfile -File scripts/dev.ps1 -LiveServer` or **buzsak: live desktop (operator session)**. It retrieves the existing operator credential from `/home/neulas/.buzsak-operator-token` using the `rpi3` SSH alias and holds it only in the app process. The header shows LIVE SERVER; enabled controls can actuate real hardware. Use only with explicit owner intent. The live URL/token are not persisted, and the token is cleared when the process exits.
- The first run prints "Preparing Flet v1.0.3 for the first use" while it downloads the desktop client. This happens once, and startup can take several seconds.

### Useful Flet CLI facts (Flet 1.0.3)

- `flet run [--web] [-d] [-r] [-p PORT] [script]` (verified with `--help`).
- `flet devices [android|ios]` lists attached devices and emulators.
- `flet debug android --device-id <id>` packages the whole app and runs it on a device or emulator.
- App logs on Android: `adb logcat -s flet.python` (stdout is priority I, stderr is E). In a built app, `print()` and `logging` output also goes to `console.log` in the app's private storage.
- The Android application id is `hu.buzsak.buzsak_app` (from `[tool.flet] org` plus the project name; verified in `build/flutter/android`).

## 3. Build configuration

All in `pyproject.toml`:

- `[project].version` is the only version source (BLD-11). `flet build` uses it as the build version.
- `[project].dependencies` is what ends up in the APK, and `flet build` **ignores `uv.lock`**. Pin runtime dependencies with `==` there (BLD-10).
- `requires-python = ">=3.11,<3.13"`: `flet build` bundles the highest supported Python the range allows, so the cap keeps the APK on 3.12.
- `[tool.flet.app] path = "src"`: the entry point is `src/main.py` and assets go in `src/assets/`.
- `[tool.flet] product` and `org` set the launcher name and the application id prefix.

Build outputs go to `build/` and are git-ignored together with `*.apk`, `*.aab` and keystores (BLD-12, SEC-04).

## 4. Release signing (planned, B-301)

Without a keystore, release builds are signed with the debug key, which is fine for local testing only. Flet reads the signing material from these environment variables, so nothing is committed:

- `FLET_ANDROID_SIGNING_KEY_STORE` (path to the `.jks`)
- `FLET_ANDROID_SIGNING_KEY_STORE_PASSWORD`
- `FLET_ANDROID_SIGNING_KEY_PASSWORD`
- `FLET_ANDROID_SIGNING_KEY_ALIAS` (defaults to `upload`)

Keep the keystore outside the repository.

## 5. Troubleshooting

### `flet build` fails with "Building with plugins requires symlink support"

Flutter needs symlinks on Windows. Turn on **Developer Mode**: Settings > System > For developers > Developer Mode (or run `start ms-settings:developers`). This is a Windows setting that the scripts cannot change for you. `doctor.ps1` reports it as `FAIL`, and `build-debug.ps1` and `device.ps1` stop early with the same instructions. To check by hand, create a symlink in a normal (non-admin) terminal; if Windows says "Administrator privilege required", the mode is still off. A new terminal may be needed after enabling it.

### `flet build` ends with a `UnicodeEncodeError` about `\u221a`, but an APK was built

Flutter prints a check mark after a good build, and Flet's logger cannot encode it when output is piped on Windows. `build-debug.ps1` sets `PYTHONUTF8=1` to avoid this. If you run `flet build` yourself with piped output, set `$env:PYTHONUTF8 = '1'` first. The APK is then in `build/apk`; if the crash happened anyway it is in `build/flutter/build/app/outputs/flutter-apk/`, and `install.ps1` finds it there.

### Typing into the app's fields with `adb input` is unreliable

On the emulator, `adb shell input text` can be swallowed by Android's stylus-handwriting tutorial, and select-all-then-delete does not clear a Flutter text field. What worked: tap the field, press the End key, send many `KEYCODE_DEL` presses in one `adb shell input keyevent` call, then `input text`. For real use, type on the on-screen keyboard.

### The packaged app says "Server unreachable" but the desktop run works

Check that the phone is on the same network as the server, and that the server address on the System tab is right. Plain HTTP is allowed by `usesCleartextTraffic` (ADR-0002); if that setting was removed from `pyproject.toml`, Android 9+ blocks it. Read the app's output with `pwsh scripts/logs.ps1 -Clear`.

### The desktop app takes several seconds to show its first screen

Flet's `SharedPreferences` service does not answer on **desktop** in this setup (`Timeout waiting for invoke method listener`; cause unknown, B-116). The settings repository gives up after 3 s and falls back to the defaults, so the app still starts, but saved settings do not persist on desktop. **On Android it works**: a saved server address survived a force-stop and relaunch. The log line to look for on desktop is `could not read stored settings`.

### `uv sync` fails with "incompatible hardlinks (os error 396)"

The profile is on a cloud-filtered (OneDrive) volume, and uv's default hardlinking cannot write there. The project sets `[tool.uv] link-mode = "copy"` to avoid this. If a different uv cache problem appears (`PermissionError`), point the cache at a fresh folder for the session:

```powershell
$env:UV_CACHE_DIR = "$env:TEMP\uv-cache-fresh"
uv sync
```

### `flutter` on `PATH` is older than Flet needs

Not an error. Flet downloads the matching SDK into `~/flutter/<version>` during the first build.

### No device shows up in `adb devices`

Enable Developer options and USB debugging on the phone, accept the RSA prompt, and try another cable or port. For an emulator, start an AVD from Android Studio's Device Manager.
