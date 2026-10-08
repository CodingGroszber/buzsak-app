"""Value and timestamp parsing (DATA-01, DATA-02, DATA-06)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from buzsak_app.domain.values import ValueParseError, parse_timestamp, parse_value


@pytest.mark.parametrize(
    ("raw", "value_type", "expected"),
    [
        ("true", "bool", True),
        ("false", "bool", False),
        ("True", "bool", True),
        ("600", "int", 600),
        ("0", "int", 0),
        ("-3", "int", -3),
        ("2.8", "float", 2.8),
        ("0.0", "float", 0.0),
        ("automatic", "string", "automatic"),
    ],
)
def test_parse_value_typed(raw, value_type, expected) -> None:
    result = parse_value(raw, value_type)
    assert result == expected
    assert type(result) is type(expected)


@pytest.mark.parametrize("value_type", ["bool", "int", "float", "string", "null", None])
def test_missing_value_stays_none_never_zero_or_false(value_type) -> None:
    assert parse_value(None, value_type) is None


@pytest.mark.parametrize(
    ("raw", "value_type"),
    [
        ("yes", "bool"),
        ("1", "bool"),
        ("1.5", "int"),
        ("abc", "float"),
        ("nan", "float"),
        ("inf", "float"),
        ("x", "null"),
        ("x", "weird"),
        ("x", None),
        (5, "int"),
        (True, "bool"),
    ],
)
def test_parse_value_rejects_malformed(raw, value_type) -> None:
    with pytest.raises(ValueParseError):
        parse_value(raw, value_type)


def test_parse_timestamp_z_is_utc() -> None:
    assert parse_timestamp(
        "2026-10-05T12:00:00Z") == datetime(2026, 10, 5, 12, tzinfo=UTC)


def test_parse_timestamp_naive_is_taken_as_utc() -> None:
    assert parse_timestamp(
        "2026-10-05 12:00:00") == datetime(2026, 10, 5, 12, tzinfo=UTC)


def test_parse_timestamp_converts_offsets_to_utc() -> None:
    assert parse_timestamp(
        "2026-10-05T14:00:00+02:00") == datetime(2026, 10, 5, 12, tzinfo=UTC)


@pytest.mark.parametrize("raw", [None, "", "yesterday", 123])
def test_parse_timestamp_malformed_is_none(raw) -> None:
    assert parse_timestamp(raw) is None
