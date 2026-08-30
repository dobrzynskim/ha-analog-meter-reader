"""DataUpdateCoordinator dla Analog Meter Reader.

Jeden cykl: pobierz zdjęcie -> zorientuj/przytnij do ROI -> zapytaj AI ->
zwaliduj względem ostatniego dobrego odczytu -> zapisz trwale przez
homeassistant.helpers.storage.Store (zamiast osobnego pliku na dysku i
helpera input_number, jak w poprzednim rozwiązaniu opartym o cron+MQTT+YAML).
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MeterReaderApiError, async_ask_gemini, async_fetch_snapshot
from .const import (
    CONF_API_KEY,
    CONF_CAMERA_URL,
    CONF_CROP_BOTTOM,
    CONF_CROP_LEFT,
    CONF_CROP_RIGHT,
    CONF_CROP_TOP,
    CONF_FLIP_HORIZONTAL,
    CONF_MAX_STEP,
    CONF_PROMPT,
    CROP_UPSCALE_FACTOR,
    DEFAULT_FLIP_HORIZONTAL,
    DEFAULT_MAX_STEP,
    DEFAULT_PROMPT,
    DOMAIN,
    GEMINI_MODEL,
    STORAGE_VERSION,
    UNCERTAIN_MARKER,
)
from .image import crop_for_ocr, load_and_orient, to_jpeg_bytes
from .validation import parse_ai_response, validate_reading

_LOGGER = logging.getLogger(__name__)


class MeterReaderCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Odpytuje kamerę i AI co update_interval, trzyma ostatni zaakceptowany odczyt."""

    def __init__(
        self, hass: HomeAssistant, entry_id: str, config: dict[str, Any], session: aiohttp.ClientSession, interval_minutes: int
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=interval_minutes),
        )
        self._config = config
        self._session = session
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry_id}")
        self._last_good: float | None = None
        self._store_loaded = False

    async def _async_load_last_good(self) -> None:
        stored = await self._store.async_load()
        self._last_good = stored.get("last_good") if stored else None
        self._store_loaded = True

    @property
    def crop_box(self) -> tuple[int, int, int, int]:
        return (
            self._config[CONF_CROP_LEFT],
            self._config[CONF_CROP_TOP],
            self._config[CONF_CROP_RIGHT],
            self._config[CONF_CROP_BOTTOM],
        )

    async def _async_update_data(self) -> dict[str, Any]:
        if not self._store_loaded:
            await self._async_load_last_good()

        try:
            raw = await async_fetch_snapshot(self._session, self._config[CONF_CAMERA_URL])
        except MeterReaderApiError as err:
            raise UpdateFailed(str(err)) from err

        flip = self._config.get(CONF_FLIP_HORIZONTAL, DEFAULT_FLIP_HORIZONTAL)
        image = await self.hass.async_add_executor_job(load_and_orient, raw, flip)
        crop = await self.hass.async_add_executor_job(crop_for_ocr, image, self.crop_box, CROP_UPSCALE_FACTOR)
        crop_bytes = await self.hass.async_add_executor_job(to_jpeg_bytes, crop)
        full_bytes = await self.hass.async_add_executor_job(to_jpeg_bytes, image)

        prompt = self._config.get(CONF_PROMPT) or DEFAULT_PROMPT.format(uncertain_marker=UNCERTAIN_MARKER)

        try:
            text = await async_ask_gemini(
                self._session, self._config[CONF_API_KEY], GEMINI_MODEL, prompt, crop_bytes
            )
        except MeterReaderApiError as err:
            raise UpdateFailed(str(err)) from err

        result: dict[str, Any] = {"image": full_bytes, "raw_text": text}

        value = parse_ai_response(text)
        if value is None:
            _LOGGER.debug("AI nie było pewne odczytu (odpowiedź: %r) - zachowuję poprzednią wartość", text)
            result["value"] = self._last_good
            result["rejected"] = False
            return result

        max_step = self._config.get(CONF_MAX_STEP, DEFAULT_MAX_STEP)
        used_value, rejected = validate_reading(value, self._last_good, max_step)

        if rejected:
            _LOGGER.warning(
                "Odczyt %.3f odrzucony (ostatni dobry: %s, max_step: %s) - zostaję przy poprzedniej wartości",
                value, self._last_good, max_step,
            )
        else:
            self._last_good = used_value
            await self._store.async_save({"last_good": used_value})

        result["value"] = used_value
        result["raw_value"] = value
        result["rejected"] = rejected
        return result
