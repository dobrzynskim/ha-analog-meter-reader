"""Number platform - ręczna korekta odczytu dla Analog Meter Reader."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_UNIT_OF_MEASUREMENT,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DEFAULT_UNIT_OF_MEASUREMENT,
    DOMAIN,
)
from .coordinator import MeterReaderCoordinator
from .entity import device_info


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: MeterReaderCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            MeterReaderManualOverride(coordinator, entry),
            MeterReaderScanInterval(coordinator, entry),
        ]
    )


class MeterReaderManualOverride(CoordinatorEntity[MeterReaderCoordinator], NumberEntity):
    """Ręczne ustawienie/korekta bieżącego odczytu.

    Przydatne, gdy AI utknęło na błędnej wartości (kilka kolejnych
    podejrzanych/odrzuconych odczytów pod rząd - patrz binary_sensor) albo
    licznik został fizycznie wymieniony/wyzerowany. Wpisana wartość od razu
    zastępuje bieżący odczyt i staje się nowym punktem odniesienia dla
    walidacji (bez czekania na kolejny cykl odpytywania kamery)."""

    _attr_has_entity_name = True
    _attr_translation_key = "manual_override"
    _attr_native_min_value = 0
    _attr_native_max_value = 999999
    _attr_native_step = 0.001
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: MeterReaderCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_manual_override"
        self._attr_device_info = device_info(entry)
        self._attr_native_unit_of_measurement = entry.data.get(
            CONF_UNIT_OF_MEASUREMENT, DEFAULT_UNIT_OF_MEASUREMENT
        )

    @property
    def native_value(self) -> float | None:
        return (self.coordinator.data or {}).get("value")

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_manual_value(value)


class MeterReaderScanInterval(CoordinatorEntity[MeterReaderCoordinator], NumberEntity):
    """Częstotliwość odczytu jako encja widoczna wprost na karcie urządzenia
    (sekcja Konfiguracja), obok ręcznej korekty - zamiast tylko w osobnym
    dialogu "Konfiguruj" (Options Flow, wciąż działa równolegle).

    Zmiana aktualizuje entry.options tą samą ścieżką co Options Flow - jeden
    punkt prawdy dla tego ustawienia, oba UI tylko go edytują. Zapisany w
    entry.options, więc przetrwa restart HA (nie tylko przeładowanie)."""

    _attr_has_entity_name = True
    _attr_translation_key = "scan_interval"
    _attr_native_min_value = 1
    _attr_native_max_value = 1440
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "min"
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: MeterReaderCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_scan_interval"
        self._attr_device_info = device_info(entry)

    @property
    def native_value(self) -> float:
        return self._entry.options.get(CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES)

    async def async_set_native_value(self, value: float) -> None:
        # async_update_entry jest synchroniczne (mimo prefiksu async_) -
        # samo zaplanuje wywołanie zarejestrowanego update_listenera
        # (_async_update_listener w __init__.py), który przeładuje wpis.
        self.hass.config_entries.async_update_entry(
            self._entry,
            options={**self._entry.options, CONF_SCAN_INTERVAL_MINUTES: int(value)},
        )
