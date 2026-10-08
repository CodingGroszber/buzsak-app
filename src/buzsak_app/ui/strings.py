"""All user-facing text, English only for 1.0 (UX-20)."""

from __future__ import annotations

APP_TITLE = "Buzsák"

TAB_OVERVIEW = "Overview"
TAB_SYSTEM = "System"

# Party tab titles keyed by server party id; unknown parties use their server label (UX-02).
PARTY_TITLES: dict[str, str] = {
    "garden_plc": "Pump",
    "valve_controller": "Greenhouse",
    "matter": "Garage",
}


def party_title(party_id: str, server_label: str) -> str:
    return PARTY_TITLES.get(party_id) or server_label.title()


# Values and states (DATA-02): each state has its own words and icon, never colour alone.
VALUE_ON = "On"
VALUE_OFF = "Off"
VALUE_OPEN = "Open"
VALUE_CLOSED = "Closed"
VALUE_MISSING = "—"
STATE_STALE = "Stale"
STATE_UNAVAILABLE = "Unavailable"
STATE_INVALID = "Invalid"
STATE_NO_DATA = "No data"
STATE_FROZEN = "Frozen"
FROZEN_CAPTION = "Automation is paused while the mode is manual"

DETAIL_OBSERVED = "Observed"
DETAIL_CHANGED = "Last changed"
DETAIL_PROBLEM = "Problem"

HEALTH_HEALTHY = "Healthy"
HEALTH_DEGRADED = "Degraded"
HEALTH_OFFLINE = "Offline"
HEALTH_UNKNOWN = "Unknown"

CONN_CONNECTING = "Connecting"
CONN_ONLINE = "Online"
CONN_OFFLINE = "Server unreachable"
CONN_UNHEALTHY = "Server problem"
CONN_UNAUTHORIZED = "Sign-in needed"
BANNER_STALE_DATA = "Showing the last data received. Values may be out of date."
STALE_SERVER_TITLE = "Server data is old"


def stale_server_note(span: str) -> str:
    return f"No new readings for {span}. The server may have stopped collecting."


FRESHNESS_NEVER = "Not updated yet"

PARTY_NOT_CONFIGURED = "Not configured"
PARTY_NO_DEVICES = "No devices"
NO_DATA_YET = "Waiting for the first data from the server"
LOADING = "Starting…"
OVERVIEW_EMPTY = "No devices reported yet"

