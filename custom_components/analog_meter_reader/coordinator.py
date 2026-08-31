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
from homeassistant.util import dt as dt_util

from .api import (
    TIMEOUT_SNAPSHOT_SECONDS,
    MeterReaderApiError,
    async_ask_ai,
    async_fetch_snapshot,
)
from .const import (
    CALIBRATION_DRIFT_ISSUE,
    CONF_AI_MODEL,
    CONF_AI_PROVIDER,
    CONF_API_BASE_URL,
    CONF_API_KEY,
    CONF_CAMERA_ENTITY_ID,
    CONF_CAMERA_URL,
    CONF_CROP_BOTTOM,
    CONF_CROP_LEFT,
    CONF_CROP_RIGHT,
    CONF_CROP_TOP,
    CONF_FLIP_HORIZONTAL,
    CONF_GEMINI_MODEL,
    CONF_MAX_STEP,
    CONF_PROMPT,
    CONF_QUIET_HOURS_END,
    CONF_QUIET_HOURS_START,
    CONSECUTIVE_BAD_THRESHOLD,
    CROP_UPSCALE_FACTOR,
    DEFAULT_AI_PROVIDER,
    DEFAULT_FLIP_HORIZONTAL,
    DEFAULT_MAX_STEP,
    DEFAULT_MODEL_BY_PROVIDER,
    DEFAULT_PROMPT,
    DOMAIN,
    STORAGE_VERSION,
    UNCERTAIN_MARKER,
)
from .image import crop_for_ocr, load_and_orient, to_jpeg_bytes
from .schedule import is_within_quiet_hours, parse_hhmm
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
        self._force_next = False

    async def _async_load_last_good(self) -> None:
        stored = await self._store.async_load()
        self._last_good = stored.get("last_good") if stored else None
        self._store_loaded = True

    async def async_prime_from_storage(self) -> None:
        """Ustaw dane startowe z ostatniej zapisanej wartości, bez czekania
        na żywy cykl kamera+AI (sieć + płatne zapytanie do Gemini).

        Wywoływane przy starcie/reloadzie integracji zamiast
        async_config_entry_first_refresh() - dzięki temu encje pojawiają
        się od razu z ostatnią znaną wartością, a prawdziwy odczyt robi
        najbliższy zaplanowany cykl w tle (patrz async_setup_entry)."""
        if not self._store_loaded:
            await self._async_load_last_good()
        self.async_set_updated_data({**(self.data or {}), "value": self._last_good})

    def async_update_config(self, config: dict[str, Any], interval_minutes: int) -> None:
        """Zastosuj nowe opcje (Options Flow) bez pełnego reloadu integracji.

        _async_update_data czyta wszystko z self._config na żywo (prompt,
        crop, max_step, godziny ciszy, model...), więc podmiana słownika
        wystarczy - nie trzeba tworzyć nowego coordinatora ani przechodzić
        przez unload/setup (co wcześniej wyzwalało zbędny, blokujący cykl
        kamera+AI przy każdej zmianie ustawień)."""
        self._config = config
        new_interval = timedelta(minutes=interval_minutes)
        if self.update_interval != new_interval:
            self.update_interval = new_interval
            self._schedule_refresh()

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

        force = self._force_next
        self._force_next = False

        quiet_start = parse_hhmm(self._config.get(CONF_QUIET_HOURS_START))
        quiet_end = parse_hhmm(self._config.get(CONF_QUIET_HOURS_END))
        if not force and is_within_quiet_hours(dt_util.now().time(), quiet_start, quiet_end):
            # Godziny ciszy - świadomie pomijamy pobranie zdjęcia i zapytanie
            # do AI (to płatne zapytanie), nie tylko "nic nowego nie robimy".
            # "force" (przycisk "Wymuś odczyt teraz") celowo omija to okno -
            # to cały sens przycisku.
            #
            # UWAGA: zwracamy "value": self._last_good jawnie, nie tylko
            # dict(self.data or {}) - self.data jest None przy pierwszym
            # cyklu po restarcie (zanim cokolwiek zostanie ustawione), więc
            # samo dict(None or {}) dawało pusty wynik i sensor pokazywał
            # brak wartości, mimo że self._last_good było poprawnie wczytane
            # ze Store linijkę wyżej. Złapane na żywo: po restarcie w oknie
            # ciszy odczyt "znikał", zamiast pokazać ostatnią zapisaną wartość.
            _LOGGER.debug("W oknie ciszy (%s-%s) - pomijam odczyt", quiet_start, quiet_end)
            return {**(self.data or {}), "value": self._last_good}

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
        provider = self._config.get(CONF_AI_PROVIDER, DEFAULT_AI_PROVIDER)
        # CONF_GEMINI_MODEL to legacy klucz sprzed obsługi wielu dostawców -
        # trzymamy odczyt jako fallback, żeby istniejący użytkownicy Gemini
        # nie stracili cicho swojego wybranego modelu po aktualizacji.
        model = (
            self._config.get(CONF_AI_MODEL)
            or self._config.get(CONF_GEMINI_MODEL)
            or DEFAULT_MODEL_BY_PROVIDER.get(provider, "")
        )
        base_url = self._config.get(CONF_API_BASE_URL)

        try:
            text = await async_ask_ai(
                self._session,
                provider,
                self._config[CONF_API_KEY],
                model,
                prompt,
                crop_bytes,
                base_url=base_url,
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

    async def async_force_refresh(self) -> None:
        """Wymusza odczyt teraz, ignorując godziny ciszy - w odróżnieniu od
        zwykłego async_refresh() (np. wywołanego po zmianie opcji), który
        powinien nadal respektować skonfigurowane okno ciszy."""
        self._force_next = True
        await self.async_refresh()

    async def async_set_manual_value(self, value: float) -> None:
        """Ręczna korekta z encji number - np. seria odrzuconych (podejrzanych)
        odczytów z tego samego powodu, albo fizyczna wymiana/zerowanie
        licznika. Nadpisuje ostatnią dobrą wartość od razu (bez czekania na
        kolejny cykl) i staje się nowym punktem odniesienia dla walidacji."""
        self._last_good = value
        await self._store.async_save({"last_good": value})
        self._register_good_cycle()
        self.async_set_updated_data({**(self.data or {}), "value": value, "rejected": False})
