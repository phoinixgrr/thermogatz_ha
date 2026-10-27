"""Thermogatz BBQ Thermometer (Haibosi AT-02) over Bluetooth LE."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant

from .coordinator import ThermogatzDevice

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]

type ThermogatzConfigEntry = ConfigEntry[ThermogatzDevice]


async def async_setup_entry(hass: HomeAssistant, entry: ThermogatzConfigEntry) -> bool:
    """Set up a thermometer from a config entry."""
    device = ThermogatzDevice(hass, entry.data[CONF_ADDRESS], entry.title)
    entry.runtime_data = device
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await device.async_start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ThermogatzConfigEntry) -> bool:
    """Unload a config entry."""
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_stop()
    return unloaded
