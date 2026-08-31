"""Testy MeterReaderCoordinator wymagające prawdziwego obiektu `hass`
(Store, DataUpdateCoordinator) - stąd pytest-homeassistant-custom-component
zamiast lekkich fake'ów jak w test_api.py/test_validation.py.

Skupione na dwóch rzeczach naprawionych w tej integracji, które łatwo cicho
zepsuć przy kolejnej zmianie: (1) start/reload nie robi już blokującego,
żywego cyklu kamera+AI - tylko wczytuje ostatnią wartość ze Store; (2) zmiana
opcji podmienia config coordinatora na żywo i przelicza interwał tylko gdy
faktycznie się zmienił, zamiast zawsze przeplanowywać cykl."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.analog_meter_reader.api import MeterReaderApiError
from custom_components.analog_meter_reader.const import (
    AI_RETRY_ATTEMPTS,
    AI_RETRY_BACKOFF_SECONDS,
    CONF_API_KEY,
    CONF_CAMERA_URL,
    CONF_CROP_BOTTOM,
    CONF_CROP_LEFT,
    CONF_CROP_RIGHT,
    CONF_CROP_TOP,
    DOMAIN,
)
from custom_components.analog_meter_reader.coordinator import MeterReaderCoordinator

BASE_CONFIG = {
    CONF_API_KEY: "key",
    CONF_CAMERA_URL: "http://camera.local/snapshot",
    CONF_CROP_LEFT: 0,
    CONF_CROP_TOP: 0,
    CONF_CROP_RIGHT: 100,
    CONF_CROP_BOTTOM: 100,
}


def make_coordinator(hass, entry_id="test-entry", config=None, interval_minutes=10):
    return MeterReaderCoordinator(
        hass,
        entry_id,
        dict(config or BASE_CONFIG),
        session=AsyncMock(),
        interval_minutes=interval_minutes,
    )


async def test_async_prime_from_storage_uses_last_good_without_live_cycle(hass, hass_storage):
    """Regresja: start/reload kiedyś czekał na cały cykl kamera+AI zanim
    encje w ogóle się pojawiły - to właśnie wyglądało jak zawieszenie."""
    entry_id = "test-entry"
    hass_storage[f"{DOMAIN}_{entry_id}"] = {
        "version": 1,
        "minor_version": 1,
        "key": f"{DOMAIN}_{entry_id}",
        "data": {"last_good": 525.075},
    }
    coordinator = make_coordinator(hass, entry_id=entry_id)

    await coordinator.async_prime_from_storage()

    assert coordinator.data["value"] == 525.075
    assert coordinator.last_update_success is True


async def test_async_prime_from_storage_empty_store_gives_none_not_crash(hass, hass_storage):
    coordinator = make_coordinator(hass, entry_id="fresh-entry")

    await coordinator.async_prime_from_storage()

    assert coordinator.data["value"] is None


async def test_async_update_config_replaces_config_dict(hass, hass_storage):
    coordinator = make_coordinator(hass)
    new_config = {**BASE_CONFIG, CONF_API_KEY: "nowy-klucz"}

    coordinator.async_update_config(new_config, interval_minutes=10)

    assert coordinator._config[CONF_API_KEY] == "nowy-klucz"


async def test_async_update_config_keeps_interval_when_unchanged(hass, hass_storage):
    """Regresja: kiedyś KAŻDA zmiana opcji (nawet samego promptu) robiła
    hass.config_entries.async_reload() - unload+setup wszystkich encji.
    async_update_config ma być tanie, gdy tylko interwał się nie zmienia."""
    coordinator = make_coordinator(hass, interval_minutes=10)
    original_interval = coordinator.update_interval

    coordinator.async_update_config(dict(BASE_CONFIG), interval_minutes=10)

    assert coordinator.update_interval == original_interval == timedelta(minutes=10)


async def test_async_update_config_reschedules_when_interval_changes(hass, hass_storage):
    coordinator = make_coordinator(hass, interval_minutes=10)

    coordinator.async_update_config(dict(BASE_CONFIG), interval_minutes=30)

    assert coordinator.update_interval == timedelta(minutes=30)
    # async_update_config przeplanowuje timer bezpośrednio (nie przez
    # listenera encji, którego tu nie ma) - trzeba go posprzątać ręcznie,
    # tak jak realny unload encji zrobiłby to za nas.
    await coordinator.async_shutdown()


async def test_async_set_manual_value_updates_last_good_and_data(hass, hass_storage):
    coordinator = make_coordinator(hass)

    await coordinator.async_set_manual_value(123.456)

    assert coordinator._last_good == 123.456
    assert coordinator.data["value"] == 123.456
    assert coordinator.data["rejected"] is False
    assert hass_storage[f"{DOMAIN}_test-entry"]["data"]["last_good"] == 123.456


async def test_async_set_manual_value_resets_consecutive_bad_counter(hass, hass_storage):
    coordinator = make_coordinator(hass)
    coordinator._consecutive_bad = 4

    await coordinator.async_set_manual_value(123.456)

    assert coordinator.data["consecutive_bad"] == 0


# --- _async_ask_ai_with_retry (patrz api.MeterReaderApiError.retryable) --


async def test_ask_ai_retry_succeeds_after_one_transient_error(hass, hass_storage):
    coordinator = make_coordinator(hass)
    error = MeterReaderApiError("chwilowy błąd 503", retryable=True)
    mock_ask_ai = AsyncMock(side_effect=[error, "515.234"])

    with (
        patch("custom_components.analog_meter_reader.coordinator.async_ask_ai", mock_ask_ai),
        patch("custom_components.analog_meter_reader.coordinator.asyncio.sleep", AsyncMock()) as mock_sleep,
    ):
        result = await coordinator._async_ask_ai_with_retry(
            "gemini", "key", "model", "prompt", b"jpeg", None
        )

    assert result == "515.234"
    assert mock_ask_ai.await_count == 2
    mock_sleep.assert_awaited_once_with(AI_RETRY_BACKOFF_SECONDS)


async def test_ask_ai_retry_gives_up_after_max_attempts(hass, hass_storage):
    coordinator = make_coordinator(hass)
    error = MeterReaderApiError("wciąż 503", retryable=True)
    mock_ask_ai = AsyncMock(side_effect=error)

    with (
        patch("custom_components.analog_meter_reader.coordinator.async_ask_ai", mock_ask_ai),
        patch("custom_components.analog_meter_reader.coordinator.asyncio.sleep", AsyncMock()),
    ):
        with pytest.raises(MeterReaderApiError):
            await coordinator._async_ask_ai_with_retry("gemini", "key", "model", "prompt", b"jpeg", None)

    assert mock_ask_ai.await_count == AI_RETRY_ATTEMPTS


async def test_ask_ai_retry_does_not_retry_non_retryable_error(hass, hass_storage):
    """Regresja: zły klucz API (retryable=False) nie może czekać
    AI_RETRY_BACKOFF_SECONDS na nic - to i tak się nie zmieni bez ingerencji
    użytkownika, więc ma lecieć dalej natychmiast, przy pierwszej próbie."""
    coordinator = make_coordinator(hass)
    error = MeterReaderApiError("zły klucz", retryable=False)
    mock_ask_ai = AsyncMock(side_effect=error)

    with (
        patch("custom_components.analog_meter_reader.coordinator.async_ask_ai", mock_ask_ai),
        patch("custom_components.analog_meter_reader.coordinator.asyncio.sleep", AsyncMock()) as mock_sleep,
    ):
        with pytest.raises(MeterReaderApiError):
            await coordinator._async_ask_ai_with_retry("gemini", "key", "model", "prompt", b"jpeg", None)

    assert mock_ask_ai.await_count == 1
    mock_sleep.assert_not_awaited()
