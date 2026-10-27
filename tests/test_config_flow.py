"""Tests for the config flow."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResultType

from custom_components.thermogatz import config_flow
from custom_components.thermogatz.config_flow import ThermogatzConfigFlow
from custom_components.thermogatz.const import SERVICE_UUID

from .conftest import ADDRESS


def info(address: str = ADDRESS, name: str = "AT-02", uuids=(SERVICE_UUID,)):
    return SimpleNamespace(address=address, name=name, service_uuids=list(uuids))


@pytest.fixture
def flow():
    f = ThermogatzConfigFlow()
    f.hass = MagicMock()
    f.context = {}
    f.async_set_unique_id = AsyncMock()
    f._abort_if_unique_id_configured = MagicMock()
    f._async_current_ids = MagicMock(return_value=set())
    return f


async def test_bluetooth_discovery_asks_for_confirmation(flow):
    result = await flow.async_step_bluetooth(info())
    assert result["type"] == FlowResultType.FORM and result["step_id"] == "bluetooth_confirm"
    flow.async_set_unique_id.assert_awaited_once_with(ADDRESS)
    assert result["description_placeholders"] == {"name": "AT-02 5F3E"}


async def test_bluetooth_confirm_creates_entry(flow):
    await flow.async_step_bluetooth(info())
    result = await flow.async_step_bluetooth_confirm({})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "AT-02 5F3E"
    assert result["data"] == {CONF_ADDRESS: ADDRESS}


async def test_user_step_lists_unconfigured_thermometers(flow):
    seen = [info(), info("11:22:33:44:55:66", "Other", uuids=()), info("AA:BB:CC:DD:EE:FF")]
    flow._async_current_ids.return_value = {"AA:BB:CC:DD:EE:FF"}
    with patch.object(config_flow, "async_discovered_service_info", return_value=seen):
        result = await flow.async_step_user()
    assert result["type"] == FlowResultType.FORM and result["step_id"] == "user"
    [schema_key] = result["data_schema"].schema
    assert list(result["data_schema"].schema[schema_key].container) == [ADDRESS]


async def test_user_step_aborts_when_nothing_found(flow):
    with patch.object(config_flow, "async_discovered_service_info", return_value=[]):
        result = await flow.async_step_user()
    assert result["type"] == FlowResultType.ABORT and result["reason"] == "no_devices_found"


async def test_user_step_creates_entry(flow):
    with patch.object(config_flow, "async_discovered_service_info", return_value=[info()]):
        await flow.async_step_user()
        result = await flow.async_step_user({CONF_ADDRESS: ADDRESS})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_ADDRESS: ADDRESS}
