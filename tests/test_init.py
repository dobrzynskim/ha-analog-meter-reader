"""Testy serwisu set_crop_box (__init__.py) - encja karty Lovelace
analog-meter-reader-crop-card go używa, ale serwis też można wywołać
ręcznie, więc testowany niezależnie od karty.

Celowo NIE robi pełnego hass.config_entries.async_setup(entry_id) (który
odpaliłby prawdziwy cykl kamera+AI w tle, patrz entry.async_create_
background_task w __init__.py) - handler serwisu i tak dotyka tylko
entity_registry + entry.data, więc wystarczy zarejestrować encję ręcznie."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.analog_meter_reader import async_setup as amr_async_setup
from custom_components.analog_meter_reader.const import (
    CONF_CROP_BOTTOM,
    CONF_CROP_LEFT,
    CONF_CROP_RIGHT,
    CONF_CROP_TOP,
    DOMAIN,
)


async def _async_setup_amr(hass):
    # Domyślna fixture `hass` nie ma http - async_setup rejestruje tam
    # ścieżkę statyczną dla karty Lovelace (nie startuje realnego serwera w
    # tym środowisku testowym). add_extra_js_url wymaga PRAWDZIWEGO pakietu
    # home-assistant-frontend (ciężka zależność, nieużywana nigdzie indziej
    # w testach) - zamockowane, bo to gotowe, oficjalne HA API (samo
    # zarejestrowanie URL-a), nie logika tej integracji do przetestowania.
    await async_setup_component(hass, "http", {})
    with patch("custom_components.analog_meter_reader.add_extra_js_url"):
        await amr_async_setup(hass, {})


ENTRY_DATA = {
    CONF_CROP_LEFT: 0,
    CONF_CROP_TOP: 0,
    CONF_CROP_RIGHT: 100,
    CONF_CROP_BOTTOM: 100,
}


async def _make_entry_and_camera_entity(hass, object_id="test_wodomierz"):
    entry = MockConfigEntry(domain=DOMAIN, data=dict(ENTRY_DATA))
    entry.add_to_hass(hass)
    entity_entry = er.async_get(hass).async_get_or_create(
        "camera",
        DOMAIN,
        f"{entry.entry_id}_last_snapshot",
        config_entry=entry,
        suggested_object_id=object_id,
    )
    return entry, entity_entry.entity_id


async def test_set_crop_box_updates_entry_data(hass):
    await _async_setup_amr(hass)
    entry, entity_id = await _make_entry_and_camera_entity(hass)

    await hass.services.async_call(
        DOMAIN,
        "set_crop_box",
        {
            "entity_id": entity_id,
            "crop_left": 12,
            "crop_top": 34,
            "crop_right": 456,
            "crop_bottom": 789,
        },
        blocking=True,
    )

    assert entry.data[CONF_CROP_LEFT] == 12
    assert entry.data[CONF_CROP_TOP] == 34
    assert entry.data[CONF_CROP_RIGHT] == 456
    assert entry.data[CONF_CROP_BOTTOM] == 789


async def test_set_crop_box_preserves_other_data_fields(hass):
    """Regresja: handler musi scalić z istniejącym entry.data (spread), nie
    nadpisać go w całości - inaczej zgubiłby klucz API, provider itd."""
    await _async_setup_amr(hass)
    entry = MockConfigEntry(domain=DOMAIN, data={**ENTRY_DATA, "api_key": "tajny-klucz"})
    entry.add_to_hass(hass)
    entity_entry = er.async_get(hass).async_get_or_create(
        "camera", DOMAIN, f"{entry.entry_id}_last_snapshot", config_entry=entry
    )

    await hass.services.async_call(
        DOMAIN,
        "set_crop_box",
        {
            "entity_id": entity_entry.entity_id,
            "crop_left": 1,
            "crop_top": 2,
            "crop_right": 3,
            "crop_bottom": 4,
        },
        blocking=True,
    )

    assert entry.data["api_key"] == "tajny-klucz"


async def test_set_crop_box_rejects_inverted_box(hass):
    await _async_setup_amr(hass)
    entry, entity_id = await _make_entry_and_camera_entity(hass)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "set_crop_box",
            {"entity_id": entity_id, "crop_left": 100, "crop_top": 0, "crop_right": 10, "crop_bottom": 50},
            blocking=True,
        )
    assert entry.data == ENTRY_DATA


async def test_set_crop_box_rejects_unknown_entity(hass):
    await _async_setup_amr(hass)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "set_crop_box",
            {
                "entity_id": "camera.nie_istnieje",
                "crop_left": 0,
                "crop_top": 0,
                "crop_right": 10,
                "crop_bottom": 10,
            },
            blocking=True,
        )


async def test_set_crop_box_rejects_entity_from_other_domain(hass):
    await _async_setup_amr(hass)
    other_entry = MockConfigEntry(domain="other_integration", data={})
    other_entry.add_to_hass(hass)
    entity_entry = er.async_get(hass).async_get_or_create(
        "camera", "other_integration", "unique123", config_entry=other_entry
    )

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "set_crop_box",
            {
                "entity_id": entity_entry.entity_id,
                "crop_left": 0,
                "crop_top": 0,
                "crop_right": 10,
                "crop_bottom": 10,
            },
            blocking=True,
        )
