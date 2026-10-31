# SWD access: solder points, firmware dump, unlock

How to attach SWD to the controller's nRF51822, dump its firmware non-destructively, and
(if needed) unlock it. There is **no key to extract** — this is just the hardware access
procedure (see `FIRMWARE_ANALYSIS.md` for what's in the dump).

Chip: **`N51822 QFACA1 1503AE`** = nRF51822 **QFAC** (256 KB / 32 KB), QFN48,
date 2015-wk03, SWD ARM Cortex-M0.

## Where to solder
Best target: the **5-pad factory programming header** on the back of the board
(component/D-pad side, center-ish, above the USB connector) — already tinned. See
`hardware/nrf_header*.png` and `hardware/board_back.png` (pads numbered 1–5 L→R).

Map the 5 pads with a multimeter (continuity), e.g.:
- **GND** — continuous with USB shell / battery −
- **3.3 V** — continuous with chip VDD
- **SWDCLK** — continuous with chip **pin 24** (corner-most gold test point)
- **SWDIO** — continuous with chip **pin 23** (the ~2.4 MΩ net)
- 5th pad — RESET or unused

Fallback (solder at the chip): pin-1 dimple at lower-left; antenna network (L5, C30–C32)
above the chip confirms rotation; QFN48 numbering is counterclockwise from pin 1, so
**SWDIO=pin 23, SWDCLK=pin 24** land at the top-right corner (the two gold vias there).
GND/VDD from the pads of C20/C21 (the caps just below the chip). See
`hardware/nrf_solder_FINAL*.png`, `hardware/nrf_solder_FINAL_zoom.png`,
`hardware/board_nrf51822.png`.

Notes:
- **Trust continuity tracing over any top-layer via guess.** The board is multi-layer and
  SWD routes through vias to the back, so annotated top-side via positions were unreliable —
  buzz pins 23/24 to the vias with a multimeter to be sure.
- Can't tell SWDIO vs SWDCLK from a photo — pick either; swap if it won't connect
  (swapping can't cause damage). Or buzz them out: pin 24 (corner-most) = SWDCLK,
  pin 23 (next one) = SWDIO. nRF51 has internal pulls → no external resistors needed.
- **VDD vs GND on the caps:** the cap pad reading ~0 Ω to the USB/charge-port shield is GND;
  the other is VDD.
- Pin 23 is shared with nRESET on nRF51 (normal for SWD).
- **Keep the controller otherwise unpowered** — let the ST-Link's 3.3 V feed VDD.
- Adapter: a ~$3 **ST-Link V2 clone** (or J-Link, or a Pi/ESP32 bit-banging SWD). 4 wires:
  SWDIO, SWDCLK, GND, 3.3 V.
- **Run everything at `-f 400k`** — the hand-soldered link is flaky faster; reseat / replug
  the ST-Link on "Target not detected" / IDCODE errors.

## Dump the flash (non-destructive, with readback protection ON)
nRF51 readback protection is bypassable (Cortex-M0 read gadget) and the chip isn't
glitch-hardened. `nrfsec` reads flash/RAM/UICR/FICR without erasing:
```
python3 -m venv venv && ./venv/bin/pip install nrfsec pyocd pyusb
./venv/bin/nrfsec read -a           # full non-destructive read (gadget bypass)
```
This is how `firmware_dump/` was produced (RBPCONF was `0xFFFF0000` = protected). If a plain
`read` is blocked by protection, nrfsec's gadget-based read still works (it did here); the
Include Security / Optiv write-ups in `RESEARCH.md` cover the technique. nRF51 SWD can't be
fully disabled and the chip isn't glitch-hardened (unlike nRF52), so no voltage glitching is
needed. (If a unit had unusually strong extra flash locking, readout could still fail — ours
didn't.)

## Unlock (DESTRUCTIVE — only to reprogram the chip)
Mass-erase clears flash **and** APPROTECT, leaving the chip open for reflashing:
```
echo y | ./venv/bin/nrfsec erase    # mass-erase + unlock (wipes firmware!)
```
Do this only after you have the dump backed up. Afterwards the chip stays unlocked, so you
can flash/read freely with pyocd.

## Restore to stock
```
pyocd flash -t nrf51 -f 400k -e chip --base-address 0x0 \
   firmware_dump/0x00000000_0x00040000_ROM.bin
```
(APPROTECT is not re-enabled; the controller otherwise returns to stock behaviour.)
