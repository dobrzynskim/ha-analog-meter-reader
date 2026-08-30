"""Integracja Analog Meter Reader dla Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES, DOMAIN
from .coordinator import MeterReaderCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.CAMERA,
    Platform.NUMBER,
    Platform.BUTTON,
]


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
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Przeładuj integrację po zmianie opcji (interwał, max_step, prompt)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Usuwa wpis konfiguracji."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
