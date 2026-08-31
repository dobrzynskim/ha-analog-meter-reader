"""Binarny sensor 'podejrzany odczyt' dla Analog Meter Reader."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
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
    async_add_entities(
        [MeterReaderSuspiciousReading(coordinator, entry), MeterReaderQuietHoursActive(coordinator, entry)]
    )


class MeterReaderSuspiciousReading(CoordinatorEntity[MeterReaderCoordinator], BinarySensorEntity):
    """Włączony, gdy ostatni surowy odczyt AI został odrzucony (cofnięcie się
    licznika albo nierealistyczny skok) - wygodny trigger na powiadomienie."""

    _attr_has_entity_name = True
    _attr_translation_key = "suspicious_reading"
    _attr_entity_category = None  # to sygnał do reakcji, nie diagnostyka

    def __init__(self, coordinator: MeterReaderCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_suspicious_reading"
        self._attr_device_info = device_info(entry)

    @property
    def is_on(self) -> bool:
        return bool((self.coordinator.data or {}).get("rejected", False))

    @property
    def icon(self) -> str:
        return "mdi:alert-circle-outline" if self.is_on else "mdi:check-circle-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        return {
            "surowy_odczyt_ai": data.get("raw_value"),
            "surowa_odpowiedz_ai": data.get("raw_text"),
            "aktualna_zaakceptowana_wartosc": data.get("value"),
        }


class MeterReaderQuietHoursActive(CoordinatorEntity[MeterReaderCoordinator], BinarySensorEntity):
    """Włączony, gdy integracja jest teraz w skonfigurowanym oknie ciszy.

    Bez tego brak nowego odczytu w oknie ciszy wygląda z zewnątrz identycznie
    jak zwykły brak aktywności - ta encja jasno pokazuje, że to celowe
    pominięcie cyklu (kamera+AI), nie awaria. Aktualizuje się raz na cykl
    (co scan_interval_minutes), tak jak sam odczyt - ta sama granulacja."""

    _attr_has_entity_name = True
    _attr_translation_key = "quiet_hours_active"
    _attr_entity_category = None  # widoczne wprost na karcie urządzenia, nie diagnostyka

    def __init__(self, coordinator: MeterReaderCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_quiet_hours_active"
        self._attr_device_info = device_info(entry)

    @property
    def is_on(self) -> bool:
        return bool((self.coordinator.data or {}).get("quiet_hours_active", False))

    @property
    def icon(self) -> str:
        return "mdi:volume-off" if self.is_on else "mdi:volume-high"
