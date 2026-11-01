# RF sniffing phase (nRF24L01 + Arduino Nano)

How the RF parameters were recovered and how to reproduce it. Summary of results is in
`README.md`; this file has the operational detail (wiring, flashing, sketches, captures).

> **Read this first (day-3 correction).** This phase (days 1–2) concluded "2 Mbps,
> address `01 02 76`, and the Nano can't act as the host". All three were wrong for the
> controller's real pairing link: it runs at **250 kbps** on 5-byte addresses
> (pairing `0xC6C2C1E7E7` in nRF24 terms), and the Nano **does** work as the host. See
> `PAIRING_PROTOCOL.md`. Everything below is kept as recorded because the wiring,
> flashing and sniffing techniques are still valid, and the mistakes are instructive.
> The 2 Mbps `01 02 76` packets were real CRC-valid packets, but their source is still unexplained.

## The packets seen at 2 Mbps (unpaired, ~every 1.5 s, input-independent; source unexplained)
- 18-byte request/announce (constant):
  `E9 74 03 80 00 48 00 00 00 00 DB 01 00 00 00 00 04 45`
  contiguous: **`E9740380004800000000DB01000000000445`**
- 1-byte fetch/poll: **`5A`**

What this phase recovered: Nordic ESB-style packets, **2 Mbps**, 3-byte address **`01 02 76`**,
CRC-16 poly `0x1021` init `0xFFFF`, channel **32 (2432 MHz)** (energy also on
~23,29,31,47,48,59,61,63,65). *Day 3: the controller's pairing link is 250 kbps / 5-byte
addresses, with per-packet hopping over ch 2..80, which plausibly explains the spread of channel
energy. The CRC algorithm matches.*

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
| `nrf24_pair` | Generic PRX harness (default 010276 @ 2M), ack payload via serial. Cmds: `K<hex>` ack payload, `KA/KF<hex>` per-packet, `C<n>` channel, `D<hex>` 2nd data addr, **`A<hex>` main listen address (3–5 B, MSB-first `uint64`)**, **`R<n>` rate 0=1M 1=2M 2=250k** (day 3), `P` print cfg, `Z` reset counters. `R2` + `AC6C2C1E7E7` = the controller's real pairing address. |
| `nrf24_host` | **Day 3: the dongle replacement.** Full pairing handshake + streaming at 250 kbps, ch32. See `PAIRING_PROTOCOL.md`. |

## Host tools (`tools/`, run with the venv python)
| Script | What it does |
|---|---|
| `readserial.py [sec]` | Dump raw serial lines. |
| `aggscan.py [sec] [label]` | Aggregate `nrf24_rpd` into a per-channel activity histogram (`<label>.json`). |
| `decode_ch32.py [sec] [label]` | Capture promiscuous output and CRC-recover packets for addr **010276** (the decoder that cracked it). |
| `broad_decode.py [sec]` | Same but recovers ANY address (3/4/5-byte) — finds other packet types. |
| `pairlog.py [sec] [cmds...]` | With `nrf24_pair`: log the handshake with timestamps. Waits for the sketch's `ready` banner before sending commands. Before that fix, commands sent right after the reset were eaten by the bootloader. Check for the `ok:<cmd>` echo. |
| `radio_state.py` / `peek_pairing.py` | Day 3, over SWD: live radio registers / live handshake state of the controller (see `PAIRING_PROTOCOL.md`). |
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

## "Why the Nano can't finish the job" (day-2 conclusion, disproved on day 3)
Original text: *"Acking keeps the controller awake but only ever elicits the `5A` poll —
input is sent only after Gazell link-layer timeslot sync, which the nRF24+ATmega cannot
perform."*

What actually happened: every listen in this phase ran at **2 Mbps on the wrong address**,
so the Nano never talked to the real pairing link. Once the firmware's handshake was decoded
and the live radio registers were read, three things became clear:
- the link is 250 kbps;
- all host replies are static, so the nRF24 can preload them as ack payloads and no real-time
  MAC is needed;
- the "sync" problem was really the app-level per-packet hopping, solved by pinning
  one channel with a 2-byte firmware patch.

The Nano is now the working host (`arduino/nrf24_host`, `PAIRING_PROTOCOL.md`).

*Lesson: a hardware-capability conclusion drawn from experiments on the wrong
parameters isn't evidence. Verify the parameters from the live device first.*
