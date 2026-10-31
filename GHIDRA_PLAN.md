# Reversing the pairing handshake in Ghidra

> **SUPERSEDED:** This plan aimed to find "ack bytes to advance pairing" so the Nano could
> emulate the dongle. The firmware RE showed it's stock Gazell with no crypto, and the
> Nano can't host-sync Gazell anyway — so this path was dropped. Instead the inputs are read
> by reprogramming the controller over SWD (see `STATUS.md`). Kept for the Ghidra setup notes.

Goal: find what ACK-payload content the controller (Gazell DEVICE) must receive to leave
beacon mode and start streaming input. There is NO crypto (confirmed), so it's a plain
byte/format check — the decompiler just has to show us which bytes.

## Load
1. Install Ghidra (free, NSA): https://ghidra-sre.org
2. New project → Import `firmware_dump/0x00000000_0x00040000_ROM.bin`.
3. Language: **ARM Cortex little-endian, 16-bit (Thumb)** — `ARM:LE:32:Cortex`.
4. Import options → set **Base Address = 0x00000000**.
5. Let auto-analysis run (defaults + "ARM Aggressive Instruction Finder" on).

## Seed the entry points (from our analysis — saves hours)
Create functions / mark these (Ghidra may already find them):
- Reset 0x154, RADIO IRQ **0x2A10**, TIMER2 0x26A2, **SWI0 0x2CC0**, UART0 0x5044.
- Assert/log helper at **0x1F88** (takes an encoded file:line arg) — rename it `dbg_assert`
  and its callers become easy landmarks for the Gazell library vs app code.
- Peripheral bases to label (Window → Memory map or just comment literals):
  RADIO 0x40001000, RNG 0x4000D000. (ECB 0x4000E000 / CCM 0x4000F000 are UNUSED.)

## Find the pairing logic
1. From `main` (follow Reset → after clock/radio init) find the loop that drives Gazell.
2. The app registers Gazell callbacks (device tx-success / tx-failed). Look for where a
   code address is stored to a RAM pointer during init, then called indirectly from the
   RADIO/SWI0 path. That callback receives the **ACK payload** — the pairing state machine.
3. In that state machine, find the comparison/branch that gates the transition from
   "beacon/pairing" to "connected/data". The bytes it checks in the ack payload are the
   answer. Watch for: a small state variable, a memcmp of the ack payload against a
   constant, or reading specific ack-payload offsets.
4. Also find where the 18-byte beacon `E9 74 03 80 00 48 .. 04 45` is BUILT (it is not a
   flash literal — assembled at runtime). That builder sits inside the same state machine
   and reveals the packet format (and which bytes are device-ID-derived vs constant).

## Cross-check with what we already know (on-air truth)
- Channel 32 (+ custom hop table), 2 Mbps, 3-byte address **01 02 76**, CRC16/0x1021/0xFFFF.
- Device→host: 18-byte REQUEST `E9740380004800000000DB01000000000445`, 1-byte FETCH `5A`.
- Host must answer the FETCH's ACK with whatever the state machine checks for.

## Then implement it
Put the required ACK-payload bytes into `tools/` + the `nrf24_pair` harness (load that ack
for the FETCH). Controller should then switch to the data address and send real input;
decode it the way we decoded the beacon (tools/decode_ch32.py as a template).

## Status note
RF layer fully reversed; firmware dumped (readback protection bypassed); no crypto. Only
the exact handshake-advance bytes remain — that's the one thing to pull out of Ghidra.
