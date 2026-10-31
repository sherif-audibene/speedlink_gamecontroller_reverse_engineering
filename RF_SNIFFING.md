# RF sniffing phase (nRF24L01 + Arduino Nano)

How the RF parameters were recovered and how to reproduce it. Summary of results is in
`README.md`; this file has the operational detail (wiring, flashing, sketches, captures).

## The packets the controller beacons (unpaired, ~every 1.5 s, input-independent)
- 18-byte request/announce (constant):
  `E9 74 03 80 00 48 00 00 00 00 DB 01 00 00 00 00 04 45`
  contiguous: **`E9740380004800000000DB01000000000445`**
- 1-byte fetch/poll: **`5A`**

Recovered RF link: Nordic ESB/**Gazell**, **2 Mbps**, 3-byte address **`01 02 76`**,
CRC-16 poly `0x1021` init `0xFFFF`, channel **32 (2432 MHz)** hopping a table (energy also
on ~23,29,31,47,48,59,61,63,65).

## Hardware
- **Board:** grey-clone "Arduino Nano" — actually an **ATmega168** (sig `1E 94 06`),
  14 KB flash / 1 KB RAM, CH340 USB (VID `1a86` / PID `7523`).
- **Radio:** nRF24L01+PA+LNA (SMA antenna) on the HW-200 breakout adapter.

### Wiring (adapter label → Nano pin)
| Adapter | Nano | | Adapter | Nano |
|---|---|---|---|---|
| VCC | **5V** (adapter regulates to 3.3V) | | MO (MOSI) | D11 |
| GND | GND | | MI (MISO) | D12 |
| CE | D9 | | SCK | D13 |
| CSN | D10 | | IRQ | (unused) |

All sketches use **SPI @ 4 MHz** (reliable over dupont wires to a PA+LNA module; 10 MHz
default fails).

## Flashing this clone (IMPORTANT — it's a 168, not a 328)
Standard `arduino:avr:nano` fails ("not in sync"); the bootloader runs at **19200 baud**:
```bash
arduino-cli compile --fqbn arduino:avr:nano:cpu=atmega168 --output-dir BUILD arduino/<sketch>
AV=~/Library/Arduino15/packages/arduino/tools/avrdude/8.0.0-arduino1/bin/avrdude
CONF=~/Library/Arduino15/packages/arduino/tools/avrdude/8.0.0-arduino1/etc/avrdude.conf
"$AV" -C "$CONF" -c arduino -p atmega168 -P /dev/cu.usbserial-XXXX -b 19200 -D \
   -U flash:w:BUILD/<sketch>.ino.hex:i
```
- Find the port: `/bin/ls /dev/cu.*` (a macOS sandbox can hide `/dev/cu.*` from shell
  globbing; use `/bin/ls` or pyserial). It re-enumerates as `usbserial-1110` vs
  `wchusbserial1110` — same device.
- Python tools need pyserial: `python3 -m venv venv && ./venv/bin/pip install pyserial`.

## Arduino sketches (`arduino/`)
| Sketch | Purpose |
|---|---|
| `nrf24_diag` | Raw SPI connectivity test (CONFIG write/readback). Use if "radio not found". |
| `nrf24_rpd` | Fast channel-activity scanner (RPD/carrier). Finds busy channels. |
| `nrf24_scanner` | Promiscuous sniffer (2-byte-address trick); parks on ch32 @ 2M. |
| `nrf24_addr` | Tries common ESB default addresses (all missed — address is custom). |
| `nrf24_rx` | ESB receiver on addr 010276, auto-ack ON. First showed the `5A` packet. |
| `nrf24_pair` | Pairing harness: PRX on 010276, ack payload via serial. Cmds: `K<hex>` ack payload, `KA/KF<hex>` per-packet, `C<n>` channel, `D<hex>` 2nd data addr, `P` print cfg, `Z` reset counters. |

## Host tools (`tools/`, run with the venv python)
| Script | What it does |
|---|---|
| `readserial.py [sec]` | Dump raw serial lines. |
| `aggscan.py [sec] [label]` | Aggregate `nrf24_rpd` into a per-channel activity histogram (`<label>.json`). |
| `decode_ch32.py [sec] [label]` | Capture promiscuous output and CRC-recover packets for addr **010276** (the decoder that cracked it). |
| `broad_decode.py [sec]` | Same but recovers ANY address (3/4/5-byte) — finds other packet types. |
| `pairlog.py [sec] [cmds...]` | With `nrf24_pair`: log the handshake with timestamps. |
| `sweep.py` / `sustain.py [ackhex] [sec]` | Sweep candidate ack payloads / sustained acking while pressing buttons (watch for new packets). |

### Reproduce the decode
```bash
# flash nrf24_scanner (parks on ch32 @ 2M), controller ON near the antenna, then:
./venv/bin/python tools/decode_ch32.py 20 test
# -> recovers addr 010276 + payload E9740380004800000000DB01000000000445
```

## Captures (`captures/`)
- `ch32_2m.txt` — ch32 @ 2M, controller on — **the clean capture that gave address + payload**.
- `cap.txt` — first broad hopping capture (2M+1M, all channels).
- `cap1m_on.txt` — parked hot-channels @1M (smeared = wrong rate).
- `baseline_off.json`, `near.json` — RPD channel-activity histograms (off vs near).

## Why the Nano can't finish the job
Acking keeps the controller awake but only ever elicits the `5A` poll — input is sent only
after Gazell link-layer timeslot sync, which the nRF24+ATmega cannot perform. The firmware
dump (see `FIRMWARE_ANALYSIS.md`) confirmed stock Gazell with **no crypto**, so there was no
key to find; inputs are read over SWD instead (see `README.md`).
