"""Button platform - ręczne wymuszenie odczytu dla Analog Meter Reader."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MeterReaderCoordinator
from .entity import device_info


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: MeterReaderCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MeterReaderForceRefresh(coordinator, entry)])


class MeterReaderForceRefresh(CoordinatorEntity[MeterReaderCoordinator], ButtonEntity):
    """Wymusza natychmiastowe pobranie zdjęcia i odczyt, bez czekania na
    kolejny zaplanowany cykl (scan_interval_minutes)."""

    _attr_has_entity_name = True
    _attr_translation_key = "force_reading"
    _attr_icon = "mdi:camera-retake"

    def __init__(self, coordinator: MeterReaderCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_force_reading"
        self._attr_device_info = device_info(entry)

    async def async_press(self) -> None:
        await self.coordinator.async_refresh()
