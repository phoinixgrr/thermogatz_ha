"""Tests for the connection sensor."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.thermogatz.binary_sensor import ConnectionSensor, async_setup_entry
from custom_components.thermogatz.coordinator import ThermogatzDevice

from .conftest import ADDRESS


async def test_setup_adds_the_connection_sensor(hass):
    entry = MagicMock()
    entry.runtime_data = ThermogatzDevice(hass, ADDRESS, "AT-02 5F3E")
    added = []
    await async_setup_entry(hass, entry, lambda entities: added.extend(entities))
    assert len(added) == 1 and added[0].unique_id == f"{ADDRESS}_connection"


async def test_connection_sensor_follows_the_link(hass):
    device = ThermogatzDevice(hass, ADDRESS, "AT-02 5F3E")
    sensor = ConnectionSensor(device)
    sensor.async_write_ha_state = MagicMock()
    sensor.async_on_remove = MagicMock()
    await sensor.async_added_to_hass()
    assert sensor.is_on is False
    device.connected = True
    device._notify_listeners()
    assert sensor.is_on is True
    sensor.async_write_ha_state.assert_called()
