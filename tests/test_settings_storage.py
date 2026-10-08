"""Settings storage round-trip (ARC-09, SEC-03)."""

from __future__ import annotations

import pytest

from buzsak_app.settings import DEFAULT_SERVER_URL, Settings


def test_round_trip() -> None:
    original = Settings(server_url="https://pi.test:8443",
                        poll_interval_s=5, request_timeout_s=3, command_timeout_s=15)
    assert Settings.from_storage(original.to_storage()) == original


def test_token_is_never_persisted() -> None:
    stored = Settings(token="s3cret").to_storage()
    assert "token" not in stored
    assert "s3cret" not in repr(stored)


def test_empty_storage_gives_defaults() -> None:
    assert Settings.from_storage({}) == Settings()


@pytest.mark.parametrize(
    ("raw", "expected_field", "expected_value"),
    [
        ({"poll_interval_s": 0.1}, "poll_interval_s", 2.0),
        ({"poll_interval_s": 999}, "poll_interval_s", 2.0),
        ({"poll_interval_s": "fast"}, "poll_interval_s", 2.0),
        ({"poll_interval_s": True}, "poll_interval_s", 2.0),
        ({"request_timeout_s": -1}, "request_timeout_s", 5.0),
        ({"command_timeout_s": 0}, "command_timeout_s", 10.0),
        ({"server_url": "ftp://x"}, "server_url", DEFAULT_SERVER_URL),
        ({"server_url": 5}, "server_url", DEFAULT_SERVER_URL),
        ({"server_url": None}, "server_url", DEFAULT_SERVER_URL),
    ],
)
def test_invalid_field_falls_back_to_its_default_only(raw, expected_field, expected_value) -> None:
    assert getattr(Settings.from_storage(
        raw), expected_field) == expected_value


def test_one_bad_field_does_not_discard_the_good_ones() -> None:
    result = Settings.from_storage(
        {"server_url": "http://pi:1", "poll_interval_s": 0, "request_timeout_s": 7})
    assert result.server_url == "http://pi:1"
    assert result.poll_interval_s == 2.0
    assert result.request_timeout_s == 7


def test_unknown_stored_keys_are_ignored() -> None:
    assert Settings.from_storage({"future": 1, "token": "x"}) == Settings()


@pytest.mark.parametrize("retired", [
    "http://192.168.1.95:8080",
    "http://192.168.1.95:8080/",
    "http://127.0.0.1:8765",
])
def test_the_retired_plain_http_address_is_replaced_by_the_default(retired) -> None:
    assert Settings.from_storage(
        {"server_url": retired}).server_url == DEFAULT_SERVER_URL


def test_a_user_chosen_address_is_kept() -> None:
    assert Settings.from_storage(
        {"server_url": "http://10.0.2.2:8080"}).server_url == "http://10.0.2.2:8080"
