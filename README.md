# Speedlink Controller Reverse-Engineering (dongle lost)

Reverse-engineering a **Speedlink 2.4 GHz wireless gamepad** (main chip **nRF51822**)
whose USB dongle was lost. Work done 2026-10-30 → 2026-11-01.

**This is the master document.** Deeper technical references:
- `PAIRING_PROTOCOL.md` — **the working dongle replacement**: pairing handshake, channel
  hopping, firmware patches, the Nano host, and the debugging journey (day 3).
- `FIRMWARE_ANALYSIS.md` — firmware RE details (memory map, functions, no-crypto proof).
- `FIRMWARE_FUNCTIONS.md` — **all 255 firmware functions** with suggested names, evidence and
  confidence. Also covers boot/main loop, subsystems, the hidden RF test mode and a bond-wipe risk for the locked image.
- `SWD_DUMP.md` — SWD solder points + non-destructive flash-dump procedure.
- `RF_SNIFFING.md` — the first RF phase: wiring, flashing, sketches, captures (with notes
  on what it got wrong).
- `ble_gamepad/README.md` — the BLE HID gamepad firmware (build/flash/status).
- `RESEARCH.md` — prior-art and external reference links.
- `LEARNING_GUIDE.md` — how to learn the skills used here (foundations, tools, practice path, exercises).

---

## What we achieved

1. **First RF sniffing phase** (nRF24L01+PA+LNA on an Arduino Nano). It found Gazell/ESB-style
   traffic but **got the link parameters wrong** (2 Mbps, `01 02 76`). See
   "RF link" below.
2. **Firmware dumped** over SWD (readback protection bypassed non-destructively) and
   **reversed in Ghidra** → proved **no encryption, no key**.
3. **Chip unlocked** (mass-erase) and **reprogrammed**; **every button + stick read live
   over SWD**.
4. **BLE stack brought up** on the controller (pairs with a PC/Mac as a HID gamepad) —
   one motor-buzz blocker remains (see `ble_gamepad/`).
5. **Dongle replaced by the Nano (day 3).** We decoded Speedlink's app-level pairing
   protocol, patched 14 bytes of the stock firmware to lock it to our host ID `ABCDEF`
   and pin channel 32, and wrote `arduino/nrf24_host`. The controller now streams input
   reports wirelessly to the Nano at **~180 reports/s**. Details in `PAIRING_PROTOCOL.md`.

**Current state of the controller:** running the **locked** image
`prebuilt_hex/speedlink_locked_ABCDEF.bin`. It only pairs with the Nano host. See
"Restore to stock" below to undo.

---

## RF link (verified on day 3 from the live radio registers)

| Item | Value |
|---|---|
| Protocol | Old Nordic **Gazell** link layer + Speedlink's own pairing handshake and channel hopping on top |
| Data rate | **250 kbps** |
| Packet | ESB-compatible, 5-byte address, CRC-16 poly `0x1021` init `0xFFFF` |
| Pairing address | prefix `E7` + base `0xC1C2C6` → nRF24 `0xC6C2C1E7E7` |
| Channel | stock: pseudo-random hop every packet (LFSR, ch 2..80); **patched: fixed 32** |
| Crypto | **none**: there is no key (the early "AES-128 pairing" theory was wrong) |

Pairing is a 3-step handshake (pair → confirm → stream), each on its own address. The
host's replies ride in ESB ack payloads. Full spec, patches and host design are in
`PAIRING_PROTOCOL.md`.

**What the first RF phase believed (kept for the record):** 2 Mbps, 3-byte address
`01 02 76`, channel 32 + a hop table, and "the controller beacons `E9 74 03 80 …` (18 B)
+ `5A` (1 B) until a Gazell host syncs, which the Nano can't do". Day 3 disproved the
link parameters (the controller transmits at 250 kbps only) and the "Nano can't" conclusion:
every host reply is static, so the nRF24 can preload it as an ack payload. Also, a stock
Gazell host would **not** have paired out of the box, because the handshake and hopping are
Speedlink-specific. The origin of the 2 Mbps `01 02 76` traffic is still unexplained
(`PAIRING_PROTOCOL.md` §7).

---

## Hardware / SWD

- **Chip:** `N51822 QFACA1` = **nRF51822 QFAC**, QFN48, 256 KB flash / 32 KB RAM,
  Cortex-M0. Device ID `45D963F4 C3CF04FB`.
- **SWD:** ST-Link V2 clone, 4 wires (SWDIO, SWDCLK, GND, 3.3 V). Solder points in
  `SWD_DUMP.md` + `hardware/` photos. **Run pyocd at `-f 400k`** — the hand-soldered
  link is flaky at higher speeds; reseat wires / replug the ST-Link on "Target not
  detected". A soldered header would make this far more reliable. **For full-chip
  flashing use `-f 100k -e chip`**: on day 3 a 400 kHz flash timed out mid-erase.
- **Live monitoring over SWD** must attach **without halting**
  (`connect_mode="attach"`). pyocd's default connect halts the core, which silences the radio.
- **Sniffer / dongle replacement:** nRF24L01+PA+LNA on an Arduino Nano — note it's actually an
  **ATmega168** (bootloader @ **19200 baud**, flash with `cpu=atmega168 -b 19200`).
  Wiring + sketch details are in `RF_SNIFFING.md` and the sketch headers.
- USB (ST-Link, CH340) was not visible from Claude Code's sandbox. Run flash/serial
  commands in your own shell (`! <cmd>` in Claude Code).

---

## Reading the buttons & sticks (works today)

The stock firmware decodes every input into RAM; we poll it over SWD. The ⚠️ mux that
blocked our *custom* firmware is handled for free by the controller's own code.

