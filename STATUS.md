# Speedlink Controller — Project Status & Full Findings

Complete reverse-engineering + custom-firmware record for the dongle-less Speedlink
gamepad (nRF51822). This is the master status; see also README.md, RESEARCH.md,
FIRMWARE_ANALYSIS.md, SWD_KEY_EXTRACTION.md, GHIDRA_PLAN.md.

## The journey (what was accomplished)
1. **RF reverse-engineered** — Nordic **Gazell**, 2 Mbps, 3-byte addr `01 02 76`, CRC16,
   ch32 (+hop table). Default Gazell pipe addresses (E7E7E7E7 / C2C2C2C2 / prefixes
   E7,C2..C8). No encryption anywhere.
2. **Conclusion on radio:** the controller only streams input once *paired* (Gazell
   link-layer sync). The nRF24+Nano cannot do Gazell host sync — so emulating the lost
   dongle on the Nano is not viable. (A $5 nRF5x running Nordic's Gazell host would.)
3. **Pivoted to reprogramming the controller** itself over SWD (ST-Link).
4. **Dumped the readback-protected firmware** with `nrfsec` (CPU read-gadget bypass),
   reverse-engineered it in Ghidra (self-built macOS decompiler). Full dump in
   `firmware_dump/`.
5. **Mass-erased + unlocked** the chip (`nrfsec erase`) and **flashed custom firmware**;
   read inputs live over the ST-Link.
6. **Read ALL inputs the easy way:** restored stock firmware and polled its decoded
   button/stick state out of RAM over SWD (mux solved for free). See the ✅ section
   under INPUT ARCHITECTURE. Tools: `tools/live_report.py`, `tools/mapper_gui.py`.
7. **BLE gamepad attempt:** the nRF51822 is a BLE chip, so we reflashed it (S130
   SoftDevice + a HID-gamepad app built from Nordic's example) to pair directly with
   a PC/Mac — no dongle. BLE **works** (paired as `Nordic_Mouse`/`Speedlink_Pad`),
   but a **vibration-motor buzz while connected** is unsolved. Full write-up +
   firmware in **`ble_gamepad/`**. Controller has been **restored to stock**.

## Hardware / SWD
- Chip: **nRF51822 QFAC** (256KB/32KB), SWD pads: **SWDCLK** = big gold test point near
  pin24 corner; **SWDIO** = adjacent (through a ~2.4MΩ net); GND + 3.3V from C20/C21.
  See `hardware/` images.
- **Run SWD at 500kHz** (`pyocd ... -f 500k`); the hand-soldered link is flaky at higher
  speed and drops often. **A soldered header would make this far more reliable.**
- ST-Link wedges after a failed op → unplug/replug USB. Reseat SWDIO/SWDCLK/GND if
  "Target not detected".

## INPUT ARCHITECTURE (key result)
Inputs are split across two paths:

### A) Direct-GPIO (active-low, need pull-up; pressed = pin → 0) — WORKING
Firmware reader `FUN_00003e7c` reads these GPIO IN bits:
| Pin   | Input (confirmed / inferred) |
|-------|------------------------------|
| **P0.21** | **Start**  ✅ confirmed |
| **P0.23** | **Back/Select** ✅ confirmed |
| **P0.10** | **X/D mode switch** ✅ confirmed (NOT a button) |
| P0.00, P0.14, P0.15, P0.22, P0.28, P0.29 | other direct buttons (not individually mapped; likely D-pad/misc) — but note most didn't respond when bridged, see below |

### ✅ SOLVED — read buttons via STOCK firmware in RAM (no mux RE needed)
Don't fight the mux in custom firmware. Flash the **stock** firmware back, let it
run, and **poll its decoded button state out of RAM over SWD** (AHB reads work
while the CPU runs — no halt). The stock firmware handles the HC4051 + sticks.
- Direct buttons bitmask: **`0x2000002c`** (bit set = pressed; see FUN_00003e7c).
- Mux buttons/sticks bitmask: **`0x20000034`** low 16 bits (see FUN_00003c0c).
- Mux bits: 0x10=ch0 0x80=ch1 0x40=ch2 0x20=ch3 0x1000=ch4 0x2000=ch5 0x4000=ch6 0x8000=ch7.
- Direct bits: 0x8=P0.21(Start) 0x1=P0.23(Back) 0x4=P0.28 0x2=P0.29 0x20000=P0.15
  0x400000=P0.14 0x800000=P0.10(X/D switch) 0x10000=P0.22. **P0.00(0x100000)=stuck-low, ignore.**
- All 8 mux channels verified switching (ch0..ch7 each respond). Tool: `tools/live_report.py`.
- Restore+run: `pyocd flash -t nrf51 -f 400k -e chip --base-address 0x0 firmware_dump/0x00000000_0x00040000_ROM.bin`

### B) Multiplexed via **74HC4051** (8-ch analog mux) → ADC — (custom-fw path, superseded)
- Mux: VCC(pin16)=3V ✓, Enable(pin6)=0V ✓ (enabled), common-out **pin3 = 3V idle**.
- Select lines **S0/S1/S2 = P0.09 / P0.10 / P0.11** (per firmware `FUN_00003c0c`).
- Mux output → ADC **AIN0 (P0.26)** (`FUN_00002edc(1)`).
- Firmware scans 8 channels (buttons) + reads 4 stick axes on other AINs
  (`FUN_00003f80`, 4-sample averaging), thresholds to a HID report (`FUN_00002ffc`).
- The **face buttons A/B/X/Y, sticks, and (at least one) shoulder are on this mux.**

### THE BLOCKER (muxed path)
- Our custom firmware's mux reads are **constant across all 8 channels** → the **mux is
  not switching**. Grounding the mux output (pin3→GND) drops the ADC to 0 (so the ADC
  *does* see the output), and pressing a **shoulder** drops **all 8 channels together**
  (confirming we read one stuck channel 8×, not 8 different ones).
- Root cause (likely): **P0.10 is both the X/D switch and select S1** — the slide
  switch clamps P0.10, so S1 can't drive the mux. **Try the other switch position (D vs
  X) — it clamps S1 to the opposite value and may expose the other 4 channels.**
- Also: unpressed mux channels are **high-impedance** (~376 float); the nRF51 ADC needs
  **no-prescaling (INPSEL=0)** and ideally **4-sample averaging** (as the stock firmware
  does) to read reliably.

## Remaining bench work to finish muxed inputs
1. Solder a firm 4-wire SWD header (stop the link drops).
2. Multimeter continuity (power off): confirm **P0.09/10/11 ↔ HC4051 pins 9/10/11**, and
   **HC4051 pin3 ↔ MCU P0.26**. Resolve the P0.10/switch conflict (the switch may need to
   be in a specific position, or S1 is driven elsewhere).
3. In `custom_fw/muxread.c`: keep INPSEL=0, add 4-sample averaging, longer settle; verify
   selects actually change pin3 by holding a shoulder and cycling selects — one select
   value should DESELECT it (AIN0 ≠ 0).
4. Map each face button/stick to its mux channel by bridging pads with the scanner live.

## Custom firmware (custom_fw/) + tools (tools/)
- `safe_hold.c/.bin` — drives all pins LOW (motors/LEDs OFF, safe on power-up). **Flash
  this if the motors ever buzz.**
- `muxread.c/.bin` — 8-channel mux scanner (AIN0, selects P0.09/10/11) → RAM 0x20001008..
- `ainscan.c/.bin` — raw AIN0..7 scanner.
- `firmware.c` — GPIO-mirror (early test).
- tools: `live_buttons.py` (direct GPIO buttons, pull-ups, motor-safe),
  `live_mux.py` (8 mux channels), `live_ain.py` (raw AIN0-7). Run with the venv python:
  `/private/tmp/.../scratchpad/venv/bin/python <tool>` at 400-500kHz.
- Build: `arm-none-eabi-gcc -mcpu=cortex-m0 -mthumb -nostdlib -nostartfiles -ffreestanding
  -Os -T nrf51.ld X.c -o X.elf && arm-none-eabi-objcopy -O binary X.elf X.bin`
- Flash: `pyocd flash -t nrf51 -f 500k --base-address 0x0 X.bin`  (chip already unlocked)

## ⚠ MOTOR SAFETY
The vibration motor driver turns ON when many pins float/pull-up at once (our first
all-pullup firmware triggered it). The motor-enable needs **multiple pins high**; driving
pins LOW keeps it off. `safe_hold.bin` guarantees off. When reading buttons, only pull up
the specific pins needed and drive the rest low.

## Restore to stock
Original firmware backup: `firmware_dump/0x00000000_0x00040000_ROM.bin`.
Restore: `pyocd flash -t nrf51 -f 400k -e chip --base-address 0x0 firmware_dump/0x00000000_0x00040000_ROM.bin`
(Note: APPROTECT won't be re-enabled; functionally the controller returns to stock.)
**The controller was restored to stock at the end of the 2026-10-31 session.**

## Repository map
- `STATUS.md` (this file), `README.md`, `RESEARCH.md`, `FIRMWARE_ANALYSIS.md`,
  `SWD_KEY_EXTRACTION.md`, `GHIDRA_PLAN.md` — docs.
- `firmware_dump/` — original firmware + FICR/UICR/RAM dumps (restore source).
- `tools/` — PC-side Python (run with the pyocd venv):
  - `live_report.py` — live button/stick readout from stock firmware's RAM over SWD.
  - `map_buttons.py` — CLI interactive name-the-controls mapper.
  - `mapper_gui.py` — tkinter GUI mapper (auto-centers sticks); writes `button_map.json`.
  - `diag_sticks.py` — find which RAM bytes move when sticks move.
  - `diag_rest.py` — measure stick rest jitter (proved SWD reads are exact, sticks clean).
- `button_map.json` — control name → signal map from the GUI mapper.
- `custom_fw/` — bare-metal nRF51 test firmware (built with Homebrew arm-none-eabi-gcc):
  - `safe_hold.c/.bin` — drive all pins low (motor OFF). Flash if it ever buzzes.
  - `muxread.c`, `ainscan.c`, `firmware.c` — early scan experiments.
  - `diag_float/direct/sel/combo.c` — motor-trigger isolation tests (BLE phase).
- `ble_gamepad/` — the BLE HID gamepad firmware + S130 SoftDevice + build/flash README
  (see its README for the motor-buzz blocker and how to finish).

## How to read the controller's buttons/sticks right now (works today)
1. Ensure stock firmware is flashed (it is).
2. `pyocd` venv:
   `/private/tmp/.../scratchpad/venv/bin/python` — or recreate a venv with
   `pyocd pyusb capstone`.
3. Run `tools/mapper_gui.py` (needs the ST-Link on SWD). Press buttons / move sticks.
   RAM: direct buttons `0x2000002c`, mux buttons `0x20000034`, 8 stick-direction
   bytes `0x2000003c..0x20000043` (rest 0, full push 255).
