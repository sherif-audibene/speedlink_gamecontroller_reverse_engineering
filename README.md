# Speedlink Controller Reverse-Engineering (dongle lost)

Reverse-engineering a **Speedlink 2.4 GHz wireless gamepad** (main chip **nRF51822**)
whose USB dongle was lost. Work done 2026-10-30 / 2026-10-31.

**This is the master document.** Deeper technical references:
- `FIRMWARE_ANALYSIS.md` — firmware RE details (memory map, functions, no-crypto proof).
- `SWD_DUMP.md` — SWD solder points + non-destructive flash-dump procedure.
- `RF_SNIFFING.md` — RF phase: wiring, flashing, sketches, captures, decode reproduction.
- `ble_gamepad/README.md` — the BLE HID gamepad firmware (build/flash/status).
- `RESEARCH.md` — prior-art and external reference links.

---

## What we achieved

1. **RF fully reverse-engineered** (nRF24L01+PA+LNA sniffer on an Arduino Nano).
2. **Firmware dumped** over SWD (readback protection bypassed non-destructively) and
   **reversed in Ghidra** → proved **no encryption, stock Gazell**.
3. **Chip unlocked** (mass-erase) and **reprogrammed**; **every button + stick read live
   over SWD** — this is the working way to read the controller today.
4. **BLE stack brought up** on the controller (pairs with a PC/Mac as a HID gamepad) —
   one motor-buzz blocker remains (see `ble_gamepad/`).
5. **Controller restored to stock** at session end (works normally).

---

## RF parameters (confirmed on-air)

| Item | Value |
|---|---|
| Protocol | Nordic ESB / **Gazell** (stock, default params) |
| Data rate | **2 Mbps** |
| Address | **01 02 76** (3-byte) |
| CRC | 16-bit, poly `0x1021`, init `0xFFFF` |
| Channel | **32 (2432 MHz)**, hops a table incl. ~23,29,31,47,48,59,61,63,65 |
| Gazell defaults | base0 `E7E7E7E7`, base1 `C2C2C2C2`, prefixes `E7 C2..C8` |

The controller beacons two input-independent packets until a host syncs (~every 1.5 s):
- 18-byte: `E9 74 03 80 00 48 00 00 00 00 DB 01 00 00 00 00 04 45`
  (contiguous `E9740380004800000000DB01000000000445`)
- 1-byte poll: `5A`

(How these were captured/decoded, plus the Nano wiring/flashing and sketches, is in
`RF_SNIFFING.md`.)

**No input is sent until Gazell link-layer sync completes.** The Nano+nRF24 **cannot**
perform Gazell host-sync (hard real-time MAC), so emulating the lost dongle on the Nano
is not viable. **There is no key and no crypto** — the early "AES-128 encrypted pairing"
theory was wrong (disproved by the firmware dump). A ~$5 nRF5x running Nordic's stock
Gazell host would pair out-of-box; we instead read inputs directly over SWD.

---

## Hardware / SWD

- **Chip:** `N51822 QFACA1` = **nRF51822 QFAC**, QFN48, 256 KB flash / 32 KB RAM,
  Cortex-M0. Device ID `45D963F4 C3CF04FB`.
- **SWD:** ST-Link V2 clone, 4 wires (SWDIO, SWDCLK, GND, 3.3 V). Solder points in
  `SWD_DUMP.md` + `hardware/` photos. **Run pyocd at `-f 400k`** — the hand-soldered
  link is flaky at higher speeds; reseat wires / replug the ST-Link on "Target not
  detected". A soldered header would make this far more reliable.
- **Sniffer (RF phase):** nRF24L01+PA+LNA on an Arduino Nano — note it's actually an
  **ATmega168** (bootloader @ **19200 baud**, flash with `cpu=atmega168 -b 19200`).
  Wiring + sketch details are in `arduino/` and the sketch headers.

---

## Reading the buttons & sticks (works today)

The stock firmware decodes every input into RAM; we poll it over SWD. The ⚠️ mux that
blocked our *custom* firmware is handled for free by the controller's own code.

Run with the pyocd venv and the ST-Link connected:
```
<venv>/bin/python tools/mapper_gui.py      # GUI: press controls, name them -> button_map.json
<venv>/bin/python tools/live_report.py     # plain live readout
```

**Input architecture / RAM map (stock firmware):**