Run with the pyocd venv and the ST-Link connected. This works with the stock or the locked
image, since the patches don't touch input decoding:
```
<venv>/bin/python tools/mapper_gui.py      # GUI: press controls, name them -> button_map.json
<venv>/bin/python tools/live_report.py     # plain live readout
```

**Input architecture / RAM map (stock firmware):**

| What | Where / how |
|---|---|
| Direct-GPIO buttons | word `0x2000002c`, bit set = pressed |
| All buttons, debounced | word `0x20000034`: direct + mux + trigger bits, bit set = pressed (full map in `FIRMWARE_FUNCTIONS.md` §3) |
| Stick axes | 6 × u16 LE at `0x2000003c..0x47`; value **0..255 in the low byte, rest 128** |

- Direct bits: `0x8`=P0.21(Start) `0x1`=P0.23(Back) `0x4`=P0.28 `0x2`=P0.29
  `0x20000`=P0.15 `0x400000`=P0.14 `0x800000`=P0.10(X/D switch) `0x10000`=P0.22.
  **P0.00 (`0x100000`) reads stuck-low and is not a button.** The firmware debounces it separately
  and uses it to choose deep sleep or latch-off at power-down, so it's probably a charger/USB-detect line
  (low–med confidence, see `FIRMWARE_FUNCTIONS.md`).
- Button bits in `0x20000034` (from the code; matches `button_map.json`): `0x10` Up, `0x20` Right,
  `0x40` Down, `0x80` Left, `0x1000` Y, `0x2000` B, `0x4000` A, `0x8000` X, `0x100`/`0x200` L2/R2,
  `0x400`/`0x800` L1/R1, `0x10000` Home. The labels "ch4…ch7" used by the mapper tools are just
  bit names. The real HC4051 channels are ch4 = A, ch5 = B, ch6 = X, ch7 = Y.
- Sticks are 2 analog sticks on **AIN4..7 = P0.03..P0.06** (ADC side, per `FUN_00003f80`).
  Measured with `tools/stick_probe.py` (2026-11-01):
  - **v0 = left stick X** (left 0 / right 255), **v1 = left stick Y** (up 0 / down 255).
  - **v4/v5 also follow the left stick** (X/Y, ~1..255). They're slow to return: v4 stayed at 137 after a push.
  - **v2/v3 did not move**, and **the right stick and both triggers changed none of the six
    values** in that test. The code explains it (`FIRMWARE_FUNCTIONS.md` §3). In D mode a digital
    sub-mode (default on, **Home toggles it**) maps the right stick onto face buttons and forces
    v2/v3 = 128. The triggers are stored elsewhere (`0x200001ee/ef` + button bits `0x100/0x200`).
    v4/v5 are an idle-timer snapshot, not live axes. Not yet re-tested with Home toggled.
  - Reads can land **mid-update**: a word briefly reads `0x8000`. The stick scan writes 16-bit values
    (centre `0x8000`) and the report builder shifts them `>>8` in place, so SWD sometimes catches the
    gap. The tools only accept two identical consecutive reads.
  - Earlier versions of this doc / the tools described the area as "8 direction bytes, rest 0"
    (`mapper_gui.py`) or "4× u16, centre `0x8000`" (`live_report.py`, `map_buttons.py`). Both
    were wrong and are fixed. The `stk1/3/5/7` entries in `button_map.json` (high bytes) were most
    likely triggered by those mid-update reads, so re-map the sticks with the fixed GUI (`ax<i>±`).
- The mux is driven by selects **P0.09 / P0.10 / P0.11**, output on **AIN0 = P0.26**.
  Note P0.10 is time-shared as both select-S1 and the X/D switch (why our static custom
  firmware couldn't switch the mux but the stock firmware can).

(SWD memory reads are exact. Once mid-update reads are filtered, the sticks read rock-steady at
rest: 300 samples over 4 s gave offset 0 on all six axes.)

---

## Going wireless again

- **Original 2.4 GHz radio + Nano dongle (working, day 3):** flash the locked image to the
  controller and `arduino/nrf24_host` to the Nano → input reports over serial. Still to
  do: the full report button map, and a PC bridge (serial → virtual gamepad), since the
  ATmega168 Nano can't be a USB HID device. See `PAIRING_PROTOCOL.md`.
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
  - `stick_probe.py` — guided per-direction stick/trigger probe (which axis moves how).
  - RF-phase scripts: `decode_ch32.py` (recovered the 2 Mbps `01 02 76` address, which
    turned out not to be the pairing link), `broad_decode.py`, `aggscan.py`, `sweep.py`,
    `sustain.py`, `readserial.py`.
  - Dongle-replacement phase: `make_locked_rom.py` (builds the patched image),
    `radio_state.py` (live radio registers → nRF24 settings), `peek_pairing.py` (live
    handshake state), `pairlog.py` (drives `nrf24_pair`).
- `arduino/` — nRF24 sketches: sniffers/receivers from the RF phase, `nrf24_pair` (generic
  test harness: address/rate/ack-payload commands) and **`nrf24_host` (the dongle
  replacement)**.
- `prebuilt_hex/` — prebuilt Nano sketches + `speedlink_locked_ABCDEF.bin` (patched
  controller image).
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
pyocd flash -t nrf51 -f 100k -e chip --base-address 0x0 \
   firmware_dump/0x00000000_0x00040000_ROM.bin
```
(Stock firmware hops channels and accepts any host again. The Nano host only works with
the locked image.)
The chip stays SWD-unlocked (APPROTECT not re-enabled), so you can reflash anytime.

⚠️ **Motor safety:** the vibration-motor driver engages when control pins float/pull-up.
Keep pins driven low. `custom_fw/safe_hold.bin` guarantees the motor off — flash it if
anything ever buzzes.
