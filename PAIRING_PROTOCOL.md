# Pairing protocol & the Nano dongle replacement

How the controller pairs and streams, how we locked it to our own host, and how an
**Arduino Nano + nRF24L01+** became a working replacement for the lost USB dongle.
Work done 2026-11-01 in Ghidra + live SWD + the Nano.

**Result:** the patched controller pairs only with host ID `ABCDEF` and streams input
reports at **~180 reports/s** to `arduino/nrf24_host` (channel 32, 250 kbps).

Sections 1–5 are the **verified** reference. Section 6 is the debugging journey: every wrong
turn we took and what it taught us. Section 7 lists what is still open.

---

## 1. Radio link (verified from live RADIO registers via `tools/radio_state.py`)

| Item | Value |
|---|---|
| Stack | Nordic Gazell (old version) as the link layer + **Speedlink's own app-level pairing/hopping** on top |
| Data rate | **250 kbps** (`RADIO.MODE = 2`) |
| Packet format | ESB-compatible: 5-byte address, 9-bit header (6-bit length + 3 bits), CRC-16 poly `0x11021` init `0xFFFF` (`PCNF0=0x00030006`, `PCNF1=0x01040020`) |
| TX power | `TXPOWER = 4` (+4 dBm) |
| Address width | 5 bytes (Gazell base length 4 + prefix) |

**Gazell ID → nRF24 address.** The firmware turns a 24-bit ID `b2 b1 b0` into a Gazell base
`b0 b1 b2 E7` with prefix `E7` (`FUN_00004770`). For an nRF24 (RF24 library `uint64`) that is
**`0x b0 b1 b2 E7 E7`**. All three addresses were verified on air:

| Address | Gazell ID | nRF24 `uint64` | Used in |
|---|---|---|---|
| Pairing | `0xC1C2C6` (constant, literal @`0x4764`/`0x4fa8`/`0x41b4`) | `0xC6C2C1E7E7` | step 1 |
| Host | host ID, e.g. `0xABCDEF` | `0xEFCDABE7E7` | step 2 |
| Controller | own ID `0x16670F` | `0x0F6716E7E7` | step 3 (streaming) |

**Own ID** (`FUN_00004158`) = `(FICR.DEVICEID[0] ^ FICR.DEVICEID[1]) & 0xFFFFFF` =
`0x45D963F4 ^ 0xC3CF04FB` → **`0x16670F`** on this chip.

## 2. The handshake (state machine `FUN_00004514`, state byte `0x20000005`)

Every call sends **one** packet and checks the ack payload the host returns.
All IDs are 3 bytes, little-endian (`FUN_00002e24`).

| Step / state | Address | Controller sends | Host must ack with | Checker |
|---|---|---|---|---|
| 1 pair | pairing | 7 B: `A1` (`0x81 \| 1<<5`), own ID, 3 B hop-LFSR state | ≥7 B: `01`, **host ID**, 3 B any | `FUN_0000483c` |
| 2 confirm | host | 7 B: `82`, own ID, host ID | ≥7 B: `02`, host ID, own ID (host ID **or** own ID must match) | `FUN_00004794` |
| 4 stream | controller | 21 B: `84` (`\|0x10` on a retransmit), flags byte, 19 B input report | ≥5 B: `04`, b1 bit0 = 0 | `FUN_000047e0` |

- Type check is `(b0 & 0x8F) == type`, so the high bits of byte 0 are free (`A1`, `94`…).
- Success in step 1 → `FUN_000048a0(hostID)` switches to the host address, state 2.
  Success in step 2 → switches to its own-ID address, state 4.
- Failure handling (stock): step 1 retries forever. Step 2 drops back to step 1 on the first
  failure. Step 4 drops back after >16 failed rounds (~0.2 s). The reset is done by `FUN_00004174`.
- Step-4 ack: if b1 bit0 is set 60+ times in a row, the controller sets pairing-struct `+9`
  (meaning unknown, maybe a sleep request). Our host always sends 0.
