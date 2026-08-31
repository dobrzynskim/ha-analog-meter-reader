"""Camera platform dla Analog Meter Reader - ostatnia pobrana klatka."""
from __future__ import annotations

from typing import Any

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CROP_BOTTOM, CONF_CROP_LEFT, CONF_CROP_RIGHT, CONF_CROP_TOP, DOMAIN
from .coordinator import MeterReaderCoordinator
from .entity import device_info


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: MeterReaderCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MeterReaderCamera(coordinator, entry)])


class MeterReaderCamera(CoordinatorEntity[MeterReaderCoordinator], Camera):
    """Ostatnia klatka pobrana z kamery licznika (po ewentualnym odbiciu
    lustrzanym) - do podglądu na dashboardzie, bez trzymania osobnego pliku
    na dysku jak w poprzednim rozwiązaniu opartym o cron."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_snapshot"

    def __init__(self, coordinator: MeterReaderCoordinator, entry: ConfigEntry) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        Camera.__init__(self)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_last_snapshot"
        self._attr_device_info = device_info(entry)

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        return (self.coordinator.data or {}).get("image")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # Aktualna ramka przycięcia (w pikselach TEGO zdjęcia - już po
        # ewentualnym odbiciu lustrzanym) - czyta stąd karta Lovelace
        # analog-meter-reader-crop-card, żeby zaznaczyć zapisaną ramkę na
        # starcie zamiast pustego prostokąta.
        return {
            "crop_left": self._entry.data.get(CONF_CROP_LEFT),
            "crop_top": self._entry.data.get(CONF_CROP_TOP),
            "crop_right": self._entry.data.get(CONF_CROP_RIGHT),
            "crop_bottom": self._entry.data.get(CONF_CROP_BOTTOM),
        }
