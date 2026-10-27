"""Tests for the AT-02 wire protocol."""

from __future__ import annotations

from custom_components.thermogatz.protocol import (
    FrameParser,
    Status,
    Temps,
    build_frame,
    request_status,
    request_temps,
    set_unit_celsius,
    xor_checksum,
)

from .conftest import NO_PROBES_FRAME, PROBE4_FRAME, STATUS_FRAME


def test_checksum_is_xor():
    assert xor_checksum(b"\x55\xaa\x00\x02\xa1\x00") == 0x5C


def test_requests_match_what_the_app_sends():
    assert request_status().hex() == "55aa0003a000005c"
    assert request_temps().hex() == "55aa0002a1005c"


def test_set_unit_frame_is_valid():
    frame = set_unit_celsius()
    assert frame[:5].hex() == "55aa0003a6"
    assert xor_checksum(frame[:-1]) == frame[-1]


def test_build_frame_length_counts_command_and_payload():
    frame = build_frame(0xA1, b"\x01\x02\x03")
    assert frame[3] == 4


def test_status_frame():
    assert FrameParser().feed(STATUS_FRAME) == [Status(battery=68, firmware="0.11", fahrenheit=False)]


def test_probe_4_connected():
    [temps] = FrameParser().feed(PROBE4_FRAME)
    assert isinstance(temps, Temps)
    assert temps.probes == (None, None, None, 136.0, None, None)
    assert temps.ambient is None


def test_ambient_only():
    [temps] = FrameParser().feed(NO_PROBES_FRAME)
    assert temps.probes == (None,) * 6
    assert temps.ambient == 18.8


def test_frame_split_across_notifications():
    parser = FrameParser()
    assert parser.feed(PROBE4_FRAME[:7]) == []
    assert len(parser.feed(PROBE4_FRAME[7:])) == 1


def test_two_frames_in_one_chunk():
    assert len(FrameParser().feed(STATUS_FRAME + PROBE4_FRAME)) == 2


def test_bad_checksum_is_dropped():
    bad = bytearray(PROBE4_FRAME)
    bad[-1] ^= 0xFF
    assert FrameParser().feed(bytes(bad)) == []


def test_garbage_before_header_is_skipped():
    assert len(FrameParser().feed(b"\x01\x02\x03" + PROBE4_FRAME)) == 1


def test_negative_and_out_of_range_values():
    def temps(raw_hex: str):
        payload = bytes.fromhex(raw_hex) + bytes.fromhex("ffff") * 5
        frame = bytes([0x55, 0xAA, 0x00, len(payload) + 1, 0xA1]) + payload
        frame += bytes([xor_checksum(frame)])
        return FrameParser().feed(frame)[0].probes[0]

    assert temps("8032") == -5.0  # sign-magnitude: 0x8000 + 50
    assert temps("efff") is None  # over range
    assert temps("f000") is None  # under range
    assert temps("ffff") is None  # nothing plugged in


def test_unknown_command_is_ignored():
    body = bytes([0x55, 0xAA, 0x00, 0x02, 0xEE, 0x01])
    assert FrameParser().feed(body + bytes([xor_checksum(body)])) == []
