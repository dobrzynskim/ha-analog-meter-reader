"""Diagnostyka dla Analog Meter Reader (pobierana z UI integracji)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_API_BASE_URL, CONF_API_KEY, CONF_CAMERA_URL, DOMAIN

# Klucz API i adresy (kamery, oraz API self-hosted modeli - mogłyby ujawnić
# IP/topologię sieci domowej) trafiają często do publicznych zgłoszeń błędów
# - maskujemy wszystkie trzy.
TO_REDACT = {CONF_API_KEY, CONF_CAMERA_URL, CONF_API_BASE_URL}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    data = dict(coordinator.data or {})
    data.pop("image", None)  # binarne dane obrazu nie mają czego wnosić do diagnostyki tekstowej

    return {
        "entry": async_redact_data({**entry.data, "options": dict(entry.options)}, TO_REDACT),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "data": data,
        },
    }