- **Step-4 ack bytes 3 and 4 = rumble** duty for the two motors (P0.24/P0.25 PWM, via
  `FUN_00004910` → `0x20000094/95`). Our host sends 0 (motors off). A host could drive rumble
  through these two bytes (untested).

Pairing struct at `0x20000004`: `+0` current channel, `+1` state, `+2` step-4 fail counter,
`+3` bonded flag, `+0xC` u16 strict-window timer, `+0xE..0x10` hop LFSR, `+0x14` own ID,
`+0x18` host ID.

## 3. Bond record & host lock

The last flash page `0x3FC00` is loaded at boot by `FUN_000041c4` → `FUN_00003a78(buf, 3)`
(page = `(FICR.CODESIZE-1) * CODEPAGESIZE`):

| Offset | Meaning | Stock dump | Locked image |
|---|---|---|---|
| `+0x04` | host ID → struct `+0x18` | `00000000` | `00ABCDEF` |
| `+0x08` | b0 = bonded flag → `+3`, b1/b2 misc | `00000000` | `00000001` |
| `+0x0C` | misc; top byte `0xAA` = normal | `AA010100` | `AA010100` |
| `+0x10` | magic `0xAA558877` (`DAT_00003aac`) | ✓ | ✓ |

Host acceptance in `FUN_0000483c`. Stock only enforces the stored host while the
bonded flag is set **and** a timer is running; otherwise it learns any host:
```
0x485e  cmp r2,#1      ; bonded?
0x4860  bne 0x4880     ; no  -> learn ANY host ID
0x4862  ldrh r1,[r4,#0xc]
0x4866  beq 0x4880     ; window over -> learn ANY host ID
0x4868  ...compare reply's host ID with stored +0x18, reject if different
```

## 4. Channel hopping (app layer, not Gazell)

Every `FUN_00004514` call first runs `FUN_00004be4`, a 24-bit LFSR (state = struct
`+0xE..0x10`). The channel is `lfsr & 0x7F` folded into 2..80 and stored in struct `+0`.
Step 1 instead uses the table `8,16,24,32,40,48,56,64` (`0x6c20`) indexed by `ch & 7`.
`FUN_000048c0(ch)` → `FUN_0000027a` installs it as a one-entry Gazell channel table.
**The 3 "random" bytes in the `0x81` packet are the LFSR state**, so a real dongle can
predict the sequence. A slow single-channel host can't follow it reliably, so we pin the
channel instead (section 5).

## 5. What we changed

### Controller: `tools/make_locked_rom.py ABCDEF` (17 bytes vs stock)
| Offset | Stock → patched | Why |
|---|---|---|
| `0x3FC04..` | bond record (host `ABCDEF`, bonded, magic) | the controller targets our host |
| `0x4860`, `0x4866` | `bne`/`beq` → NOP | strict lock: always compare host ID |
| `0x45f0`, `0x4624` | `beq`/`b 0x46d6` → `0x4610` (return) | step 2 retries instead of resetting |
| `0x46a0` | `cmp r0,#0x10` → `#0xFE` | streaming tolerates ~3 s of misses and still self-recovers |
| `0x48c2` | `mov r4,r0` → `movs r4,#32` | no hopping: always channel 32 |
| `0x3908` | `bl 0x3ab0` → 2× NOP | Home power-off no longer overwrites the bond with host 0 (step 9) |

Flash (`-f 100k -e chip`; 400 kHz / sector erase timed out mid-erase on our wiring):
```
pyocd flash -t nrf51 -f 100k -e chip --base-address 0x0 prebuilt_hex/speedlink_locked_ABCDEF.bin
```
Restore stock: same command with `firmware_dump/0x00000000_0x00040000_ROM.bin`.

### Host: `arduino/nrf24_host/nrf24_host.ino`
- Same radio settings as section 1, channel 32, dynamic payloads + ack payloads. All
  replies are static and preloaded in the ack FIFO, so the ATmega never has to react
  in real time.
