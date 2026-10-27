#!/usr/bin/env python3
"""Talk to an AT-02 from a computer, without Home Assistant.

Connects, asks for the status, starts the temperature stream and prints every
decoded frame (plus the raw bytes). Handy to check a thermometer, a new
firmware, or to capture traffic for a bug report.

    pip install bleak
    python3 tools/probe.py              # first AT-02 found, 30 seconds
    python3 tools/probe.py 60 AA:BB:..  # 60 seconds, a given address (macOS: CoreBluetooth UUID)

The thermometer accepts one connection at a time: close the phone app and
disable the Home Assistant entry first.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import time
from pathlib import Path

from bleak import BleakClient, BleakScanner

PROTOCOL = Path(__file__).resolve().parents[1] / "custom_components" / "thermogatz" / "protocol.py"
spec = importlib.util.spec_from_file_location("thermogatz_protocol", PROTOCOL)
protocol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)

WRITE_UUID = "0000cee1-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000cee2-0000-1000-8000-00805f9b34fb"


async def main() -> None:
    seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    target = sys.argv[2].upper() if len(sys.argv) > 2 else None

    print("scanning...")
    device = await BleakScanner.find_device_by_filter(
        lambda d, ad: (d.address.upper() == target) if target else (ad.local_name or d.name) == "AT-02",
        timeout=20,
    )
    if device is None:
        sys.exit("no AT-02 found (is the phone app closed and the Home Assistant entry disabled?)")

    parser = protocol.FrameParser()
    start = time.time()

    def on_notify(_, data: bytearray) -> None:
        for frame in parser.feed(bytes(data)):
            print(f"{time.time() - start:6.1f}s  {data.hex(' ')}\n         {frame}", flush=True)

    async with BleakClient(device) as client:
        print(f"connected to {device.address}, mtu {client.mtu_size}")
        await client.start_notify(NOTIFY_UUID, on_notify)
        await client.write_gatt_char(WRITE_UUID, protocol.request_status(), response=False)
        await asyncio.sleep(0.5)
        await client.write_gatt_char(WRITE_UUID, protocol.request_temps(), response=False)
        await asyncio.sleep(seconds)


if __name__ == "__main__":
    asyncio.run(main())
