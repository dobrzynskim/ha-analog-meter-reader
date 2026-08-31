"""Text platform - godziny ciszy jako encje w sekcji Konfiguracja."""
from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_QUIET_HOURS_END, CONF_QUIET_HOURS_START, DOMAIN
from .coordinator import MeterReaderCoordinator
from .entity import device_info

# Pusty string (wyłączone) albo GG:MM 24h.
HHMM_PATTERN = r"^$|^([01]\d|2[0-3]):[0-5]\d$"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: MeterReaderCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            MeterReaderQuietHoursText(coordinator, entry, CONF_QUIET_HOURS_START, "quiet_hours_start"),
            MeterReaderQuietHoursText(coordinator, entry, CONF_QUIET_HOURS_END, "quiet_hours_end"),
        ]
    )


class MeterReaderQuietHoursText(CoordinatorEntity[MeterReaderCoordinator], TextEntity):
    """Początek/koniec godzin ciszy (format GG:MM, pusty = wyłączone) - ta
    sama wartość i ścieżka zapisu (entry.options) co w Options Flow, tylko
    widoczna wprost na karcie urządzenia."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = TextMode.TEXT
    _attr_native_min = 0
    _attr_native_max = 5
    _attr_pattern = HHMM_PATTERN

    def __init__(
        self, coordinator: MeterReaderCoordinator, entry: ConfigEntry, conf_key: str, translation_key: str
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._conf_key = conf_key
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{entry.entry_id}_{conf_key}"
        self._attr_device_info = device_info(entry)

    @property
    def native_value(self) -> str:
        return self._entry.options.get(self._conf_key, "")

    async def async_set_value(self, value: str) -> None:
        self.hass.config_entries.async_update_entry(
            self._entry,
            options={**self._entry.options, self._conf_key: value},
        )
