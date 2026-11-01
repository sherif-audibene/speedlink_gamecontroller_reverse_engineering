# Firmware analysis (nRF51822)

Technical reference for the dumped stock firmware. For the overall story see `README.md`;
for how the dump was taken see `SWD_DUMP.md`.

Dump files in `firmware_dump/`:
- `0x00000000_0x00040000_ROM.bin` — 256 KB flash (the firmware; code+data occupy ~27 KB)
- `0x10000000_..._FICR.bin`, `0x10001000_..._UICR.bin` — factory / user config
- `0x20000000_..._RAM.bin` — 32 KB RAM captured while running in pairing mode
- live PERIPH/GPIO register snapshots, `nrfsec_dump.log` (the RADIO was powered down in
  that PERIPH snapshot, so it holds no radio config. Use `tools/radio_state.py` for live values.)

## Verified facts
- Genuine firmware: reset vector `0x00000155`, initial SP `0x20000ef0`.
- Chip: nRF51822 **QFAC**, 256 KB flash / 32 KB RAM (FICR CODESIZE=256, CODEPAGESIZE=1024).
- UICR RBPCONF = `0xFFFF0000` (readback protection WAS enabled; bypassed to read).
- Flash usage: ~27 KB of code+data at the bottom + a small config page at the top;
  ~229 KB free.

## No encryption (key finding)
- **No hardware AES** — zero references to ECB (`0x4000E000`) or CCM/AAR (`0x4000F000`).
- **No software crypto** — no AES S-box/T-tables/Rcon, no SHA-256, no MD5.
- **No embedded 16-byte key** — no high-entropy 16-byte constants.
- Only crypto-ish primitive: **hardware RNG** (`0x4000D000`), get-random routine at
  `0x69f4` (clear VALRDY `@0x4000D100`, start `@0x4000D000`, poll, read VALUE `@0x4000D500`).

=> Pairing is a **plain, non-crypto** process. **There is no key to recover.**