SYSTEM_SERVER = "Server"
SYSTEM_STATUS = "Connection"
SYSTEM_UPDATED = "Last update"
SYSTEM_GENERATED = "Server time"
SYSTEM_ISSUES = "Tolerated data issues"
SYSTEM_ERROR = "Last error"
SYSTEM_POLL = "Refresh every"
SYSTEM_VERSION = "App version"
SYSTEM_SAVE = "Save"
SYSTEM_SAVED = "Saved"
SYSTEM_SIGN_OUT = "Sign out"
SYSTEM_SIGNED_OUT = "Signed out; saved token removed."
SYSTEM_TOKEN = "Access token"
SYSTEM_TOKEN_NOTE = "Encrypted on this device until sign-out or uninstall. Server expiry or revocation still applies."
BANNER_UNAUTHORIZED = "The server needs an access token. Enter it in System."
GREENHOUSE_CONTROL = "Garden Valve Control"
VALVES = "Valves"
MODE_MANUAL = "Manual"
MODE_AUTOMATIC = "Automatic"
MODE_AUTOMATIC_HINT = "Automation in control. Switch to Manual for valve control; changing mode closes all valves."
MODE_MANUAL_HINT = "Manual override; automation is suspended. Changing mode closes all valves."
MODE_UNKNOWN_HINT = "Mode is unavailable until fresh server data arrives"
SIMULATION_LABEL = "SIMULATED"
LIVE_SERVER_LABEL = "LIVE SERVER"
COMMAND_SUBMITTING = "⏳ Sending command"
COMMAND_REJECTED = "❌ Command rejected"
COMMAND_RETRY_SAME_INTENT = "Tap again to safely check or retry this same request."
COMMAND_STATUS_UNAVAILABLE = "Command status unavailable; its outcome may be uncertain."
COMMAND_CHECK_STATUS = "Check status"
COMMAND_RETRY = "Retry same request"
COMMAND_UNCERTAIN_LOCK = "Command outcome is uncertain. Further controls are locked until the server reconciles it."
CONTROL_DEVICE_UNAVAILABLE = "Controls require a healthy device and fresh readings."
CONTROL_MODE_UNAVAILABLE = "Controls require a fresh mode reading."
CONTROL_NO_HANDLER = "Command service is unavailable."
CONTROL_SCHEMA_INVALID = "The server capability schema does not match this control."
RAIN_NOT_REPORTED = "Rain automation is not reported by the server."
AUTOMATION = "AUTOMATION"
SENSORS = "SENSORS"
MIST_AUTOMATION = "Mist automation"
RAIN_AUTOMATION = "Rain schedule"
MIST_TARGET = "Target humidity"
MIST_DUTY = "Duty cycle"
MIST_VALVE = "Mist valve"
MIST_PROGRESS = "Mist cycle progress"
AUTOMATION_SENSOR = "Humidity sensor valid"
TIME_SYNC = "Clock synchronized"
SENSOR_VALID = "Valid"
SENSOR_INVALID = "Invalid"
TIME_SYNCHRONIZED = "Synchronized"
TIME_UNSYNCHRONIZED = "Not synchronized"
RAIN_START = "Daily start"
RAIN_DURATION = "Run duration"
RAIN_VALVE = "Rain valve"
RAIN_LAST_RUN = "Last run"
RAIN_NO_PREVIOUS_RUN = "No previous run"
SENSOR_A = "Sensor A"
SENSOR_B = "Sensor B"
SENSOR_TEMPERATURE = "Temperature"
SENSOR_HUMIDITY = "Humidity"
SENSOR_OK = "Sensor OK"
SENSOR_FAULT = "Sensor fault"
SENSOR_AGE_MISSING = "Frame age unavailable"
SENSOR_NO_GOOD_FRAME = "No good frame recorded"
DEVICE_FIRMWARE = "Firmware"
DEVICE_IP = "Controller IP"
GARAGE_RIGHT = "Garage Right"
GARAGE_LEFT = "Garage Left"
GARAGE_TRIGGER = "Trigger"
GARAGE_TRIGGER_TOOLTIP = "Send one brief garage-door trigger"
GARAGE_RELAY_ACTIVE = "Relay on"
GARAGE_RELAY_INACTIVE = "Relay off"
GARAGE_UNREACHABLE = "Unavailable"
PULSE_DISABLED = "Pulse unavailable"
PULSE_PENDING = "⏳ Pulse pending"
PULSE_UNCERTAIN = "⚠️ Pulse outcome uncertain"
PULSE_UNKNOWN = "⚠️ Pulse status unknown"
PULSE_CANCELLED = "⏹ Pulse cancelled"
PULSE_BUTTON_TOOLTIP = "Send one server-controlled 0.5-second pulse"
GARAGE_POSITION_NOTE = "Door position is not reported"


def garage_label(device_id: str) -> str:
    return {
        "sonoff-1": GARAGE_RIGHT,
        "sonoff-2": GARAGE_LEFT,
    }.get(device_id, device_id)


def pulse_sent(relay_state: str) -> str:
    return f"✅ Pulse sent · {relay_state}"


def pulse_error(relay_state: str) -> str:
    return f"❌ Pulse error · {relay_state}"


def pulse_expired(relay_state: str) -> str:
    return f"⌛ Pulse expired · {relay_state}"


_PULSE_STATUS_LABELS = {
    "pending": "⏳ Pulse pending",
    "dispatching": "⚙️ Sending pulse",
    "sent": "📡 Pulse sent",
    "succeeded": "✅ Pulse completed",
    "failed": "❌ Pulse failed",
    "expired": "⌛ Pulse expired",
    "uncertain": "⚠️ Pulse outcome uncertain",
}


def pulse_status(status: str, reason: str | None = None) -> str:
    label = _PULSE_STATUS_LABELS.get(
        status, f"Pulse: {status.replace('_', ' ')}")
    detail = reason.replace("\n", " ").strip()[:120] if reason else ""
    return label + (f" · {detail}" if detail else "")


def mist_run_hint(minutes: float) -> str:
    value = f"{minutes:.1f}" if 0 < minutes < 1 else str(round(minutes))
    return f"{value}m"


def rain_run_hint(start: str, duration_minutes: int) -> str:
    return f"{start} · {duration_minutes}m"


def mist_progress(elapsed_s: int, period_s: int, percent: int) -> str:
    return f"{elapsed_s} s of {period_s} s · {percent}%"


