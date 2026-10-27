"""Wire protocol of the Haibosi / Thermogatz AT-02 BBQ thermometer.

Frames, in both directions, on the cee1 (write) and cee2 (notify) characteristics:

    55 AA 00 <len> <cmd> <payload...> <xor>

``len`` counts the command byte plus the payload. ``xor`` is the XOR of every
preceding byte of the frame.
"""

from __future__ import annotations

from dataclasses import dataclass

HEADER = b"\x55\xaa\x00"

CMD_STATUS = 0xA0
CMD_TEMPS = 0xA1
CMD_SET_UNIT = 0xA6

NO_PROBE = 0xFFFF
PROBE_OVER_RANGE = 0xEFFF
PROBE_UNDER_RANGE = 0xF000


def xor_checksum(data: bytes) -> int:
    """XOR of all bytes."""
    value = 0
    for byte in data:
        value ^= byte
    return value


def build_frame(cmd: int, payload: bytes = b"") -> bytes:
    """Build a command frame."""
    body = HEADER + bytes([len(payload) + 1, cmd]) + payload
    return body + bytes([xor_checksum(body)])


def request_status() -> bytes:
    """Ask for battery, firmware and unit."""
    return build_frame(CMD_STATUS, b"\x00\x00")


def request_temps() -> bytes:
    """Start the one-per-second temperature stream."""
    return build_frame(CMD_TEMPS, b"\x00")


def set_unit_celsius() -> bytes:
    """Switch the device to degrees Celsius."""
    return build_frame(CMD_SET_UNIT, b"\x00\xff")


@dataclass(frozen=True)
class Status:
    """Reply to the status request."""

    battery: int
    firmware: str
    fahrenheit: bool
    alarm_interval: int | None = None


@dataclass(frozen=True)
class Temps:
    """One temperature report. A value is None when nothing is plugged in.

    ``probes`` are the numbered sockets; ``ambient`` is the separate seventh
    slot the app shows as the grill (ambient) temperature.
    """

    probes: tuple[float | None, ...]
    ambient: float | None


def _decode_temp(hi: int, lo: int) -> float | None:
    raw = (hi << 8) | lo
    if raw in (NO_PROBE, PROBE_OVER_RANGE, PROBE_UNDER_RANGE):
        return None
    if raw > 0x8000:
        raw = -(raw - 0x8000)
    return raw / 10


class FrameParser:
    """Reassemble frames from notification chunks."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[Status | Temps]:
        """Add a chunk and return every complete, valid frame decoded from it."""
        self._buf += data
        out: list[Status | Temps] = []
        while True:
            start = self._buf.find(HEADER)
            if start < 0:
                self._buf.clear()
                break
            if start:
                del self._buf[:start]
            if len(self._buf) < 5:
                break
            total = 3 + 1 + self._buf[3] + 1
            if len(self._buf) < total:
                break
            frame = bytes(self._buf[:total])
            del self._buf[:total]
            if xor_checksum(frame[:-1]) != frame[-1]:
                continue
            decoded = _decode(frame[4], frame[5:-1])
            if decoded is not None:
                out.append(decoded)
        return out


def _decode(cmd: int, payload: bytes) -> Status | Temps | None:
    if cmd == CMD_STATUS and len(payload) >= 4:
        return Status(
            battery=payload[0],
            firmware=f"{payload[1]}.{payload[2]}",
            fahrenheit=payload[3] != 0,
            alarm_interval=payload[5] if len(payload) > 5 else None,
        )
    if cmd == CMD_TEMPS and len(payload) >= 12:
        values = [_decode_temp(hi, lo) for hi, lo in zip(payload[0::2], payload[1::2])]
        return Temps(probes=tuple(values[:6]), ambient=values[6] if len(values) > 6 else None)
    return None