| What | Where / how |
|---|---|
| Direct-GPIO buttons | word `0x2000002c`, bit set = pressed |
| Mux buttons (HC4051) | word `0x20000034` (low 16 bits), bit set = pressed |
| Stick directions | 8 bytes `0x2000003c..0x20000043`, **rest 0, full push 255** |

- Direct bits: `0x8`=P0.21(Start) `0x1`=P0.23(Back) `0x4`=P0.28 `0x2`=P0.29
  `0x20000`=P0.15 `0x400000`=P0.14 `0x800000`=P0.10(X/D switch) `0x10000`=P0.22.
  **P0.00 (`0x100000`) reads stuck-low — ignore, not a button.**
- Mux bits: `0x10`=ch0 `0x80`=ch1 `0x40`=ch2 `0x20`=ch3 `0x1000`=ch4 `0x2000`=ch5
  `0x4000`=ch6 `0x8000`=ch7 (face buttons / d-pad / shoulders).
- Sticks are 2 analog sticks on **AIN4..7 = P0.03..P0.06** (8 direction bytes).
- The mux is driven by selects **P0.09 / P0.10 / P0.11**, output on **AIN0 = P0.26**.
  Note P0.10 is time-shared as both select-S1 and the X/D switch (why our static custom
  firmware couldn't switch the mux but the stock firmware can).

(SWD memory reads are exact — verified the stick rest jitter is 0; any noise would be
real analog, not our reads.)

---

## Going wireless again

- **PC / Mac / phone:** reflash the nRF51822 as a **BLE HID gamepad** — see
  `ble_gamepad/`. BLE is confirmed working; a vibration-motor buzz while connected is the
  one open blocker (documented there with the diagnostics and the likely fix).
- **PlayStation:** not possible on this chip — PS uses Bluetooth *Classic* + Sony auth;
  the nRF51 is BLE-only. (A USB bridge via an ESP32-S3 would be the PS path.)

---

## Repository map

- `firmware_dump/` — original firmware + FICR/UICR/RAM dumps (restore source).
- `tools/` — PC-side Python (run with a pyocd venv):
  - `mapper_gui.py` — tkinter GUI control-mapper → `button_map.json`.
  - `live_report.py` — live button/stick readout over SWD.
  - `map_buttons.py` — CLI interactive mapper.
  - `diag_sticks.py`, `diag_rest.py` — stick-location / rest-jitter diagnostics.
  - RF-phase scripts: `decode_ch32.py` (cracked the address), `broad_decode.py`,
    `aggscan.py`, `pairlog.py`, `sweep.py`, `sustain.py`, `readserial.py`.
- `arduino/` — nRF24 sniffer/receiver/pairing sketches (RF phase).
- `custom_fw/` — bare-metal nRF51 test firmware (Homebrew arm-none-eabi-gcc):
  `safe_hold` (all pins low — flash if it ever buzzes), scan experiments,
  `diag_float/direct/sel/combo` (BLE-phase motor-trigger isolation tests).
- `ble_gamepad/` — BLE HID gamepad firmware + S130 SoftDevice + build/flash README.
- `captures/`, `hardware/` — RF captures and annotated board photos.
- `button_map.json` — control-name → signal map from the GUI mapper.

### Build / flash quick reference
- **Bare-metal custom_fw:** `arm-none-eabi-gcc -mcpu=cortex-m0 -mthumb -nostdlib
  -nostartfiles -ffreestanding -Os -T custom_fw/nrf51.ld X.c -o X.elf && objcopy -O
  binary X.elf X.bin` ; `pyocd flash -t nrf51 -f 400k --base-address 0x0 X.bin`.
  (Homebrew gcc has no C library — fine for bare-metal, not for the SDK.)
- **BLE firmware:** needs nRF5 SDK 12.3 + Arm gcc 10.3 (newlib) — see `ble_gamepad/README.md`.

### Restore to stock (undo everything)
```
pyocd flash -t nrf51 -f 400k -e chip --base-address 0x0 \
   firmware_dump/0x00000000_0x00040000_ROM.bin
```
The chip stays SWD-unlocked (APPROTECT not re-enabled), so you can reflash anytime.

⚠️ **Motor safety:** the vibration-motor driver engages when control pins float/pull-up.
Keep pins driven low. `custom_fw/safe_hold.bin` guarantees the motor off — flash it if
anything ever buzzes.