- **Address ring:** pipe 1 walks pairing → host → controller address and
  **advances after 1.5 s of silence** (not on reception). As long as the controller keeps
  sending the current step, our reply hasn't landed yet, so we keep answering it. A lost
  ack only costs a retry. Wherever the controller is, one lap of the ring reaches it.
- **Waits for the ack to be transmitted** (TX FIFO empty) before flushing or changing the
  address. The ack leaves ~0.65 ms after RX at 250 kbps.
- **Own ID stored in EEPROM**, so a Nano reset still finds a controller that is already streaming.
- Serial 115200: `STATE …`, `tick 81:n 82:n 84:n` (packets/s per step; off by default, `#define TICK_LOG 1`), and `REP <hex>` when
  the report changes.

### Input report (`REP` = 20 bytes after the `84` type byte; preliminary)
`18 | 01 LX LY RX RY B1 B2 00 …`
- `18`: the flags byte the firmware builds (`x<<4 | (y&3)<<2 | struct[8]`), not input.
  Bits 2..3 carry the power state (`0x2000011a`).
- The 19-byte report is built by `FUN_00002ffc` at `0x200001a0`. Its layout depends on the **X/D
  switch** (decoded from code, see `FIRMWARE_FUNCTIONS.md` §3; only D mode has been seen on air):
  - **D mode** (our controller): `01 | LX LY RX RY | b5 | b6 | b7 | L2 R2 pressure`.
    - b5 = hat (low nibble, `F` = centre) + `10` A/✕, `20` B/○, `40` X/□, `80` Y/△.
    - b6 = `01` L1, `02` R1, `04` L2, `08` R2, `10` Back/Select, `20` Start, `40` L3, `80` R3.
    - b7 = `01` Home.
  - **X mode:** `00 14 | b2 | b3 | LT RT | LX LY RX RY` (int16 LE), XInput-style.
  - In D mode a **digital sub-mode** (default on, **Home toggles it**) maps the right stick onto
    face buttons and forces RX/RY = `0x80`, so turn it off for an analog right stick.
- Matches what we saw: `REP 18 | 01 80 80 80 80 0F 00` at rest. `0F`→`8F`/`2F`/`4F` = face
  buttons; `B2` `10`/`20` = Back/Start.

## 6. The journey: wrong turns and lessons

1. **Static analysis said "pairing address E7+C1C2C6"; the old sniff said "`01 02 76` at
   2 Mbps".** The Nano heard nothing on the decoded address, first because the address
   commands were swallowed by the Nano bootloader (`pairlog.py` now waits for the sketch
   banner), then because of byte-order guesses.
   *Lesson: an echoed `ok:` confirmation is worth having in any serial command protocol.*
2. **Reading the live radio registers settled it.** `tools/radio_state.py` showed
   `MODE=2` = **250 kbps**. Every earlier listen ran at 2 Mbps. At 250 kbps the first
   address (`C6C2C1E7E7`) received `A1 0F6716 …` immediately.
   *Lesson: when static analysis and sniffing disagree, read the live peripheral.*
3. **Step 1 passed, step 2 never did.** Stock resets to step 1 on any step-2 failure, and a
   one-channel host misses most attempts. Patched step 2 to retry (`0x45f0`, `0x4624`).
4. **The debug tool lied.** `peek_pairing.py` used pyocd's default connect, which
   **halts the CPU**. Its single unchanging output line was a frozen controller. Every test run
   alongside it was invalid, including the run where the host sketch's **pipe 0 looked
   deaf**. That pipe-0 conclusion is therefore unproven. We moved to pipe 1 only anyway.
   *Lesson: monitor with `connect_mode="attach"`.*
5. **The ack-flush race.** The sketch flushed/rewrote the ack FIFO right after RX, before
   the ack had been transmitted, so the controller mostly got empty acks. Fixed by waiting for
   TX FIFO empty.
6. **Advance on reception → desync.** Switching address the moment a step was heard broke
   whenever that one ack was lost. Fixed with the silence-driven ring.
