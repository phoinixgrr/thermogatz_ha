"""Constants for the Thermogatz BBQ Thermometer integration."""

DOMAIN = "thermogatz"

SERVICE_UUID = "0000cee0-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000cee1-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000cee2-0000-1000-8000-00805f9b34fb"

# The AT-02 has four probe sockets.
PROBE_COUNT = 4

# No data for this long while connected means the link is dead.
STALE_AFTER_SECONDS = 20
# Battery and firmware are only sent on request.
STATUS_POLL_SECONDS = 300
