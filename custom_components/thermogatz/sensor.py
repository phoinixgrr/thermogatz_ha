"""Sensors for Thermogatz."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ThermogatzConfigEntry
from .const import DOMAIN, PROBE_COUNT
from .coordinator import ThermogatzDevice


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ThermogatzConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    device = entry.runtime_data
    async_add_entities(
        [ProbeSensor(device, i) for i in range(PROBE_COUNT)]
        + [
            AmbientSensor(device),
            BatterySensor(device),
            FirmwareSensor(device),
            AlarmIntervalSensor(device),
        ]
    )


class ThermogatzEntity(SensorEntity):
    """Base class: push updates from the device."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, device: ThermogatzDevice) -> None:
        self._device = device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.address)},
            name=device.name,
            manufacturer="Thermogatz",
            model="AT-02",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to device updates."""
        self.async_on_remove(self._device.async_add_listener(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class ProbeSensor(ThermogatzEntity):
    """Temperature of one probe socket."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, device: ThermogatzDevice, index: int) -> None:
        super().__init__(device)
        self._index = index
        self._attr_unique_id = f"{device.address}_probe_{index + 1}"
        self._attr_translation_key = "probe"
        self._attr_translation_placeholders = {"number": str(index + 1)}

    @property
    def native_value(self) -> float | None:
        """Probe temperature, None when nothing is plugged in."""
        return self._device.probes[self._index]

    @property
    def available(self) -> bool:
        """Unavailable while disconnected or when the socket is empty."""
        return self._device.connected and self.native_value is not None


class AmbientSensor(ThermogatzEntity):
    """Ambient (grill) temperature, the separate seventh slot."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_translation_key = "ambient"

    def __init__(self, device: ThermogatzDevice) -> None:
        super().__init__(device)
        self._attr_unique_id = f"{device.address}_ambient"

    @property
    def native_value(self) -> float | None:
        """Ambient temperature, None when not reported."""
        return self._device.ambient

    @property
    def available(self) -> bool:
        """Unavailable while disconnected or when the slot is empty."""
        return self._device.connected and self.native_value is not None


class BatterySensor(ThermogatzEntity):
    """Thermometer battery level."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, device: ThermogatzDevice) -> None:
        super().__init__(device)
        self._attr_unique_id = f"{device.address}_battery"

    @property
    def native_value(self) -> int | None:
        """Battery percentage."""
        return self._device.battery

    @property
    def available(self) -> bool:
        """Available while connected and the status reply has arrived."""
        return self._device.connected and self._device.battery is not None


class FirmwareSensor(ThermogatzEntity):
    """Firmware version reported by the thermometer."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "firmware"

    def __init__(self, device: ThermogatzDevice) -> None:
        super().__init__(device)
        self._attr_unique_id = f"{device.address}_firmware"

    @property
    def native_value(self) -> str | None:
        """Firmware version, kept after the link drops because it does not change."""
        return self._device.firmware

    @property
    def available(self) -> bool:
        """Available once the thermometer has reported it."""
        return self._device.firmware is not None


class AlarmIntervalSensor(ThermogatzEntity):
    """How often the thermometer repeats an alarm, as set on the device."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "alarm_interval"

    def __init__(self, device: ThermogatzDevice) -> None:
        super().__init__(device)
        self._attr_unique_id = f"{device.address}_alarm_interval"

    @property
    def native_value(self) -> int | None:
        """Alarm repeat interval in minutes."""
        return self._device.alarm_interval

    @property
    def available(self) -> bool:
        """Available once the thermometer has reported it."""
        return self._device.alarm_interval is not None
