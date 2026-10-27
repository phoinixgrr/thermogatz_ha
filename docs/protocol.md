# AT-02 Bluetooth protocol

Everything below was read from the vendor app and then confirmed against a real AT-02 (firmware 0.11). Addresses
in the examples are placeholders. See [reverse-engineering.md](reverse-engineering.md) for how it was found.

## Advertisement

| Field | Value |
|---|---|
| Local name | `AT-02` |
| Service UUID | `0000cee0-0000-1000-8000-00805f9b34fb` |
| Manufacturer data | the device address in reverse byte order plus `00` (see below) |
| Address type | public |
| Connectable | yes, **one connection at a time** |

The raw packet of an example device with the address `AA:BB:CC:DD:5F:3E`:

```
02 01 06                      flags
08 ff 3e 5f dd cc bb aa 00    manufacturer data
03 02 e0 ce                   complete 16-bit service list: 0xCEE0
06 09 41 54 2d 30 32          complete local name "AT-02"
```

The manufacturer data is the device address in reverse byte order (`3e 5f dd cc bb aa` is `AA:BB:CC:DD:5F:3E`),
plus a trailing `00`. Bluetooth reads the first two bytes as a company id, so that "id" differs on every unit and
means nothing, so match on the name or the service UUID. The advertisement carries **no temperatures**, so you have to connect.

While a central is connected the thermometer stops advertising, which is why it vanishes from Home Assistant's
Bluetooth devices while the phone app (or this integration) holds it.

## GATT

No pairing or encryption is needed. The phone shows the device as bonded, but a plain connection works.

| Characteristic | UUID | Properties | Handle seen |
|---|---|---|---|
| Service | `0000cee0-0000-1000-8000-00805f9b34fb` | | |
| Command | `0000cee1-0000-1000-8000-00805f9b34fb` | write without response | 11 |
| Data | `0000cee2-0000-1000-8000-00805f9b34fb` | notify | 14 |

Default ATT MTU is 23, so every frame fits one 20-byte notification. The parser still reassembles split frames.

## Frame format

Both directions use the same frame:

```
55 AA 00 <len> <cmd> <payload ...> <xor>
```

- `len` is `1 + payload length` (the command byte plus the payload, without the header and checksum)
- `xor` is the XOR of every preceding byte of the frame
- multi-byte numbers are big-endian

## Commands

| Cmd | Direction | Meaning |
|---|---|---|
| `A0` | request `55 AA 00 03 A0 00 00 5C`, reply | status: battery, firmware, unit |
| `A1` | request `55 AA 00 02 A1 00 5C`, then one reply per second | temperatures |
| `A6` | request | set temperature unit |
| `A5` | notification | alarm event (not decoded by this integration) |
| `A8` | request | sent by the app after connecting, purpose unknown, and the thermometer works without it |

The device sends nothing until it is asked: connect, subscribe to `cee2`, write `A0` and then `A1`. After one
`A1` request the stream continues until the link drops. The app does the same with a short pause between the writes.

### `A0` status reply

```
55 AA 00 08 A0 | 44 00 0B 00 C0 05 01 | DC
                 |  |  |  |  |  |  |
                 |  |  |  |  |  +--+-- unknown (05 01 on the sample device)
                 |  |  |  |  +-------- unknown flags (C0)
                 |  |  |  +----------- unit, 00 = Celsius, 01 = Fahrenheit
                 |  +--+-------------- firmware major.minor = 0.11
                 +-------------------- battery percent (0x44 = 68)
```

### `A1` temperature reply

```
55 AA 00 0F A1 | ff ff  ff ff  ff ff  05 50  ff ff  ff ff  00 bc | 04
                 slot1  slot2  slot3  slot4  slot5  slot6  slot7
```

Seven 16-bit slots, tenths of a degree:

| Slot | Meaning on the AT-02 |
|---|---|
| 1 to 4 | probe sockets 1 to 4 |
| 5, 6 | probe 5 and 6 on bigger models, always `ffff` on the AT-02 |
| 7 | ambient (grill) temperature, the app calls it probe 0 |

Special values:

| Raw | Meaning |
|---|---|
| `ffff` | nothing plugged in |
| `efff` | over range |
| `f000` | under range |
| above `8000` | negative, `-(raw - 0x8000)` |

Examples:

| Frame ends with | Decoded |
|---|---|
| `... ff ff ff ff ff ff 05 50 ff ff ff ff ff ff 04` | probe 4 = `0x0550` = 1360 = **136.0 °C** |
| `... ff ff ff ff ff ff ff ff ff ff ff ff 00 bc ed` | ambient = `0x00BC` = 188 = **18.8 °C** |

The scale is tenths of a degree Celsius: the app converts with `(raw * 1.8 + 320) / 10` for Fahrenheit, and the
battery reading and the temperatures agree with the phone app.

### `A6` set unit

`55 AA 00 03 A6 <unit> FF <xor>`, unit `00` = Celsius, `01` = Fahrenheit. The app sends this on every connection to
make the thermometer match its own setting. The integration does the same, but only to force Celsius when the
status reply says the device is in Fahrenheit.

## What is not known

- The meaning of the last three `A0` bytes and of `A8`.
- Whether temperatures are sent in tenths of a degree Fahrenheit when the device is in Fahrenheit. The integration
  avoids the question by switching the device to Celsius.
- Alarm (`A5`) and target-temperature commands. They are not needed to read temperatures and are not implemented.
- Other models in the same family (names such as `AT-01`, `AT-03`, `AT-02W1`) share the app and probably the
  protocol, but only the AT-02 was tested.
