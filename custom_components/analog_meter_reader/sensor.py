"""Sensor platform dla Analog Meter Reader."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_DEVICE_CLASS,
    CONF_UNIT_OF_MEASUREMENT,
    CONSECUTIVE_BAD_THRESHOLD,
    DEFAULT_DEVICE_CLASS,
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
        [MeterReaderSensor(coordinator, entry), MeterReaderConsecutiveBadReadsSensor(coordinator, entry)]
    )


class MeterReaderSensor(CoordinatorEntity[MeterReaderCoordinator], SensorEntity):
    """Odczyt licznika skorygowany o walidację monotoniczności."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 3

    def __init__(self, coordinator: MeterReaderCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_reading"
        self._attr_device_class = entry.data.get(CONF_DEVICE_CLASS, DEFAULT_DEVICE_CLASS)
        self._attr_native_unit_of_measurement = entry.data.get(
            CONF_UNIT_OF_MEASUREMENT, DEFAULT_UNIT_OF_MEASUREMENT
        )
        self._attr_device_info = device_info(entry)

    @property
    def native_value(self) -> float | None:
        return (self.coordinator.data or {}).get("value")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        return {
            "raw_value": data.get("raw_value"),
            "raw_text": data.get("raw_text"),
            "odczyt_odrzucony": data.get("rejected", False),
        }


class MeterReaderConsecutiveBadReadsSensor(CoordinatorEntity[MeterReaderCoordinator], SensorEntity):
    """Ile kolejnych cykli pod rząd zwróciło odrzucony/niepewny odczyt.

    coordinator._register_bad_cycle() zgłasza Repair Issue dopiero po
    osiągnięciu CONSECUTIVE_BAD_THRESHOLD - ten sensor pokazuje sam licznik
    na bieżąco, więc widać rosnący trend (i można się na niego zaalarmować
    samemu) zanim Repair Issue w ogóle wystrzeli."""

    _attr_has_entity_name = True
    _attr_translation_key = "consecutive_bad_reads"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator: MeterReaderCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_consecutive_bad_reads"
        self._attr_device_info = device_info(entry)

    @property
    def native_value(self) -> int:
        return (self.coordinator.data or {}).get("consecutive_bad", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"prog_repair_issue": CONSECUTIVE_BAD_THRESHOLD}
