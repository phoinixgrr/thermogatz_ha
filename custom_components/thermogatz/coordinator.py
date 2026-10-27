"""Persistent BLE connection to a Thermogatz AT-02."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import timedelta
import logging
import time

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    NOTIFY_UUID,
    PROBE_COUNT,
    STALE_AFTER_SECONDS,
    STATUS_POLL_SECONDS,
    WRITE_UUID,
)
from .protocol import (
    FrameParser,
    Status,
    Temps,
    request_status,
    request_temps,
    set_unit_celsius,
)

_LOGGER = logging.getLogger(__name__)

_WATCHDOG_INTERVAL = timedelta(seconds=10)
_STATUS_RETRY_SECONDS = 10
_RECONNECT_MIN_SECONDS = 2
_RECONNECT_MAX_SECONDS = 60


class ThermogatzDevice:
    """Keep one connection open and fan the decoded data out to entities.

    The AT-02 accepts a single BLE connection, so while Home Assistant holds it
    the phone app cannot connect. Disable the config entry to hand it back.
    """

    def __init__(self, hass: HomeAssistant, address: str, name: str) -> None:
        self.hass = hass
        self.address = address
        self.name = name
        self.battery: int | None = None
        self.firmware: str | None = None
        self.probes: list[float | None] = [None] * PROBE_COUNT
        self.ambient: float | None = None
        self.connected = False

        self._client: BleakClient | None = None
        self._parser = FrameParser()
        self._listeners: list[Callable[[], None]] = []
        self._reconnect_task: asyncio.Task[None] | None = None
        self._last_frame = 0.0
        self._last_status_request = 0.0
        self._unsub: list[CALLBACK_TYPE] = []
        self._stopping = False

    @callback
    def async_add_listener(self, update: Callable[[], None]) -> CALLBACK_TYPE:
        """Register an entity callback."""
        self._listeners.append(update)

        @callback
        def remove() -> None:
            self._listeners.remove(update)

        return remove

    @callback
    def _notify_listeners(self) -> None:
        for update in list(self._listeners):
            update()

    async def async_start(self) -> None:
        """Start watching for the device and keep it connected."""
        self._unsub.append(
            bluetooth.async_register_callback(
                self.hass,
                self._async_advertisement,
                bluetooth.BluetoothCallbackMatcher(
                    address=self.address, connectable=True
                ),
                bluetooth.BluetoothScanningMode.ACTIVE,
            )
        )
        self._unsub.append(
            async_track_time_interval(self.hass, self._async_watchdog, _WATCHDOG_INTERVAL)
        )
        self._unsub.append(
            async_track_time_interval(
                self.hass, self._async_poll_status, timedelta(seconds=STATUS_POLL_SECONDS)
            )
        )
        self._ensure_connecting()

    async def async_stop(self) -> None:
        """Disconnect and stop reconnecting."""
        self._stopping = True
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()
        if self._reconnect_task is not None:
            self._reconnect_task.cancel()
        if self._client is not None:
            await self._client.disconnect()

    @callback
    def _async_advertisement(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        self._ensure_connecting()

    @callback
    def _ensure_connecting(self) -> None:
        """Make sure exactly one reconnect loop is running while disconnected.

        Relying on advertisements alone is not enough: Home Assistant only
        delivers an advertisement when its content changed, so a thermometer
        that keeps sending the same packet would never trigger a reconnect.
        """
        if self._stopping or self.connected:
            return
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = self.hass.async_create_background_task(
                self._async_reconnect_loop(), f"thermogatz reconnect {self.address}"
            )

    async def _async_reconnect_loop(self) -> None:
        """Connect, retrying with exponential backoff until it works."""
        delay = _RECONNECT_MIN_SECONDS
        while not self._stopping and not self.connected:
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if ble_device is not None and await self._async_connect(ble_device):
                return
            _LOGGER.debug("%s not connected, retrying in %ss", self.address, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, _RECONNECT_MAX_SECONDS)

    async def _async_connect(self, ble_device: BLEDevice) -> bool:
        """Open the link and start the stream. Returns True on success."""
        client: BleakClient | None = None
        try:
            client = await establish_connection(
                BleakClientWithServiceCache,
                ble_device,
                self.name,
                self._async_disconnected,
                ble_device_callback=lambda: bluetooth.async_ble_device_from_address(
                    self.hass, self.address, connectable=True
                )
                or ble_device,
            )
            self._parser = FrameParser()
            await client.start_notify(NOTIFY_UUID, self._async_notification)
            self._client = client
            self.connected = True
            self._last_frame = time.monotonic()
            self._last_status_request = time.monotonic()
            await client.write_gatt_char(WRITE_UUID, request_status(), response=False)
            await asyncio.sleep(0.5)
            await client.write_gatt_char(WRITE_UUID, request_temps(), response=False)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Connecting to %s failed: %s", self.address, err)
            if client is not None:
                await client.disconnect()
            self._set_disconnected()
            return False
        self._notify_listeners()
        return True

    @callback
    def _async_disconnected(self, client: BleakClient) -> None:
        _LOGGER.debug("%s disconnected", self.address)
        self._set_disconnected()
        self._ensure_connecting()

    @callback
    def _set_disconnected(self) -> None:
        self.connected = False
        self._client = None
        self.probes = [None] * PROBE_COUNT
        self.ambient = None
        self._notify_listeners()

    def _async_notification(self, _: object, data: bytearray) -> None:
        for frame in self._parser.feed(bytes(data)):
            self._last_frame = time.monotonic()
            if isinstance(frame, Status):
                self.battery = frame.battery
                self.firmware = frame.firmware
                if frame.fahrenheit and self._client is not None:
                    self.hass.async_create_background_task(
                        self._async_write(set_unit_celsius()),
                        f"thermogatz unit {self.address}",
                    )
            elif isinstance(frame, Temps):
                self.probes = list(frame.probes[:PROBE_COUNT])
                self.ambient = frame.ambient
                self._ask_status_if_unknown()
        self._notify_listeners()

    @callback
    def _ask_status_if_unknown(self) -> None:
        """Repeat the status request until battery is known.

        The first request, sent right after connecting, can be lost on a busy
        proxy link, and the next scheduled poll is minutes away.
        """
        now = time.monotonic()
        if self.battery is None and now - self._last_status_request > _STATUS_RETRY_SECONDS:
            self._last_status_request = now
            self.hass.async_create_background_task(
                self._async_write(request_status()), f"thermogatz status {self.address}"
            )

    async def _async_write(self, frame: bytes) -> None:
        if self._client is None:
            return
        try:
            await self._client.write_gatt_char(WRITE_UUID, frame, response=False)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Write to %s failed: %s", self.address, err)

    async def _async_poll_status(self, _: object) -> None:
        if self.connected:
            await self._async_write(request_status())

    async def _async_watchdog(self, _: object) -> None:
        """Drop a link that stopped delivering so it gets re-established."""
        self._ensure_connecting()
        if (
            self.connected
            and self._client is not None
            and time.monotonic() - self._last_frame > STALE_AFTER_SECONDS
        ):
            _LOGGER.debug("%s went quiet, reconnecting", self.address)
            await self._client.disconnect()
