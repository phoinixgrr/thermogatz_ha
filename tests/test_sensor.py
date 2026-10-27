"""Tests for the sensor entities."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from custom_components.thermogatz.coordinator import ThermogatzDevice
from custom_components.thermogatz.sensor import (
    AlarmIntervalSensor,
    AmbientSensor,
    BatterySensor,
    FirmwareSensor,
    ProbeSensor,
    async_setup_entry,
)

from .conftest import ADDRESS, NO_PROBES_FRAME, PROBE4_FRAME, STATUS_FRAME


def make_device(hass) -> ThermogatzDevice:
    return ThermogatzDevice(hass, ADDRESS, "AT-02 5F3E")


def test_probe_sensor_values_and_availability(hass):
    device = make_device(hass)
    sensor = ProbeSensor(device, 3)
    assert sensor.native_value is None and not sensor.available
    device.connected = True
    device._async_notification(None, bytearray(PROBE4_FRAME))
    assert sensor.native_value == 136.0 and sensor.available
    assert not ProbeSensor(device, 0).available
    device.connected = False
    assert not sensor.available


def test_ambient_sensor(hass):
    device = make_device(hass)
    device.connected = True
    sensor = AmbientSensor(device)
    assert not sensor.available
    device._async_notification(None, bytearray(NO_PROBES_FRAME))
    assert sensor.native_value == 18.8 and sensor.available


def test_battery_sensor_goes_unavailable_with_the_link(hass):
    device = make_device(hass)
    sensor = BatterySensor(device)
    device._async_notification(None, bytearray(STATUS_FRAME))
    assert sensor.native_value == 68
    assert not sensor.available  # not connected
    device.connected = True
    assert sensor.available


def test_unique_ids_are_stable_and_distinct(hass):
    device = make_device(hass)
    entities = [ProbeSensor(device, i) for i in range(4)] + [
        AmbientSensor(device),
        BatterySensor(device),
        FirmwareSensor(device),
        AlarmIntervalSensor(device),
    ]
    ids = [e.unique_id for e in entities]
    assert len(set(ids)) == 8
    assert ids[0] == f"{ADDRESS}_probe_1" and ids[4] == f"{ADDRESS}_ambient" and ids[5] == f"{ADDRESS}_battery"


async def test_setup_creates_all_entities(hass):
    entry = MagicMock()
    entry.runtime_data = make_device(hass)
    added = []
    await async_setup_entry(hass, entry, lambda entities: added.extend(entities))
    assert len(added) == 8


async def test_entity_follows_device_updates(hass):
    device = make_device(hass)
    sensor = ProbeSensor(device, 3)
    sensor.async_write_ha_state = MagicMock()
    sensor.async_on_remove = MagicMock()
    await sensor.async_added_to_hass()
    device._async_notification(None, bytearray(PROBE4_FRAME))
    sensor.async_write_ha_state.assert_called()
    await asyncio.sleep(0)


def test_firmware_and_alarm_interval_survive_a_dropped_link(hass):
    device = make_device(hass)
    firmware, interval = FirmwareSensor(device), AlarmIntervalSensor(device)
    assert not firmware.available and not interval.available
    device._async_notification(None, bytearray(STATUS_FRAME))
    assert firmware.native_value == "0.11" and firmware.available
    assert interval.native_value == 5 and interval.available
    device._set_disconnected()
    assert firmware.available and interval.available