7. **Streaming died in ~0.2 s** (16 failed rounds) before the host's 1.5 s
   silence-advance arrived. A first patch (NOP the reset) caused a **deadlock**: a Nano
   reset lost the own ID, so it could never find a controller stuck streaming. The final
   fix is both: EEPROM own ID + threshold 254 rounds (~3 s) instead of never.
8. **Only ~4 reports/s.** The app layer hops every packet (section 4). Pinning channel 32
   (`0x48c2`) → **~180 reports/s**, stable.
9. **Bond wipe on Home power-off.** Documenting the firmware turned up a risk: the latch-off
   state (`0x38bc`) saves the bond record with host ID 0. Confirmed on hardware: after
   switching off with Home, `read32 0x3fc00 20` showed `ffffffff 00000000 00000000 aa000100
   aa558877` (host 0, bonded 0, magic intact), and the strict lock then rejects the Nano.
   Only 2 callers of the save routine exist (a scan for `bl 0x3ab0`): `0x3a20` (normal sleep,
   saves the real host ID) and `0x3908` (latch-off, saves zeros). NOPing `0x3908` fixed it:
   power off with Home → power on → reconnects to the Nano.
   *Lesson: an "undefined" function in Ghidra has no xrefs; scan the raw binary for BL targets.*

## 7. Open questions
- **The old `01 02 76` / `E9 74 03 80…` / `5A` traffic at 2 Mbps** (`RF_SNIFFING.md`) is not
  this link: the controller only ever showed `MODE=2` (250 kbps). Its source is unexplained.
  Packets did appear on the Nano shortly after the controller was powered on, so the
  controller isn't ruled out. Possibly another firmware path (two startup paths exist,
  `FUN_00004f50` vs `FUN_00004700`), or another nearby 2.4 GHz device.
- ~~`0x698c` / `0x69c0` raw TX/RX~~ **Resolved:** the hidden RF test mode (Start+Home+Back at
  power-on) uses Nordic `radio_test` modulated / constant-carrier TX. ~~Two startup paths~~
  **Resolved:** `0x4700` is the only normal setup; `0x4f50` is test mode 3.
- ~~Bond-wipe risk~~ **Fixed and verified on hardware** (section 6 step 9): Home power-off used to
  save host ID 0; `bl 0x3ab0` at `0x3908` is now NOPed. Details: `FIRMWARE_FUNCTIONS.md`.
- Pipe 0 on the host: untested since the halt bug (section 6.4).
- Following the LFSR hop sequence (instead of pinning ch32) for interference robustness.
- Full input-report map; then a PC side (serial → virtual gamepad), since the ATmega168
  Nano can't be a USB HID device.
- **Next project:** passive on-air sniffer of the controller ↔ Nano link with an ESP32 running
  esp-sdr (receive-only, so not a Nano replacement). Plan: `RF_SNIFFING.md` → "Next project".
- **Right stick and triggers** changed none of the six RAM axis values in the
  2026-11-01 `stick_probe.py` test. Explained by the code (D-mode digital sub-mode + triggers stored
  elsewhere, see `FIRMWARE_FUNCTIONS.md`). Not yet confirmed on hardware by toggling Home.

## 8. Tools added in this phase
| Tool | Purpose |
|---|---|
| `tools/make_locked_rom.py` | build the patched image (`--selftest`, `--soft` = bond only, no strict lock) |
| `tools/radio_state.py` | live RADIO registers + pairing state + nRF24-equivalent address/rate/channel |
| `tools/peek_pairing.py` | live handshake state + last ack payload received (non-halting) |
| `tools/pairlog.py` | drive `nrf24_pair` (`A<addr>`, `R<rate>`, `K…`) and log packets |
| `arduino/nrf24_pair` | generic PRX harness: `A<hex>` address, `R0/1/2` rate (1M/2M/250k), ack payloads |
| `arduino/nrf24_host` | the dongle replacement |
