"""Binary sensors for Thermogatz."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ThermogatzConfigEntry
from .const import DOMAIN
from .coordinator import ThermogatzDevice


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ThermogatzConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    async_add_entities([ConnectionSensor(entry.runtime_data)])


class ConnectionSensor(BinarySensorEntity):
    """Whether Home Assistant currently holds the Bluetooth link."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "connection"

    def __init__(self, device: ThermogatzDevice) -> None:
        self._device = device
        self._attr_unique_id = f"{device.address}_connection"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.address)},
            name=device.name,
            manufacturer="Thermogatz",
            model="AT-02",
        )

    @property
    def is_on(self) -> bool:
        """True while the link is up."""
        return self._device.connected

    async def async_added_to_hass(self) -> None:
        """Subscribe to device updates."""
        self.async_on_remove(self._device.async_add_listener(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