def sensor_age(seconds: int) -> str:
    return f"Last good frame {seconds} s ago"


def sensor_last_error(error: str) -> str:
    return f"Last sensor error: {error}"


def relay_tooltip(label: str, state: bool | None) -> str:
    if state is None:
        return f"{label}: state unavailable"
    return f"Set {label} to {'closed' if state else 'open'}"


_COMMAND_REASON_TEXT = {
    "device_interlock": "device safety interlock",
    "device_rejected": "device rejected the action",
    "transport_outcome_ambiguous": "transport outcome is unknown",
    "ambiguous_device_response": "device response was ambiguous",
    "interrupted_dispatch": "server restarted during dispatch",
    "deadline_expired": "command expired before dispatch",
    "stale_revision": "device state changed before dispatch",
    "stale_telemetry": "device data was stale",
    "precondition_failed": "device precondition failed",
}

_COMMAND_STATE_LABELS = {
    "pending": "🕒 Command queued",
    "dispatching": "⚙️ Sending to controller",
    "sent": "📡 Command sent",
    "acknowledged": "📨 Accepted; waiting for telemetry",
    "confirmed": "✅ Command confirmed",
    "failed": "❌ Command failed",
    "expired": "⌛ Command expired",
    "cancelled": "⏹ Command cancelled",
    "uncertain": "⚠️ Command outcome uncertain",
}


def command_status(status: str, reason: str | None = None) -> str:
    detail = _COMMAND_REASON_TEXT.get(reason, "") if reason else ""
    label = _COMMAND_STATE_LABELS.get(
        status, f"Command: {status.replace('_', ' ')}")
    return label + (f" · {detail}" if detail else "")


ERROR_BAD_URL = "Enter an address starting with http:// or https://"
ERROR_TOKEN_REJECTED = "The server rejected this token; it was not saved."
ERROR_TOKEN_VERIFY = "Could not verify server access; the token was not saved."
ERROR_SECURE_STORAGE_UNAVAILABLE = "Could not access encrypted token storage; no changes were saved."


def mode_text(value: object) -> str:
    return str(value).capitalize()


def failures_text(count: int) -> str:
    return f"{count} failed poll" + ("" if count == 1 else "s")


def pulse_text(status: str, error: str | None) -> str:
    return f"Last pulse: {status}" + (f" ({error})" if error else "")


def updated_ago(span: str) -> str:
    return f"Updated {span} ago"


def seconds_text(seconds: float) -> str:
    return f"{seconds:g} s"


# Parameter labels and one-line captions, keyed by server parameter id (UX-10, SSOT-07).
PARAMETER_LABELS: dict[str, str] = {
    "pressure_bar": "Pressure",
    "water_level_liters": "Water level",
    "well_pump": "Well pump",
    "tank_pump": "Tank pump",
    "left_sw": "Left switch",
    "right_sw": "Right switch",
    "switch_led": "Switch LED",
    "wifi_led": "Wi-Fi LED",
    "sensor_a_temperature_c": "Sensor A temperature",
    "sensor_a_humidity_pct": "Sensor A humidity",
    "sensor_b_temperature_c": "Sensor B temperature",
    "sensor_b_humidity_pct": "Sensor B humidity",
    "mode": "Mode",
    "relay1_mist": "Mist",
    "relay2_rain": "Rain",
    "relay3_drip": "Drip",
    "relay4_light": "Light",
    "automation_target_pct": "Humidity target",
    "automation_duty": "Duty",
    "automation_period_s": "Period",
    "automation_elapsed_s": "Elapsed",
    "automation_valve_on": "Automation valve",
    "automation_sensor_valid": "Automation sensor",
    "automation_time_synced": "Time sync",
    "on_off": "Power",
}

PARAMETER_CAPTIONS: dict[str, str] = {
    "pressure_bar": "Below about 0.1 bar the sensor reads invalid",
    "water_level_liters": "Sensor may over-range; treat high readings with care",
    "mode": "Manual allows valve control",
    "automation_duty": "Share of the period the mist valve runs",
    "automation_target_pct": "Humidity the automation aims for",
}


def parameter_label(parameter_id: str) -> str:
    """Known label, or a readable fallback so unknown server parameters still render."""
    return PARAMETER_LABELS.get(parameter_id) or parameter_id.replace("_", " ").capitalize()


def parameter_caption(parameter_id: str) -> str | None:
    return PARAMETER_CAPTIONS.get(parameter_id)
