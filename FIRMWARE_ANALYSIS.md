# Firmware dump + analysis (nRF51822)

> **Update:** this analysis (no crypto, stock Gazell) is correct and current. The project
> then used it to read all inputs by reprogramming the chip over SWD, and to build a BLE
> gamepad. See `STATUS.md` (input readout) and `ble_gamepad/` (BLE). The "reverse the
> handshake to emulate the dongle" next-step below was not needed — reading inputs over SWD
> made dongle emulation unnecessary.

Dumped 2026-10-31 via SWD + `nrfsec` (readback protection bypassed, non-destructive).
Files in `firmware_dump/`:
- `0x00000000_0x00040000_ROM.bin` — 256 KB flash (THE firmware; used 0x0..0x3FC14)
- `0x10000000_..._FICR.bin`, `0x10001000_..._UICR.bin` — factory/user config
- `0x20000000_..._RAM.bin` (32 KB, captured while running in pairing mode)
- PERIPH/GPIO dumps (live register snapshots)
- `nrfsec_dump.log`

## Verified
- Genuine firmware: reset vector 0x00000155, initial SP 0x20000ef0.
- Chip: nRF51822 QFAC, 256 KB flash / 32 KB RAM. Device ID 0x45D963F4 0xC3CF04FB.
- UICR RBPCONF = 0xFFFF0000 (readback protection was ENABLED; bypassed to read).

## Key finding: NO ENCRYPTION
- **No hardware AES** — zero references to ECB (0x4000E000) or CCM/AAR (0x4000F000).
- **No software crypto** — no AES S-box / T-tables / Rcon, no SHA-256, no MD5.
- **No embedded 16-byte key** (no high-entropy 16-byte constants).
- Only crypto-ish primitive: **hardware RNG** (0x4000D000) — a get-random-byte routine
  at 0x69f4 (clear VALRDY @0x4000D100, start @0x4000D000, poll, read VALUE @0x4000D500).
=> The pairing is a **plain challenge/validation handshake** (gzp-style with encryption
   OFF, or a simple custom scheme) using RNG session tokens. **There is no secret key to
   recover** — the earlier "extract the AES key" framing does not apply. Replaying the
   correct non-crypto handshake is sufficient.
- NOT stock Nordic gzp: gzp VALIDATION_ID {0x32,0x53,0x66} not present; observed command
  bytes (0xE9 beacon, 0x5A fetch) are not gzp's 0x00-0x08. It's a proprietary protocol.

## Located
- Radio driver ~0x6980-0x6c84; RADIO config helpers at 0x698c (TX setup) and 0x69c0 (RX
  setup) writing PCNF0/PCNF1/RXADDRESSES (RADIO base 0x40001000, config block 0x40001500).
- Radio code reads FICR (0x6c72/0x6c82 literals) — RF address 01:02:76 is likely DERIVED
  from the chip DEVICEID at runtime (not stored as literal bytes; none found in flash).
- Literal pools interleave with code, so FLAT disassembly misaligns — proper analysis
  needs control-flow recovery.

## Next step: reverse the handshake in Ghidra (free)
1. Load `0x00000000_0x00040000_ROM.bin` in Ghidra: ARM Cortex, **little-endian, Thumb**,
   base 0x0. Point the reset vector (0x155&~1) and SP from 0x0/0x4.
2. Find the RADIO RX interrupt/handler and the packet-parse routine; trace how it reacts
   to the device's REQUEST (E9 74 03 ...) and FETCH (5A), and what ACK payload it expects
   to advance (it just needs the right bytes — no crypto gate).
3. Replicate that response in `tools/` + the `nrf24_pair` Nano harness (set the ack
   payload the firmware expects on the FETCH). Then the controller should leave beacon
   mode and stream input on the data address.

## Why earlier ack-payload sweep failed
We guessed ack-payload *values* blindly; the handshake wants a specific *structured*
response (command/format), which the firmware defines. With the dump we can read that
format exactly instead of guessing. (Also ESB can't give different acks to interleaved
same-pipe REQUEST/FETCH packets reliably — may need careful FIFO handling.)
