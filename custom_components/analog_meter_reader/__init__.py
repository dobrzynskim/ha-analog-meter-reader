"""Integracja Analog Meter Reader dla Home Assistant."""
from __future__ import annotations

import logging
from pathlib import Path

import voluptuous as vol

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_CROP_BOTTOM,
    CONF_CROP_LEFT,
    CONF_CROP_RIGHT,
    CONF_CROP_TOP,
    CONF_SCAN_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
)
from .coordinator import MeterReaderCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.CAMERA,
    Platform.NUMBER,
    Platform.BUTTON,
    Platform.TEXT,
]

SERVICE_SET_CROP_BOX = "set_crop_box"
CARD_JS_FILENAME = "analog-meter-reader-crop-card.js"
STATIC_URL_PATH = f"/{DOMAIN}_static"

# config_flow-only integracja (brak konfiguracji przez YAML) - wymagane przez
# hassfest, skoro definiujemy async_setup (rejestracja karty/serwisu poniżej).
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SET_CROP_BOX_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Required(CONF_CROP_LEFT): vol.Coerce(int),
        vol.Required(CONF_CROP_TOP): vol.Coerce(int),
        vol.Required(CONF_CROP_RIGHT): vol.Coerce(int),
        vol.Required(CONF_CROP_BOTTOM): vol.Coerce(int),
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Rejestruje towarzyszącą kartę Lovelace (wizualna kalibracja ramki
    przez przeciąganie prostokąta na zdjęciu, zamiast wpisywania pikseli
    odczytanych z siatki) i serwis set_crop_box, którego ta karta używa.

    Raz na cały proces HA (nie per wpis konfiguracji) - karta i serwis są
    wspólne dla wszystkich skonfigurowanych liczników tej integracji."""
    www_dir = Path(__file__).parent / "www"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL_PATH, str(www_dir), cache_headers=False)]
    )
    add_extra_js_url(hass, f"{STATIC_URL_PATH}/{CARD_JS_FILENAME}")

    async def _async_handle_set_crop_box(call: ServiceCall) -> None:
        box = (
            call.data[CONF_CROP_LEFT],
            call.data[CONF_CROP_TOP],
            call.data[CONF_CROP_RIGHT],
            call.data[CONF_CROP_BOTTOM],
        )
        # Pełna walidacja względem rozmiaru zdjęcia (InvalidCropBox) dzieje
        # się i tak przy najbliższym cyklu w coordinator._async_update_data -
        # tu tylko odsiewamy oczywiście bez sensu wpisane wartości (karta z
        # założenia nie powinna nigdy wysłać czegoś takiego, to zabezpieczenie
        # na wypadek ręcznego wywołania serwisu z Narzędzi deweloperskich).
        if box[2] <= box[0] or box[3] <= box[1] or min(box) < 0:
            raise ServiceValidationError(f"Nieprawidłowa ramka przycięcia: {box}")

        registry = er.async_get(hass)
        for entity_id in call.data[ATTR_ENTITY_ID]:
            entity_entry = registry.async_get(entity_id)
            entry = (
                hass.config_entries.async_get_entry(entity_entry.config_entry_id)
                if entity_entry and entity_entry.config_entry_id
                else None
            )
            if entry is None or entry.domain != DOMAIN:
                raise ServiceValidationError(
                    f"{entity_id} nie należy do integracji Analog Meter Reader."
                )

            hass.config_entries.async_update_entry(
                entry,
                data={
                    **entry.data,
                    CONF_CROP_LEFT: box[0],
                    CONF_CROP_TOP: box[1],
                    CONF_CROP_RIGHT: box[2],
                    CONF_CROP_BOTTOM: box[3],
                },
            )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_CROP_BOX):
        hass.services.async_register(
            DOMAIN, SERVICE_SET_CROP_BOX, _async_handle_set_crop_box, schema=SET_CROP_BOX_SCHEMA
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Konfiguruje integrację na podstawie wpisu utworzonego przez config_flow."""
    session = async_get_clientsession(hass)
    # Options (interwał, max_step, prompt) nadpisują wartości domyślne z
    # config_flow - łączymy w jeden słownik, żeby coordinator nie musiał znać
    # różnicy między data (stałe przy tworzeniu wpisu) a options (edytowalne
    # później przez Options Flow).
    config = {**entry.data, **entry.options}
    interval_minutes = entry.options.get(CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES)

    coordinator = MeterReaderCoordinator(hass, entry.entry_id, config, session, interval_minutes)
    # Nie async_config_entry_first_refresh() - to byłby żywy cykl kamera+AI
    # (sieć + płatne zapytanie do Gemini) blokujący setup encji, co przy
    # każdym starcie/reloadzie integracji wyglądało jak zawieszenie. Zamiast
    # tego encje dostają od razu ostatnią zapisaną wartość, a prawdziwy
    # odczyt robi pierwszy zaplanowany cykl w tle, już po starcie.
    await coordinator.async_prime_from_storage()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    entry.async_create_background_task(
        hass, coordinator.async_refresh(), f"{DOMAIN}_{entry.entry_id}_first_refresh"
    )
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Zastosuj nowe opcje (interwał, max_step, prompt, crop...) na żywo.

    Bez pełnego hass.config_entries.async_reload() - ten robił unload+setup
    wszystkich encji przy KAŻDEJ zmianie opcji, co razem z blokującym
    pierwszym odczytem (kamera+AI) wyglądało jak zawieszona integracja."""
    coordinator: MeterReaderCoordinator = hass.data[DOMAIN][entry.entry_id]
    config = {**entry.data, **entry.options}
    interval_minutes = entry.options.get(CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES)
    coordinator.async_update_config(config, interval_minutes)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Usuwa wpis konfiguracji."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
