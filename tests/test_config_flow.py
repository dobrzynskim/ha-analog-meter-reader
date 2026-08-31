"""Testy config_flow.py wymagające prawdziwego `hass` (FlowManager,
MockConfigEntry) - stąd pytest-homeassistant-custom-component.

Skupione na walidacji "własne/OpenAI-compatible wymaga adresu URL", bo to
jedyna nietrywialna logika dodana wraz z obsługą wielu dostawców AI - reszta
formularza to zwykłe pola vol.Schema, których błędne dodanie i tak wywali
hassfest/import."""
from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.analog_meter_reader.const import (
    AI_PROVIDER_OPENAI_COMPATIBLE,
    CONF_AI_PROVIDER,
    CONF_API_BASE_URL,
    CONF_API_KEY,
    CONF_CAMERA_URL,
    CONF_DEVICE_CLASS,
    CONF_FLIP_HORIZONTAL,
    CONF_MAX_STEP,
    CONF_NAME,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_UNIT_OF_MEASUREMENT,
    DOMAIN,
)

USER_INPUT_OPENAI_COMPATIBLE_NO_URL = {
    CONF_NAME: "Wodomierz",
    CONF_CAMERA_URL: "http://camera.local/snapshot",
    CONF_AI_PROVIDER: AI_PROVIDER_OPENAI_COMPATIBLE,
    CONF_API_KEY: "key",
    CONF_DEVICE_CLASS: "water",
    CONF_UNIT_OF_MEASUREMENT: "m3",
    CONF_FLIP_HORIZONTAL: True,
}


async def test_user_step_requires_base_url_for_openai_compatible(hass):
    """Regresja: dostawca 'własne API' bez adresu URL nie ma dokąd wysłać
    zapytania - walidacja musi to złapać, zanim cokolwiek spróbuje pobrać
    zdjęcie z kamery (dlatego ten test nie mockuje pobierania zdjęcia -
    jeśli walidacja przepuści błędny input dalej, test i tak by to wykrył
    przez brak zamockowanej sesji/kamery)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data=USER_INPUT_OPENAI_COMPATIBLE_NO_URL
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "base_url_required"}


async def test_options_flow_requires_base_url_for_openai_compatible(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_NAME: "Wodomierz",
            CONF_CAMERA_URL: "http://camera.local/snapshot",
            CONF_AI_PROVIDER: "gemini",
            CONF_API_KEY: "key",
        },
        options={},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_AI_PROVIDER: AI_PROVIDER_OPENAI_COMPATIBLE,
            CONF_API_KEY: "key",
            CONF_API_BASE_URL: "",
            CONF_SCAN_INTERVAL_MINUTES: 10,
            CONF_MAX_STEP: 2.0,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "base_url_required"}


async def test_options_flow_saves_new_provider_and_key(hass):
    """Ustawienia dostawcy/klucza/URL/modelu żyją w options (obok data) i są
    edytowalne bez ponownego dodawania integracji - to jest właśnie ta
    zmiana: użytkownik może przejść z Gemini na własne API bez usuwania
    integracji i ponownej kalibracji ramki."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_NAME: "Wodomierz",
            CONF_CAMERA_URL: "http://camera.local/snapshot",
            CONF_AI_PROVIDER: "gemini",
            CONF_API_KEY: "stary-klucz",
        },
        options={},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_AI_PROVIDER: AI_PROVIDER_OPENAI_COMPATIBLE,
            CONF_API_KEY: "nowy-klucz",
            CONF_API_BASE_URL: "http://localhost:11434/v1",
            CONF_SCAN_INTERVAL_MINUTES: 15,
            CONF_MAX_STEP: 2.0,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_AI_PROVIDER] == AI_PROVIDER_OPENAI_COMPATIBLE
    assert entry.options[CONF_API_KEY] == "nowy-klucz"
    assert entry.options[CONF_API_BASE_URL] == "http://localhost:11434/v1"
