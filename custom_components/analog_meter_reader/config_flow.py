"""Config flow dla integracji Analog Meter Reader."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MeterReaderApiError, async_fetch_snapshot
from .const import (
    CONF_API_KEY,
    CONF_CAMERA_URL,
    CONF_CROP_BOTTOM,
    CONF_CROP_LEFT,
    CONF_CROP_RIGHT,
    CONF_CROP_TOP,
    CONF_DEVICE_CLASS,
    CONF_FLIP_HORIZONTAL,
    CONF_MAX_STEP,
    CONF_NAME,
    CONF_PROMPT,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_UNIT_OF_MEASUREMENT,
    DEFAULT_DEVICE_CLASS,
    DEFAULT_FLIP_HORIZONTAL,
    DEFAULT_MAX_STEP,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DEFAULT_UNIT_OF_MEASUREMENT,
    DOMAIN,
)
from .image import crop_for_ocr, load_and_orient

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default="Wodomierz"): str,
        vol.Required(CONF_CAMERA_URL): str,
        vol.Required(CONF_API_KEY): str,
        vol.Required(CONF_DEVICE_CLASS, default=DEFAULT_DEVICE_CLASS): vol.In(["water", "gas"]),
        vol.Required(CONF_UNIT_OF_MEASUREMENT, default=DEFAULT_UNIT_OF_MEASUREMENT): str,
        vol.Required(CONF_CROP_LEFT): int,
        vol.Required(CONF_CROP_TOP): int,
        vol.Required(CONF_CROP_RIGHT): int,
        vol.Required(CONF_CROP_BOTTOM): int,
        vol.Required(CONF_FLIP_HORIZONTAL, default=DEFAULT_FLIP_HORIZONTAL): bool,
    }
)


class CannotConnect(Exception):
    """Nie udało się pobrać zdjęcia z podanego adresu kamery."""


class InvalidCrop(Exception):
    """Podana ramka przycięcia wykracza poza zdjęcie albo jest pusta."""


async def _async_validate(hass: HomeAssistant, data: dict[str, Any]) -> None:
    session = async_get_clientsession(hass)
    try:
        raw = await async_fetch_snapshot(session, data[CONF_CAMERA_URL])
    except MeterReaderApiError as err:
        raise CannotConnect from err

    def _decode_and_crop() -> None:
        image = load_and_orient(raw, flip_horizontal=data[CONF_FLIP_HORIZONTAL])
        box = (data[CONF_CROP_LEFT], data[CONF_CROP_TOP], data[CONF_CROP_RIGHT], data[CONF_CROP_BOTTOM])
        crop = crop_for_ocr(image, box, scale=1)
        if crop.width <= 0 or crop.height <= 0:
            raise InvalidCrop

    try:
        await hass.async_add_executor_job(_decode_and_crop)
    except InvalidCrop:
        raise
    except Exception as err:  # noqa: BLE001
        raise CannotConnect from err


class AnalogMeterReaderConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow integracji."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await _async_validate(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidCrop:
                errors["base"] = "invalid_crop"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Nieoczekiwany błąd podczas walidacji konfiguracji")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_input[CONF_CAMERA_URL])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return AnalogMeterReaderOptionsFlow(config_entry)


class AnalogMeterReaderOptionsFlow(config_entries.OptionsFlow):
    """Strojenie bez zmiany kodu: interwał, tolerancja skoku, własny prompt."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL_MINUTES,
                    default=options.get(CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                vol.Required(
                    CONF_MAX_STEP, default=options.get(CONF_MAX_STEP, DEFAULT_MAX_STEP)
                ): vol.All(vol.Coerce(float), vol.Range(min=0.01, max=1000)),
                vol.Optional(CONF_PROMPT, default=options.get(CONF_PROMPT, "")): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
