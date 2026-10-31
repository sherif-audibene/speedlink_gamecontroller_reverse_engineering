# Speedlink Controller Reverse-Engineering (dongle lost)

Reverse-engineering a Speedlink 2.4 GHz wireless gamepad (main chip **nRF51822**)
whose USB dongle was lost, using an **nRF24L01+PA+LNA** module on an **Arduino Nano**.
Goal: sniff the controller and eventually re-create a receiver/dongle.

Work done 2026-10-30 / 2026-10-31.

---

## TL;DR status

| Item | Result |
|---|---|
| Protocol | Nordic ESB / **Gazell** (shares radio PHY with nRF24L01+) |
| Data rate | **2 Mbps** |
| Address | **01 02 76** (3-byte ESB address) |
| CRC | 16-bit, poly `0x1021`, init `0xFFFF` |
| Channel | **32 (2432 MHz)**; hops a custom table (energy also on ~23,29,31,47,48,59,61,63,65) |
| Can we receive its packets? | **Yes** (clean, CRC-valid) |
| Can we ACK it? | **Yes** — acking keeps the controller awake, but only ever elicits the `5A` poll |
| Pairing protocol | **Stock Nordic Gazell, NO encryption** (proven by dumping + reversing the firmware — see below). Earlier "AES-128 encrypted pairing" guess was WRONG. |
| Dongle emulation on the Nano? | **No** — Gazell host-sync is a hard real-time radio MAC the nRF24+ATmega can't perform. (A ~$5 nRF5x running Nordic's stock Gazell host would pair out-of-box.) |
| Can we read buttons/sticks? | **YES** — not over the Nano radio, but by **reprogramming the controller's nRF51822 over SWD** and reading its decoded state. All buttons + sticks confirmed. See `STATUS.md`. |

> **This README covers the first (RF-sniffing) phase.** The project went much further:
> dumped the firmware, unlocked the chip, read every input over SWD, and even got a
> BLE stack running on the controller. **Read `STATUS.md` for the full, current story**
> and the repository map. The Gazell/AES conclusions in the old "The wall" section
> below are superseded by `FIRMWARE_ANALYSIS.md` (no crypto, stock Gazell).

### The two packets the controller sends (unpaired, forever, ~every 1.5 s)
- 18-byte "request/announce": `E9 74 03 80 00 48 00 00 00 00 DB 01 00 00 00 00 04 45` (constant)
- 1-byte "fetch": `5A`

Neither changes with buttons/sticks → the controller is only beaconing for a host.

---

## Hardware

- **Board:** grey-clone "Arduino Nano" — actually an **ATmega168** (sig `1E 94 06`), 14 KB flash / 1 KB RAM. CH340 USB (VID 1a86 / PID 7523).
- **Radio:** nRF24L01+PA+LNA (SMA antenna) on the HW-200 breakout adapter.

### Wiring (adapter label → Nano pin)
| Adapter | Nano | | Adapter | Nano |
|---|---|---|---|---|
| VCC | **5V** (adapter regulates to 3.3V) | | MO (MOSI) | D11 |
| GND | GND | | MI (MISO) | D12 |
| CE | D9 | | SCK | D13 |
| CSN | D10 | | IRQ | (unused) |

All sketches use SPI @ 4 MHz (reliable over dupont wires to a PA+LNA module; 10 MHz default fails).

---

## Flashing (this specific clone) — IMPORTANT

Standard `arduino:avr:nano` **fails** ("not in sync") because it's a 168, not a 328,
and its bootloader runs at **19200 baud**. Use:

```bash
# compile for ATmega168
arduino-cli compile --fqbn arduino:avr:nano:cpu=atmega168 --output-dir BUILD arduino/<sketch>

# upload (find port with: ls /dev/cu.wchusbserial* /dev/cu.usbserial*)
AV=~/Library/Arduino15/packages/arduino/tools/avrdude/8.0.0-arduino1/bin/avrdude
CONF=~/Library/Arduino15/packages/arduino/tools/avrdude/8.0.0-arduino1/etc/avrdude.conf
"$AV" -C "$CONF" -c arduino -p atmega168 -P /dev/cu.usbserial-XXXX -b 19200 -D \
   -U flash:w:BUILD/<sketch>.ino.hex:i
```

macOS note: a sandbox can hide `/dev/cu.*` from shell globbing; use `/bin/ls /dev/cu.*`
or pyserial to enumerate. The port sometimes re-enumerates as `usbserial-1110` vs
`wchusbserial1110` — both are the same device.

Python tools need pyserial: `python3 -m venv venv && ./venv/bin/pip install pyserial`.

---

## Arduino sketches (`arduino/`)

