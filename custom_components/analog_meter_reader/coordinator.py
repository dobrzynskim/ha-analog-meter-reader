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

from homeassistant.components.camera import async_get_image
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    TIMEOUT_SNAPSHOT_SECONDS,
    MeterReaderApiError,
    async_ask_gemini,
    async_fetch_snapshot,
)
from .const import (
    CALIBRATION_DRIFT_ISSUE,
    CONF_API_KEY,
    CONF_CAMERA_ENTITY_ID,
    CONF_CAMERA_URL,
    CONF_CROP_BOTTOM,
    CONF_CROP_LEFT,
    CONF_CROP_RIGHT,
    CONF_CROP_TOP,
    CONF_FLIP_HORIZONTAL,
    CONF_MAX_STEP,
    CONF_PROMPT,
    CONSECUTIVE_BAD_THRESHOLD,
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
        self._entry_id = entry_id
        self._config = config
        self._session = session
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry_id}")
        self._last_good: float | None = None
        self._store_loaded = False
        self._consecutive_bad = 0

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

        camera_entity_id = self._config.get(CONF_CAMERA_ENTITY_ID)
        try:
            if camera_entity_id:
                # Encja camera zamiast surowego URL-a - HA samo wyciąga
                # klatkę z dowolnego źródła, które już obsługuje (RTSP,
                # ONVIF, Frigate, go2rtc, WebRTC...), nie tylko z prostego
                # snapshotu HTTP.
                camera_image = await async_get_image(
                    self.hass, camera_entity_id, timeout=TIMEOUT_SNAPSHOT_SECONDS
                )
                raw = camera_image.content
            else:
                raw = await async_fetch_snapshot(self._session, self._config[CONF_CAMERA_URL])
        except MeterReaderApiError as err:
            raise UpdateFailed(str(err)) from err
        except HomeAssistantError as err:
            raise UpdateFailed(f"Nie udało się pobrać klatki z encji {camera_entity_id}: {err}") from err

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
            self._register_bad_cycle()
            return result

        max_step = self._config.get(CONF_MAX_STEP, DEFAULT_MAX_STEP)
        used_value, rejected = validate_reading(value, self._last_good, max_step)

        if rejected:
            _LOGGER.warning(
                "Odczyt %.3f odrzucony (ostatni dobry: %s, max_step: %s) - zostaję przy poprzedniej wartości",
                value, self._last_good, max_step,
            )
            self._register_bad_cycle()
        else:
            self._last_good = used_value
            await self._store.async_save({"last_good": used_value})
            self._register_good_cycle()

        result["value"] = used_value
        result["raw_value"] = value
        result["rejected"] = rejected
        return result

    @property
    def _drift_issue_id(self) -> str:
        return f"{CALIBRATION_DRIFT_ISSUE}_{self._entry_id}"

    def _register_bad_cycle(self) -> None:
        """Odrzucony albo niepewny odczyt - licz kolejne pod rząd; długa seria
        zwykle znaczy, że kamera się poruszyła i ramka przestała trafiać w
        pasek cyfr, nie że to zwykły szum pojedynczego odczytu."""
        self._consecutive_bad += 1
        if self._consecutive_bad == CONSECUTIVE_BAD_THRESHOLD:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self._drift_issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="calibration_drift",
                translation_placeholders={"count": str(self._consecutive_bad)},
            )

    def _register_good_cycle(self) -> None:
        if self._consecutive_bad >= CONSECUTIVE_BAD_THRESHOLD:
            ir.async_delete_issue(self.hass, DOMAIN, self._drift_issue_id)
        self._consecutive_bad = 0

    async def async_set_manual_value(self, value: float) -> None:
        """Ręczna korekta z encji number - np. seria odrzuconych (podejrzanych)
        odczytów z tego samego powodu, albo fizyczna wymiana/zerowanie
        licznika. Nadpisuje ostatnią dobrą wartość od razu (bez czekania na
        kolejny cykl) i staje się nowym punktem odniesienia dla walidacji."""
        self._last_good = value
        await self._store.async_save({"last_good": value})
        self._register_good_cycle()
        self.async_set_updated_data({**(self.data or {}), "value": value, "rejected": False})
