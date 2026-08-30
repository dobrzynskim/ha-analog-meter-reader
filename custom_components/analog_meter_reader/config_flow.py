"""Config flow dla integracji Analog Meter Reader.

Dwa kroki: 'user' (dane połączenia) -> 'crop' (kalibracja ramki przycięcia
z żywym podglądem zdjęcia z kamery i podglądem samego przycięcia po każdej
próbie - iteracyjnie, aż użytkownik zaznaczy "Zatwierdź").
"""
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
    CONF_CONFIRM,
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
    CROP_UPSCALE_FACTOR,
    DEFAULT_DEVICE_CLASS,
    DEFAULT_FLIP_HORIZONTAL,
    DEFAULT_MAX_STEP,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DEFAULT_UNIT_OF_MEASUREMENT,
    DOMAIN,
)
from .image import InvalidCropBox, crop_for_ocr, load_and_orient, to_data_uri

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default="Wodomierz"): str,
        vol.Required(CONF_CAMERA_URL): str,
        vol.Required(CONF_API_KEY): str,
        vol.Required(CONF_DEVICE_CLASS, default=DEFAULT_DEVICE_CLASS): vol.In(["water", "gas"]),
        vol.Required(CONF_UNIT_OF_MEASUREMENT, default=DEFAULT_UNIT_OF_MEASUREMENT): str,
        vol.Required(CONF_FLIP_HORIZONTAL, default=DEFAULT_FLIP_HORIZONTAL): bool,
    }
)


class AnalogMeterReaderConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow integracji."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._full_image = None  # PIL.Image, żywe między krokami tej samej sesji flow
        self._last_crop_preview_uri: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            try:
                raw = await async_fetch_snapshot(session, user_input[CONF_CAMERA_URL])
                image = await self.hass.async_add_executor_job(
                    load_and_orient, raw, user_input[CONF_FLIP_HORIZONTAL]
                )
            except MeterReaderApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Nieoczekiwany błąd podczas pobierania zdjęcia z kamery")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_input[CONF_CAMERA_URL])
                self._abort_if_unique_id_configured()
                self._data = dict(user_input)
                self._full_image = image
                return await self.async_step_crop()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_crop(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        width, height = self._full_image.width, self._full_image.height

        if user_input is not None:
            box = (
                user_input[CONF_CROP_LEFT],
                user_input[CONF_CROP_TOP],
                user_input[CONF_CROP_RIGHT],
                user_input[CONF_CROP_BOTTOM],
            )
            try:
                crop = await self.hass.async_add_executor_job(
                    crop_for_ocr, self._full_image, box, CROP_UPSCALE_FACTOR
                )
                self._last_crop_preview_uri = await self.hass.async_add_executor_job(to_data_uri, crop)
            except InvalidCropBox:
                errors["base"] = "invalid_crop"
            else:
                if user_input.get(CONF_CONFIRM):
                    self._data.update(
                        {
                            CONF_CROP_LEFT: box[0],
                            CONF_CROP_TOP: box[1],
                            CONF_CROP_RIGHT: box[2],
                            CONF_CROP_BOTTOM: box[3],
                        }
                    )
                    return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)

        defaults = user_input or {
            CONF_CROP_LEFT: 0,
            CONF_CROP_TOP: 0,
            CONF_CROP_RIGHT: width,
            CONF_CROP_BOTTOM: height,
        }
        schema = vol.Schema(
            {
                vol.Required(CONF_CROP_LEFT, default=defaults[CONF_CROP_LEFT]): int,
                vol.Required(CONF_CROP_TOP, default=defaults[CONF_CROP_TOP]): int,
                vol.Required(CONF_CROP_RIGHT, default=defaults[CONF_CROP_RIGHT]): int,
                vol.Required(CONF_CROP_BOTTOM, default=defaults[CONF_CROP_BOTTOM]): int,
                vol.Required(CONF_CONFIRM, default=False): bool,
            }
        )

        full_preview_uri = await self.hass.async_add_executor_job(to_data_uri, self._full_image)
        image_md = f"Pełne zdjęcie ({width}x{height}px):\n\n![Pełne zdjęcie]({full_preview_uri})"
        if self._last_crop_preview_uri:
            image_md += (
                f"\n\n**Podgląd przycięcia (powiększony {CROP_UPSCALE_FACTOR}x"
                f" - tak widzi to AI):**\n\n![Przycięcie]({self._last_crop_preview_uri})"
            )

        return self.async_show_form(
            step_id="crop",
            data_schema=schema,
            errors=errors,
            description_placeholders={"image_preview": image_md},
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