| Sketch | Purpose |
|---|---|
| `nrf24_diag` | Raw SPI connectivity test (reads CONFIG, write/readback). Use if "radio not found". |
| `nrf24_rpd` | Fast channel-activity scanner (RPD/carrier). Finds which channels are busy. |
| `nrf24_scanner` | Promiscuous sniffer (2-byte-address trick). Last configured: park on ch32 @ 2M. |
| `nrf24_addr` | Tries common ESB default addresses with CRC on (all missed — address is custom). |
| `nrf24_rx` | Proper ESB receiver on addr 010276, auto-ack ON. First showed the `5A` packet. |
| `nrf24_pair` | **Pairing harness v2.** PRX on 010276, configurable ack payload via serial. Main tool for handshake attempts. Serial cmds: `K<hex>` ack payload, `KA/KF<hex>` per-packet, `C<n>` channel, `D<hex>` 2nd data addr, `P` print cfg, `Z` reset counters. |

---

## Host tools (`tools/`, run with the venv python)

| Script | What it does |
|---|---|
| `readserial.py [sec]` | Dump raw serial lines. |
| `aggscan.py [sec] [label]` | Aggregate `nrf24_rpd` output into a per-channel activity histogram (saves `<label>.json`). |
| `decode_ch32.py [sec] [label]` | Capture promiscuous `nrf24_scanner` output and CRC-recover packets for address **010276** (the decoder that cracked it). |
| `broad_decode.py [sec]` | Same but recovers ANY address (3/4/5-byte) — finds other packet types. |
| `pairlog.py [sec] [cmds...]` | With `nrf24_pair`: log the handshake sequence with timestamps. Extra args are serial cmds, e.g. `pairlog.py 15 "KAABBCCDDEE"`. |
| `sweep.py` | Sweep a list of candidate ack payloads, report any NEW packet types. |
| `sustain.py [ackhex] [sec]` | Sustained acking with one payload while you press buttons; watch for new packets/input. |

### Reproduce the key decode
```bash
# flash nrf24_scanner (currently parks on ch32 @ 2M), controller ON near antenna, then:
./venv/bin/python tools/decode_ch32.py 20 test
# -> recovers addr 010276, 18-byte payload E9740380004800000000DB01000000000445
```

---

## Captures (`captures/`)
- `cap.txt` — first broad hopping capture (2M+1M, all channels).
- `cap1m_on.txt` — parked hot-channels @1M, controller on (showed smeared = wrong rate).
- `ch32_2m.txt` — ch32 @ 2M, controller on — **the clean capture that gave address + payload**.
- `baseline_off.json`, `near.json` — RPD channel-activity histograms (controller off vs near).

---

## What was behind the wall (RESOLVED — the AES theory was wrong)

We dumped the controller's nRF51822 flash over SWD (readback protection bypassed
non-destructively with `nrfsec`) and reversed it in Ghidra. Findings:

- **No encryption anywhere** — no AES, no key, no crypto gate. The earlier "AES-128
  encrypted pairing" guess in this README was **incorrect**.
- It's **100% stock Nordic Gazell with default parameters**. "Pairing" is just the
  Gazell link-layer timeslot sync.
- The Nano+nRF24 **cannot** perform Gazell host-sync (hard real-time MAC) — so
  emulating the lost dongle on the Nano is not viable regardless.

Details in `FIRMWARE_ANALYSIS.md`; the SWD dump procedure in `SWD_KEY_EXTRACTION.md`
(note: it extracts the *firmware*, not a key — there is none).

### How we actually read the inputs (works today)
Reprogrammed the controller over SWD and read its decoded button/stick state out of
RAM. **All buttons + sticks confirmed.** Full procedure + the live tools
(`tools/live_report.py`, `tools/mapper_gui.py`) are in `STATUS.md`.

### Going wireless again
- **To a PC/Mac/phone:** reflash the nRF51822 as a **BLE HID gamepad** — see
  `ble_gamepad/` (BLE confirmed working; one motor-buzz blocker documented there).
- **Original dongle behaviour:** a ~$5 nRF5x running Nordic's stock Gazell host would
  pair out-of-box (stock Gazell, no custom work).
- **Not possible on this chip:** PlayStation (Bluetooth *Classic* + Sony auth; nRF51 is BLE-only).

---

## Current state & restore
The controller was **restored to stock firmware** at the end of the 2026-10-31 session
(works normally). To restore it again from the backup:
```bash
pyocd flash -t nrf51 -f 400k -e chip --base-address 0x0 \
   firmware_dump/0x00000000_0x00040000_ROM.bin
```
(The chip stays SWD-unlocked — APPROTECT is not re-enabled — so you can reflash anytime.)

## Resume checklist (RF-sniffing phase only; the main story is in `STATUS.md`)
1. Wire per table, flash `nrf24_pair` for ATmega168 @19200 (see Flashing).
2. `tools/pairlog.py 15` + power on controller → confirm you still see E974/5A on ch32.
3. For reading inputs or going wireless, don't continue down the Nano path — see
   `STATUS.md` (SWD readout) and `ble_gamepad/` (BLE).
