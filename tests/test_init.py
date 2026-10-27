"""Tests for entry setup and unload."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_ADDRESS

import custom_components.thermogatz as integration

from .conftest import ADDRESS


async def test_setup_entry_starts_the_device(hass):
    entry = MagicMock(data={CONF_ADDRESS: ADDRESS}, title="AT-02 5F3E")
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    with patch.object(integration, "ThermogatzDevice") as device_cls:
        device_cls.return_value.async_start = AsyncMock()
        assert await integration.async_setup_entry(hass, entry) is True
    device_cls.assert_called_once_with(hass, ADDRESS, "AT-02 5F3E")
    hass.config_entries.async_forward_entry_setups.assert_awaited_once()
    device_cls.return_value.async_start.assert_awaited_once()


async def test_unload_entry_stops_the_device(hass):
    entry = MagicMock()
    entry.runtime_data.async_stop = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    assert await integration.async_unload_entry(hass, entry) is True
    entry.runtime_data.async_stop.assert_awaited_once()


async def test_failed_platform_unload_keeps_the_device_running(hass):
    entry = MagicMock()
    entry.runtime_data.async_stop = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)
    assert await integration.async_unload_entry(hass, entry) is False
    entry.runtime_data.async_stop.assert_not_awaited()