**Corrected on day 3** (see `PAIRING_PROTOCOL.md`). The link layer is an old Nordic
**Gazell** whose init (`FUN_00000db8`) loads the Gazell defaults (base0 `E7E7E7E7`, base1
`C2C2C2C2`, prefixes `E7 C2..C8`). The **application then overrides them**:
- **250 kbps**, not 2 Mbit.
- Its own 3-step pairing handshake on per-step addresses (pairing base `0xC1C2C6`, then
  the host ID, then the controller's own ID).
- Its own **per-packet channel hopping** (24-bit LFSR, `FUN_00004be4`).

Day-1/2 statements that the link was "stock Gazell with default parameters, 2 Mbit, default
channel table" and that "streaming = Gazell timeslot sync the Nano can't perform" were
wrong. A Nano + nRF24 now acts as the host. The `E9 74 …` packets from the first RF phase are
not part of this link (origin unexplained).

## Peripheral / code map
- RADIO base `0x40001000` (config block `0x40001500`); RNG `0x4000D000`.
  ECB/CCM/AAR present in silicon but **unused**.
- `0x698c` / `0x69c0` (reached via `FUN_00004cd0`) are **raw radio TX/RX starters**
  (set FREQUENCY/TXPOWER/MODE, then `TASKS_TXEN`/`RXEN`), probably a factory test mode,
  not the Gazell driver. An earlier note called this region "the radio driver" and claimed it
  derived the address `01:02:76` from FICR at `0x6c72`/`0x6c82`. That was wrong: `0x6c40..`
  is a literal pool. The real ID derivation is `FUN_00004158`: own ID =
  `(FICR.DEVICEID[0] ^ DEVICEID[1]) & 0xFFFFFF` = `0x16670F`.
- Literal pools interleave with code, so flat disassembly misaligns — use Ghidra's
  control-flow recovery.

## Pairing / radio app layer (day 3, details in `PAIRING_PROTOCOL.md`)
| Function | Role |
|---|---|
| `FUN_00004514` | pairing state machine (1 pair → 2 confirm → 4 stream), one packet per call |
| `FUN_0000483c` / `FUN_00004794` / `FUN_000047e0` | validate the host's ack payload for steps 1 / 2 / 4 |
| `FUN_00004174` | reset to step 1 (pairing address) |
| `FUN_000048a0` / `FUN_00004770` | switch radio to an ID's address / build the Gazell base from an ID |
| `FUN_000048c0` → `FUN_0000027a` | set the channel (one-entry Gazell channel table) |
| `FUN_00004be4` | 24-bit LFSR → next hop channel (2..80) |
| `FUN_00004158` | own ID from FICR DEVICEID |
| `FUN_000041c4` / `FUN_00003a78` | load the bond record from the last flash page `0x3FC00` |
| `FUN_00002e24` | read a little-endian 24-bit ID |
| `FUN_00004f50` / `FUN_00004700` | two startup paths that configure Gazell + pairing address (difference not analysed) |

## Input scan (how the inputs are decoded)
Reimplemented/ported for the custom firmware and verified live over SWD.

- **`FUN_00003c0c` — mux scan.** Drives selects P0.09/10/11, reads ADC **AIN0 (P0.26)** per
  channel (via `FUN_00002edc`), thresholds to 8 button bits. Also drives P0.12/P0.13 for two
  extra channels, and reads 2 trigger analog channels on AIN2/AIN3 (P0.01/P0.02).
- **`FUN_00003e7c` — direct GPIO buttons** (active-low, pull-ups) via `FUN_00006444`
  (GPIO-IN bit): P0.21(Start), P0.23(Back), P0.22, P0.28, P0.29, P0.00, P0.14, P0.10(X/D
  switch), P0.15.
- **`FUN_00003f80` — sticks.** 4 axes, each 4-sample averaged, on **AIN4..7 = P0.03..P0.06**,
  with auto-calibration (tracks per-axis min/max).
- **`FUN_00002edc` — ADC read.** nRF51 legacy ADC; arg is one-hot PSEL (`1`=AIN0, `2`=AIN1,
  `4`=AIN2, … `0x80`=AIN7); preserves the init CONFIG bits, sets PSEL, START, polls END,
  returns RESULT. ENABLE `0x40007500`, CONFIG `0x40007504`, RESULT `0x40007508`.
- **GPIO helpers:** `FUN_00006464`=OUTSET(pin), `FUN_00006434`=OUTCLR(pin),
  `FUN_00006444`=read GPIO-IN bit.

### Decoded RAM state (what `tools/` polls)
- Direct buttons bitmask: `0x2000002c`. Mux buttons bitmask: `0x20000034` (low 16 bits).
- Stick axes: 6 × u16 LE at `0x2000003c..0x47`, value 0..255 in the low byte, rest 128
  (v0/v1 = left stick X/Y; details and open questions in `README.md`). Earlier notes said
  "8 bytes, rest 0, full deflection 255". That was wrong.
- (Bit → pin/channel legend is in `README.md`.)

## Ghidra setup (to reproduce)
- Import `firmware_dump/0x00000000_0x00040000_ROM.bin` as **ARM:LE:32:Cortex**
  (little-endian Thumb), **base 0x0**; run auto-analysis with Aggressive Instruction Finder.
- On macOS the decompiler ships no binary — build it from source and run via Rosetta
  (x86_64). Ghidra 12.1.4 was used (GhidraMCP extension is version-pinned to 12.1.4).
- Entry points / landmarks: Reset `0x154`, RADIO IRQ `0x2A10`, TIMER2 `0x26A2`,
  SWI0 (Gazell callback dispatch) `0x2CC0`, UART0 `0x5044`, assert/log helper `0x1F88`.
- Gazell device-init at `FUN_00000db8` (loads Gazell defaults; the app overrides them, see above).
  Annotated functions saved in the Ghidra project "speedlink": RADIO_IRQHandler,
  AddPacketToTxFifo, ConfigureRadioAddressChannel, GazellTxSuccessCallback,
  HandleGazellAssert, SWI0_GazellCallbackDispatch, Reset_Handler.
