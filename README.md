[![Validate with HACS Action](https://github.com/phoinixgrr/thermogatz_ha/actions/workflows/hacs-validation.yml/badge.svg)](https://github.com/phoinixgrr/thermogatz_ha/actions/workflows/hacs-validation.yml)
[![Validate with hassfest Action](https://github.com/phoinixgrr/thermogatz_ha/actions/workflows/hassfest-validation.yaml/badge.svg)](https://github.com/phoinixgrr/thermogatz_ha/actions/workflows/hassfest-validation.yaml)
[![Tests](https://github.com/phoinixgrr/thermogatz_ha/actions/workflows/tests.yml/badge.svg)](https://github.com/phoinixgrr/thermogatz_ha/actions/workflows/tests.yml)
[![codecov](https://codecov.io/gh/phoinixgrr/thermogatz_ha/branch/main/graph/badge.svg)](https://codecov.io/gh/phoinixgrr/thermogatz_ha)

<h1><img src="https://raw.githubusercontent.com/phoinixgrr/thermogatz_ha/main/custom_components/thermogatz/brand/logo.png" alt="Thermogatz for Home Assistant" width="420"></h1>

Local Bluetooth integration for the **Thermogatz AT-02** wireless BBQ thermometer. Probe and ambient temperatures
and the battery level in Home Assistant, with no cloud account and no phone app.

![Device page](images/device.png)

## The device

The AT-02 is a round Bluetooth grill thermometer that mounts on a grill, smoker or kamado. It has
a small LCD with the current temperature and probe number, four sockets for food probes (the numbered orange flaps), and one
ambient probe on a threaded stem that goes through the grill wall and is held by a fixing nut, so it measures the
air inside the cooker. The case is rated IP54. The same vendor app is sold under the ToGrill and Thermogatz names.

<p>
  <img src="https://raw.githubusercontent.com/phoinixgrr/thermogatz_ha/main/images/product-overview.jpg" alt="The AT-02 with its food probes" width="32%">
  <img src="https://raw.githubusercontent.com/phoinixgrr/thermogatz_ha/main/images/product-features.jpg" alt="Sockets, ambient probe and mounting" width="32%">
  <img src="https://raw.githubusercontent.com/phoinixgrr/thermogatz_ha/main/images/product-assembly.jpg" alt="Probe sockets 1 to 4 and the ambient probe stem" width="32%">
</p>

That is also how the integration maps it: sockets 1 to 4 become `Probe 1` to `Probe 4`, the stem probe becomes `Ambient`.
Product photos are the manufacturer's, shown only to identify the device.

The vendor protocol is undocumented. It was reverse-engineered from the Android app and is written up in
[docs/protocol.md](docs/protocol.md), with the method in [docs/reverse-engineering.md](docs/reverse-engineering.md).

## What it does

- Finds the thermometer by itself and offers it under *Discovered*
- Keeps a Bluetooth connection open and updates once a second
- Four probe temperatures and the ambient (grill) temperature, each unavailable while nothing is plugged in
- Battery level
- Works through any Bluetooth adapter or [ESPHome Bluetooth proxy](https://esphome.io/components/bluetooth_proxy/)
  that Home Assistant uses
- Reconnects by itself, with exponential backoff, if the link drops or the thermometer goes out of range

## Requirements

- A Thermogatz AT-02 (BLE name `AT-02`). Other models of the same OEM family (`AT-01`, `AT-03`, `Pro-05`, ...) are
  not supported and untested
- Home Assistant with a working [Bluetooth integration](https://www.home-assistant.io/integrations/bluetooth/)
  within range of the thermometer. Active connections are needed, so a proxy has to allow them (an ESPHome proxy
  needs `bluetooth_proxy: active: true`)

## Installation

HACS: add `https://github.com/phoinixgrr/thermogatz_ha` as a custom repository (category Integration), install
**Thermogatz BBQ Thermometer**, restart.

Manual: copy `custom_components/thermogatz/` to your `custom_components/` and restart.

## Setup

Switch the thermometer on and close the phone app. Home Assistant shows the device under **Settings > Devices &
services > Discovered**, then click **Add**. If it does not show up, use **Add integration > Thermogatz BBQ Thermometer**,
which lists every AT-02 Home Assistant can currently see.

<img src="https://raw.githubusercontent.com/phoinixgrr/thermogatz_ha/main/images/add.png" alt="Discovered thermometer ready to add" width="640">

> **One connection at a time.** The thermometer talks to a single Bluetooth client. While Home Assistant is
> connected, the phone app cannot connect, and the other way round. To use the app, disable the integration entry
> (**Settings > Devices & services > Thermogatz > ... > Disable**) and enable it again afterwards.

## Entities

For a device called `AT-02 5F3E` (the last four digits of its address):

| Entity | Unit | |
|---|---|---|
| `sensor.at_02_5f3e_probe_1` ... `probe_4` | °C | unavailable while nothing is plugged into that socket |
| `sensor.at_02_5f3e_ambient` | °C | the grill (ambient) probe |
| `sensor.at_02_5f3e_battery` | % | diagnostic |

Temperatures are always Celsius. Home Assistant converts them to your unit system. If the thermometer is set to
Fahrenheit, the integration switches it back to Celsius when it connects.

## Automations

Replace the entity ids and `notify.notify` with yours.

### Meat is done

```yaml
- alias: BBQ probe 1 reached 74 C
  triggers:
    - trigger: numeric_state
      entity_id: sensor.at_02_5f3e_probe_1
      above: 74
  actions:
    - action: notify.notify
      data:
        title: BBQ
        message: "Probe 1 is at {{ states('sensor.at_02_5f3e_probe_1') }} °C"
```

### Grill too hot

```yaml
- alias: BBQ grill too hot
  triggers:
    - trigger: numeric_state
      entity_id: sensor.at_02_5f3e_ambient
      above: 280
      for: "00:01:00"
  actions:
    - action: notify.notify
      data:
        message: "Grill is at {{ states('sensor.at_02_5f3e_ambient') }} °C"
```

### Thermometer lost

Probes go unavailable when the link drops. An unplugged probe does too, so watch the battery sensor, which is
only available while connected.

```yaml
- alias: BBQ thermometer disconnected
  triggers:
    - trigger: state
      entity_id: sensor.at_02_5f3e_battery
      to: unavailable
      for: "00:03:00"
  actions:
    - action: notify.notify
      data:
        message: "The BBQ thermometer lost its Bluetooth link"
```

## How it works

The AT-02 advertises as `AT-02` with the vendor service `0xCEE0`. After connecting, the integration subscribes to the
notify characteristic `0xCEE2` and writes two requests to `0xCEE1`: status (`A0`) and "send temperatures" (`A1`).
The thermometer then sends one 20-byte frame per second with seven 16-bit slots in tenths of a degree: four probe
sockets, two spare probe slots, and the ambient probe. There is no pairing and no encryption.

```
55 AA 00 0F A1 | ff ff  ff ff  ff ff  05 50  ff ff  ff ff  00 bc | 04
                 p1     p2     p3     p4     p5     p6     amb      xor
                                      136.0 °C                   18.8 °C
```

| What | Value |
|---|---|
| Service | `0000cee0-0000-1000-8000-00805f9b34fb` |
| Command (write without response) | `0000cee1-0000-1000-8000-00805f9b34fb` |
| Data (notify) | `0000cee2-0000-1000-8000-00805f9b34fb` |
| Frame | `55 AA 00 <len> <cmd> <payload> <xor>` |
| Probe 1 to 4 | frame bytes 5-6, 7-8, 9-10, 11-12 |
| Ambient | frame bytes 17-18 |
| Battery | `A0` reply, byte 5, percent |
| Not connected | `ffff` |

Full details, the decoded fields and what is still unknown: [docs/protocol.md](docs/protocol.md).

### How it was found

The vendor app was pulled from a phone with `adb`, decompiled with [jadx](https://github.com/skylot/jadx), and the
UUIDs, the start-up sequence and the notification parser were read from it. Everything was then replayed against a
real thermometer from a Mac with [bleak](https://github.com/hbldh/bleak) ([`tools/probe.py`](tools/probe.py)) and
compared with the numbers on the phone. The walkthrough is in
[docs/reverse-engineering.md](docs/reverse-engineering.md).

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Not discovered | the phone app (or something else) is connected, the thermometer is off, or no active Bluetooth proxy is in range |
| Everything unavailable | the link dropped. It retries on its own with backoff up to 60 s. Check that nothing else is connected |
| A probe is unavailable | nothing is plugged into that socket, or the probe is damaged (the thermometer reports it as not connected) |
| Battery unavailable | only while the link is down or just after connecting. It asks again every 10 s until the thermometer answers |

For a bug report, run `python3 tools/probe.py 30` with the integration disabled and attach the output, and enable
debug logging:

```yaml
logger:
  logs:
    custom_components.thermogatz: debug
```

## Development

```sh
pip install -r requirements_test.txt
pytest
```

Protocol parsing and the connection handling are covered by tests that use frames captured from a real device. The
Bluetooth link itself is only exercised against a real thermometer.

## Disclaimer

This is an independent project, not affiliated with, endorsed by, or supported by Thermogatz or Haibosi. The
names are used only to say which device it works with. The logo is a neutral drawing, not the vendor's. The
protocol was worked out for interoperability with a device the author owns, and no vendor code, assets or app
packages are included here.

## License

[AGPL-3.0](LICENSE)
