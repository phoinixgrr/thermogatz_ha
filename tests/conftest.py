"""Shared fixtures for the Thermogatz integration tests."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ADDRESS = "AA:BB:CC:DD:5F:3E"

# Frames captured from a real AT-02 (see docs/protocol.md).
STATUS_FRAME = bytes.fromhex("55aa0008a044000b00c00501dc")
NO_PROBES_FRAME = bytes.fromhex("55aa000fa1ffffffffffffffffffffffff00bced")
PROBE4_FRAME = bytes.fromhex("55aa000fa1ffffffffffff0550ffffffffffff04")


@pytest.fixture
def hass() -> MagicMock:
    """A hass stand-in that really runs background tasks."""
    hass = MagicMock()

    def run(coro, name=None):
        try:
            return asyncio.get_running_loop().create_task(coro)
        except RuntimeError:  # sync test: nothing to run the task on
            coro.close()
            return MagicMock()

    hass.async_create_background_task.side_effect = run
    return hass
