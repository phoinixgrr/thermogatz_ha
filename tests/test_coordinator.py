"""Tests for the connection handling."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.thermogatz import coordinator as mod
from custom_components.thermogatz.coordinator import ThermogatzDevice
from custom_components.thermogatz.protocol import request_status, request_temps, set_unit_celsius

from .conftest import ADDRESS, NO_PROBES_FRAME, PROBE4_FRAME, STATUS_FRAME


@pytest.fixture
def device(hass):
    return ThermogatzDevice(hass, ADDRESS, "AT-02 5F3E")


def fake_client() -> MagicMock:
    client = MagicMock()
    client.start_notify = AsyncMock()
    client.write_gatt_char = AsyncMock()
    client.disconnect = AsyncMock()
    return client


def test_notifications_update_state(device):
    device._async_notification(None, bytearray(STATUS_FRAME))
    device._async_notification(None, bytearray(PROBE4_FRAME))
    assert device.battery == 68
    assert device.probes[3] == 136.0
    assert device.ambient is None
    device._async_notification(None, bytearray(NO_PROBES_FRAME))
    assert device.probes == [None] * 4
    assert device.ambient == 18.8


def test_listeners_are_called_and_removable(device):
    calls = []
    remove = device.async_add_listener(lambda: calls.append(1))
    device._async_notification(None, bytearray(PROBE4_FRAME))
    assert calls == [1]
    remove()
    device._async_notification(None, bytearray(PROBE4_FRAME))
    assert calls == [1]


async def test_fahrenheit_device_is_switched_to_celsius(device):
    device._client = fake_client()
    device._async_notification(None, bytearray(bytes.fromhex("55aa0008a044000b01c00501dd")))
    await asyncio.sleep(0)
    device._client.write_gatt_char.assert_awaited_with(mod.WRITE_UUID, set_unit_celsius(), response=False)


async def test_status_is_requested_again_while_battery_unknown(device):
    device._client = fake_client()
    device._async_notification(None, bytearray(PROBE4_FRAME))
    await asyncio.sleep(0)
    device._client.write_gatt_char.assert_awaited_once_with(mod.WRITE_UUID, request_status(), response=False)
    # rate limited
    device._async_notification(None, bytearray(PROBE4_FRAME))
    await asyncio.sleep(0)
    assert device._client.write_gatt_char.await_count == 1


async def test_status_not_requested_once_battery_known(device):
    device._client = fake_client()
    device._async_notification(None, bytearray(STATUS_FRAME))
    device._async_notification(None, bytearray(PROBE4_FRAME))
    await asyncio.sleep(0)
    device._client.write_gatt_char.assert_not_awaited()


async def test_connect_starts_stream(device):
    client = fake_client()
    with (
        patch.object(mod, "establish_connection", AsyncMock(return_value=client)),
        patch.object(mod.asyncio, "sleep", AsyncMock()),
        patch.object(mod, "bluetooth"),
    ):
        assert await device._async_connect(MagicMock()) is True
    assert device.connected
    client.start_notify.assert_awaited_once()
    writes = [c.args[1] for c in client.write_gatt_char.await_args_list]
    assert writes == [request_status(), request_temps()]


async def test_failed_connect_returns_false_and_disconnects(device):
    client = fake_client()
    client.start_notify.side_effect = RuntimeError("boom")
    with patch.object(mod, "establish_connection", AsyncMock(return_value=client)), patch.object(mod, "bluetooth"):
        assert await device._async_connect(MagicMock()) is False
    assert not device.connected
    client.disconnect.assert_awaited_once()


async def test_reconnect_loop_backs_off_exponentially(device):
    sleeps: list[float] = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    attempts = iter([False, False, False, False, True])

    async def fake_connect(_):
        ok = next(attempts)
        device.connected = ok
        return ok

    device._async_connect = fake_connect
    with patch.object(mod, "bluetooth"), patch.object(mod.asyncio, "sleep", fake_sleep):
        await device._async_reconnect_loop()
    assert sleeps == [2, 4, 8, 16]


async def test_backoff_is_capped(device):
    sleeps: list[float] = []

    async def fake_sleep(delay):
        sleeps.append(delay)
        if len(sleeps) == 8:
            device._stopping = True

    device._async_connect = AsyncMock(return_value=False)
    with patch.object(mod, "bluetooth"), patch.object(mod.asyncio, "sleep", fake_sleep):
        await device._async_reconnect_loop()
    assert max(sleeps) == 60


async def test_loop_waits_while_device_is_not_seen(device):
    device._async_connect = AsyncMock()
    stop = {"n": 0}

    async def fake_sleep(_):
        stop["n"] += 1
        device._stopping = stop["n"] >= 2

    with patch.object(mod, "bluetooth") as bt, patch.object(mod.asyncio, "sleep", fake_sleep):
        bt.async_ble_device_from_address.return_value = None
        await device._async_reconnect_loop()
    device._async_connect.assert_not_awaited()


async def test_disconnect_triggers_reconnect_loop(device):
    device.connected = True
    started = []
    device._async_reconnect_loop = lambda: started.append(1) or asyncio.sleep(0)
    device._async_disconnected(MagicMock())
    await asyncio.sleep(0)
    assert not device.connected
    assert started == [1]


async def test_only_one_reconnect_loop_at_a_time(device):
    started = []

    async def loop():
        started.append(1)
        await asyncio.sleep(0.05)

    device._async_reconnect_loop = loop
    device._ensure_connecting()
    device._ensure_connecting()
    await asyncio.sleep(0)
    assert started == [1]
    device._reconnect_task.cancel()


async def test_no_reconnect_when_stopping_or_connected(device):
    device._async_reconnect_loop = AsyncMock()
    device._stopping = True
    device._ensure_connecting()
    device._stopping = False
    device.connected = True
    device._ensure_connecting()
    assert device._reconnect_task is None


async def test_disconnect_clears_values(device):
    device._async_notification(None, bytearray(PROBE4_FRAME))
    device._ensure_connecting = MagicMock()
    device._async_disconnected(MagicMock())
    assert device.probes == [None] * 4 and device.ambient is None


async def test_watchdog_drops_a_silent_link(device):
    device.connected = True
    device._client = fake_client()
    device._last_frame = 0.0
    device._ensure_connecting = MagicMock()
    with patch.object(mod.time, "monotonic", return_value=1000.0):
        await device._async_watchdog(None)
    device._client.disconnect.assert_awaited_once()


async def test_watchdog_keeps_a_live_link_and_restarts_dead_loop(device):
    device.connected = True
    device._client = fake_client()
    device._last_frame = 995.0
    device._ensure_connecting = MagicMock()
    with patch.object(mod.time, "monotonic", return_value=1000.0):
        await device._async_watchdog(None)
    device._client.disconnect.assert_not_awaited()
    device._ensure_connecting.assert_called_once()


async def test_stop_cancels_loop_and_disconnects(device):
    client = fake_client()
    device._client = client
    device._reconnect_task = asyncio.get_running_loop().create_task(asyncio.sleep(10))
    await device.async_stop()
    await asyncio.sleep(0)
    assert device._reconnect_task.cancelled()
    client.disconnect.assert_awaited_once()
