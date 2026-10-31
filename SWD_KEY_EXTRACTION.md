# SWD firmware dump → extract the pairing key

The controller uses a **proprietary protocol** (NOT stock Nordic gzp — see RESEARCH.md),
so guessing the pairing response can't work. The pairing logic + any key live in the
controller's **nRF51822** flash. This is the plan to read them out.

Chip confirmed from the board: **`N51822 QFACA1 1503AE`** = nRF51822, **QFAC** variant
(256 KB flash / 32 KB RAM), QFN48, date 2015-wk03. SWD-programmable ARM Cortex-M0.

## BEST solder target: the 5-pad programming header on the BACK of the board
The board has a **5-pad factory programming header** on the back (component/D-pad side),
center-ish, above the USB connector — already tinned, far easier than chip pins.
See `hardware/nrf_header.png` / `hardware/nrf_header_zoom.png` (pads numbered 1-5 L->R)
and `hardware/board_back.png`.

**Map the 5 pads with a multimeter (continuity):**
- GND   = pad continuous with USB shell / battery -
- 3.3V  = pad continuous with chip VDD
- SWDCLK= pad continuous with chip pin 24 (the big gold test point traced earlier)
- SWDIO = pad continuous with chip pin 23 (the ~2.4 MOhm net)
- 5th pad = RESET or unused
Record the result (e.g. pad1=GND,pad2=3V3,pad3=SWDIO,pad4=SWDCLK,pad5=RST).

### (Fallback) solder at the chip itself
- `hardware/nrf_solder_FINAL.png` / `_zoom.png`, `hardware/board_nrf51822.png`
NOTE: top-layer via guesses were unreliable (board is multi-layer; SWD routes through
vias to the back). Trust continuity tracing over the annotated vias. Chip orientation:
pin-1 dimple at lower-left; SWDIO=pin23, SWDCLK=pin24 at the top-right corner.

Orientation: **pin-1 dimple is at the chip's lower-left corner**; the antenna/RF network
(L5, C30–C32 → ANT) is above the chip, which confirms the rotation. QFN48 numbering is
counterclockwise from pin 1, so **SWDIO = pin 23, SWDCLK = pin 24** land on the chip's
**top-right corner**.

| Signal | Where to solder |
|---|---|
| **SWDIO** | one of the two **gold vias** at the chip's top-right corner (red circles in the image) |
| **SWDCLK** | the other gold via |
| **GND** | GND pad of C20 or C21 (the caps just below the chip), or the USB/charge-port shield |
| **VDD 3.3V** | VDD pad of C20 or C21 |

Notes:
- **SWDIO vs SWDCLK:** can't be told apart from a photo. Just pick either; if the probe
  won't connect, swap the two wires — swapping them cannot cause damage. (Or buzz each via
  to pins 23/24 with a multimeter: pin 24 = corner-most = SWDCLK, pin 23 = next one = SWDIO.)
- **VDD vs GND on the caps:** the cap pad reading ~0 Ω to the USB shield is GND; the other is VDD.
- Pin 23 is shared with nRESET on nRF51 — normal for SWD.
- nRF51 has internal pulls on SWDIO/SWDCLK → no external resistors needed.
- Keep the controller otherwise unpowered; let the ST-Link's 3.3 V feed VDD.

## Adapter
A **~$3 ST-Link V2 clone** (or J-Link, or a Pi/ESP32 bit-banging SWD). 4 wires:
SWDIO, SWDCLK, GND, 3.3 V.

## Dump the flash (non-destructive)
nRF51 readback protection has been bypassable since 2015 and the chip isn't glitch-hardened.
`nrfsec` reads flash/RAM/UICR/FICR **with protection still enabled** (no erase):

```bash
python3 -m venv venv && ./venv/bin/pip install nrfsec
# needs OpenOCD or pyocd present for the ST-Link
./venv/bin/nrfsec read -a controller_dump.bin     # full, non-destructive read
# (nrfsec 'unlock' is the DESTRUCTIVE mass-erase option — do NOT use; it wipes the key)
```
If `read` fails because protection blocks it, nrfsec's gadget-based read should still work;
fall back to the Include Security / Optiv write-ups (links in RESEARCH.md).

## Find the key + protocol in the dump
```bash
# the 3-byte RF address we recovered, as a landmark:
xxd controller_dump.bin | grep -i '0102 76'
# scan for 16-byte high-entropy blobs (candidate AES keys) and the beacon bytes:
#   beacon payload we saw on-air: E9 74 03 80 00 48 00 00 00 00 DB 01 00 00 00 00 04 45
strings -n 6 controller_dump.bin | less
```
Then reverse the pairing routine (how it builds the response to the `5A` fetch and the
`E974…` request) and replay it as the ack payload via the `nrf24_pair` harness (tools/).

## Risk / honesty
- If APPROTECT + extra flash locking is unusually strong on this unit, readout may fail.
- If the protocol is custom-crypto, you still have to understand the routine after dumping.
- But dumping nRF51 is a solved, documented procedure — this is the realistic path to pairing.
