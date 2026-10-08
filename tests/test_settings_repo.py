"""Settings repository against a fake key-value store (ARC-09, SEC-03, NFR-04)."""

from __future__ import annotations

import asyncio
import json

import pytest

from buzsak_app.settings import Settings
from buzsak_app.state.settings_repo import SETTINGS_KEY, SettingsRepository
from buzsak_app.state.token_repository import TOKEN_KEY, SecureTokenRepository


class FakeStore:
    def __init__(self, initial=None, *, fail_get=False, fail_set=False) -> None:
        self.data = dict(initial or {})
        self.fail_get, self.fail_set = fail_get, fail_set

    async def get(self, key):
        if self.fail_get:
            raise OSError("storage unavailable")
        return self.data.get(key)

    async def set(self, key, value):
        if self.fail_set:
            raise OSError("storage unavailable")
        self.data[key] = value
        return True


def _run(coro):
    return asyncio.run(coro)


def test_save_then_load_round_trips() -> None:
    store = FakeStore()
    repo = SettingsRepository(store)
    original = Settings(server_url="https://pi.test", poll_interval_s=7)
    assert _run(repo.save(original)) is True
    assert _run(repo.load()) == original


def test_saved_payload_never_contains_the_token() -> None:
    store = FakeStore()
    _run(SettingsRepository(store).save(Settings(token="s3cret")))
    assert "s3cret" not in store.data[SETTINGS_KEY]
    assert "token" not in json.loads(store.data[SETTINGS_KEY])


def test_nothing_stored_gives_defaults() -> None:
    assert _run(SettingsRepository(FakeStore()).load()) == Settings()


@pytest.mark.parametrize("stored", ["{not json", "[1, 2]", "42", 42, True, ["a"]])
def test_corrupt_stored_value_gives_defaults(stored) -> None:
    assert _run(SettingsRepository(
        FakeStore({SETTINGS_KEY: stored})).load()) == Settings()


def test_partially_invalid_stored_settings_keep_the_valid_fields() -> None:
    stored = json.dumps({"server_url": "http://pi:1", "poll_interval_s": 0})
    loaded = _run(SettingsRepository(FakeStore({SETTINGS_KEY: stored})).load())
    assert loaded.server_url == "http://pi:1"
    assert loaded.poll_interval_s == 2.0


def test_storage_read_failure_gives_defaults() -> None:
    assert _run(SettingsRepository(
        FakeStore(fail_get=True)).load()) == Settings()


def test_storage_write_failure_returns_false_without_raising() -> None:
    assert _run(SettingsRepository(
        FakeStore(fail_set=True)).save(Settings())) is False


class HungStore:
    """Never answers, like a Flet service whose client side is not listening (seen on desktop)."""

    async def get(self, key):
        await asyncio.sleep(3600)

    async def set(self, key, value):
        await asyncio.sleep(3600)


def test_a_store_that_never_answers_cannot_block_load_or_save() -> None:
    repo = SettingsRepository(HungStore(), timeout_s=0.05)
    assert _run(repo.load()) == Settings()
    assert _run(repo.save(Settings())) is False


class FakeSecureStore:
    def __init__(self, *, fail=False) -> None:
        self.data = {}
        self.fail = fail

    async def get(self, key):
        if self.fail:
            raise OSError("secret value must not appear in logs")
        return self.data.get(key)

    async def set(self, key, value):
        if self.fail:
            raise OSError("secret value must not appear in logs")
        self.data[key] = value

    async def remove(self, key):
        if self.fail:
            raise OSError("secret value must not appear in logs")
        self.data.pop(key, None)


def test_secure_token_is_saved_loaded_and_removed() -> None:
    store = FakeSecureStore()
    repo = SecureTokenRepository(store)

    assert _run(repo.save(" operator-token ")) is True
    assert store.data == {TOKEN_KEY: "operator-token"}
    assert _run(repo.load()) == "operator-token"
    assert _run(repo.clear()) is True
    assert _run(repo.load()) is None


def test_secure_storage_failures_are_bounded_and_do_not_log_secret_values(caplog) -> None:
    repo = SecureTokenRepository(FakeSecureStore(fail=True), timeout_s=0.05)

    assert _run(repo.load()) is None
    assert _run(repo.save("operator-token")) is False
    assert _run(repo.clear()) is False
    assert "secret value" not in caplog.text
    assert "operator-token" not in caplog.text
