# How the protocol was found

The vendor does not publish the protocol, so it was read from their Android app and confirmed on a real thermometer.
This is the procedure, in case you want to check it, extend it, or do the same for another device.

Only protocol facts are written down in this repository. No app code, assets or APK are redistributed.

## 1. Find out what the device is

The app is "ThermoGatz" (package `com.togrill.haibosi`, version 10.8), a generic app of the OEM Haibosi that serves
dozens of thermometer models. The thermometer shows up as `AT-02`.

Home Assistant already tells you a lot, with no tools: *Settings > Devices & services > Bluetooth > (an adapter or proxy) > Download diagnostics* of the
Bluetooth integration lists every advertisement a proxy has heard, with the name, service UUIDs and manufacturer
data (see [protocol.md](protocol.md#advertisement)). Note that a connected device stops advertising, so the phone
app must be closed first.

## 2. Get the app from the phone

```sh
adb shell pm list packages | grep -i -E "thermo|gatz|bbq"
adb shell pm path com.togrill.haibosi          # base.apk plus split_config.*.apk
adb pull <path>/base.apk
adb shell dumpsys bluetooth_manager | grep -B1 -A1 AT-02     # name, bond state, LE
```

`dumpsys` also shows when the app connects and disconnects, and that the device is LE-only.

Do this in a fresh directory and treat the APK as untrusted data: do not run scripts from inside it.

## 3. Decompile

```sh
brew install jadx
jadx -q -j 6 --no-res -d out base.apk       # about 19000 classes, a few minutes
```

The app is native Java (not Flutter or React Native), so jadx gives readable code. It also bundles a Tuya SDK
(`com.thingclips`) for the WiFi products. The AT-02 does not use it.

## 4. Find the UUIDs

```sh
grep -rhoE '"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"' out/sources/com | sort | uniq -c | sort -rn
```

Most hits belong to the Tuya SDK (`fd50`, `fff6`, the `00010203-...` family). The ones in the vendor's own package
are `0000cee0`, `cee1` and `cee2`:

- `com/togrill/haibosi/bbq/tools/BluetoothManage.java`: `cee0`/`cee1` for writes, and the scan filter, which is a
  list of device names (`"AT-01", "AT-02", "Pro-05", ...`) matched against the advertised name
- `com/clj/fastble/BleManager.java` (the FastBle library): `cee0`/`cee2` for notifications

## 5. Find the framing and the commands

`HomeDeviceListActivity` holds the code that runs after the connection is up and the code that parses what comes
back:

- The runnable around line 530 is the **start-up sequence**: write `A0`, wait, write `A1`, wait 300 ms, write `A8`.
  Every request is built as `{0x55, 0xAA, 0x00, len, cmd, ...}` and ends with `ByteUtils.f(array)`, which is an XOR
  over the array (the checksum slot still being zero).
- Method `Y(DeviceBean, byte[])` is the **notification parser**. It checks `b[0] == 0x55 && b[1] == 0xAA` and
  switches on `b[4]`: `0xA0` status (battery `b[5]`, firmware `b[6].b[7]`, unit `b[8]`), `0xA1` temperatures,
  `0xA5` alarms, `0xA9` gas gauge reports, and so on.
- For `0xA1`, the code reads two bytes per probe at `b[5..6]`, `b[7..8]`, ... and hands them to `ProbeBean.N(byte[])`,
  which treats `ffff` as "not connected", `efff` and `f000` as range errors, and values above `0x8000` as negative.
  Probe 0, the ambient probe, is read from `b[17..18]`.
- `CommonUtil.C(int)` shows the unit of the number: it converts with `(i * 1.8 + 320) / 10`, so the raw value is
  tenths of a degree Celsius.

Two things are easy to get wrong while reading it: the file is huge and obfuscated (names like `Y`, `bArr11`), and
some branches are for other models (`ATK-02`, gas readers, ovens). Follow `deviceBean.g().equals("AT-02")`.

## 6. Check it against the device

Static reading is not enough, so replay it. The thermometer accepts a single connection, so close the app (or turn
the phone's Bluetooth off) and disable the Home Assistant entry, then:

```sh
pip install bleak
python3 tools/probe.py 30
```

First experiment, subscribing to `cee2` and doing nothing: silence for 40 seconds. The device only talks when asked.
Writing `A0` returned the status frame within 100 ms, and writing `A1` started the one-per-second stream. Battery
(68 %) and the first temperature (136.0 °C, probe 4) matched the phone screenshot taken minutes earlier.

Unplugging the probe changed slot 4 to `ffff`, and plugging the ambient probe moved a value into slot 7, which fixed
the last open question (where the ambient temperature is).

## 7. Things worth knowing

- Home Assistant only delivers an advertisement to a callback when its content changed. A thermometer that
  re-sends an identical packet never triggers it again, so reconnecting cannot rely on advertisements. The
  integration runs its own retry loop with exponential backoff.
- An ESPHome Bluetooth proxy connects fine, because the AT-02 needs no pairing. If you want to watch the traffic of the
  real app instead of replaying it, enable *Bluetooth HCI snoop log* in Android developer options, toggle
  Bluetooth, use the app, then pull the log with `adb bugreport` and open it in Wireshark.
- Legal note: this is interoperability work on a device the author owns. It is not affiliated with or endorsed by
  Thermogatz or Haibosi.
