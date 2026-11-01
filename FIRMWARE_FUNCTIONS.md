# Firmware function reference (Speedlink pad, nRF51822 stock firmware)

All **255 Ghidra functions** of `firmware_dump/0x00000000_0x00040000_ROM.bin`, plus code
regions Ghidra hasn't defined as functions yet. Produced 2026-11-01 by five parallel
read-only Ghidra passes (one per address range). The key claims were then cross-checked by hand
(see "Verified / corrected"). Every row has a **confidence** (high / med / low). Treat low as a lead,
not a fact. **These names are applied in the Ghidra project** (`speedlink.rep`, 2026-11-01).
The exact mapping is in `tools/ghidra_names.json`; reapply it with `tools/apply_ghidra_names.py`.
Differences from the "Suggested name" column: low confidence → `_maybe` suffix; Gazell-core
duplicates of API names → `gzll_core_` prefix; `0x2c50` → `gzll_queue_callback_event`;
`0x2edc` → `ADC_ReadChannel`, `0x4074` → `GPIO_InitPins` (the plugin rejected the generic names).

Related: `FIRMWARE_ANALYSIS.md` (overview, no-crypto proof), `PAIRING_PROTOCOL.md` (radio
link + the Nano dongle), `README.md` (input RAM map, hardware).

---

## Big picture

**Boot:** `Reset_Handler 0x154` → SystemInit `0x4edc` → C runtime init → thunk `0xc8` →
**`main` = `FUN_00005a50`**.

`main` init order:
1. GPIO `0x4074` (P0.16 power latch + P0.7 out, LEDs P0.17–20, button pull-ups)
2. HFXO `0x5620`
3. 10.24 ms tick on TIMER0 `0x4fc0`
4. rumble PWM `0x4960`
5. own ID `0x4158`
6. **Gazell setup `0x4700`** (the only normal radio setup)
7. pairing reset `0x4174`
8. input init `0x492c`
9. **bond-record load `0x41c4`**
10. WDT `0x50f8`
11. test-mode check `0x4c68`

**Main loop (every 10.24 ms tick):**
- power latch
- pairing/stream step `FUN_00004514` (while app state `0x20000068` is 2 or 4)
- input task `0x4bb0`: direct buttons `0x3e7c` → mux `0x3c0c` → sticks `0x3f80` → report builder `0x2ffc`
- rumble
- app state machine `0x4a54`
- feed the watchdog

| Layer | Address range | Notes |
|---|---|---|
| Old **Nordic Gazell** (nrf_gzll) API + core | `0x018c`–`0x2d5c` | API wrappers, packet pool (6×34 B @`0x20000578`, empty = `0xDEADDEAD`), 16 FIFOs × 3, radio driver (state `0x20000644`), TIMER2 1 MHz scheduler, SWI0 callback queue. ESB-compatible radio config. Variant has extras (CRC-length setter, no-ack flag on TX add) |
| **Application** | `0x2e24`–`0x5a50` | ADC/battery, input scan + debouncing, **report builder** (X / D / unused PS3 layouts), turbo, LEDs, power states, **pairing state machine**, bond record, hidden RF test mode |
| **Nordic SDK drivers** | `0x5b38`–`0x69f4` | nrf_adc, delay, IRQ, GPIOTE, PPI, TIMER, WDT, **app_pwm** (rumble), radio_test helpers, RNG |

**Peripherals:**

| Peripheral | Used for |
|---|---|
| RADIO | Gazell, 250 kbps app setting; radio_test |
| TIMER0 | app tick |
| TIMER1 + GPIOTE + PPI | 2-ch rumble PWM, P0.24/P0.25, 200 Hz |
| TIMER2 | Gazell |
| RTC1 + SWI1 | app_timer |
| ADC | sticks AIN4–7, triggers AIN2/3, mux AIN0, battery AIN1 |
| NVMC | bond record |
| WDT | 200 ms |
| RNG | test payload |
| POWER | SYSTEMOFF |
| UART0 | driver linked in but never started (dead code) |

No crypto peripherals are used.

## Verified / corrected by hand (2026-11-01)

| Topic | Result |
|---|---|
| Watchdog | **200 ms**, behaviour 0 (**paused in sleep and debugger halt**): `0x50f8` passes cfg `0x6c08` = {0, 200, 1}. The 2000 ms cfg at `0x6c5c` is the unused SDK default. One draft had this wrong; it is fixed below |
| `0x2c50` "AddPacketToTxFifo" (old Ghidra name) | **Misnamed.** It copies a 12-byte event into a 10-entry ring, then sets NVIC ISPR bit 20 (SWI0) = **queue a Gazell callback event**. The real "add packet to TX FIFO" is **`0x40e`** (pipe ≤7, len ≤32, no-ack flag) |
| "Two startup paths" (`0x4f50` vs `0x4700`) | Resolved: `0x4700` is the only normal one. `0x4f50` is only reached from RF **test mode 3** |
| `0x698c` / `0x69c0` | radio_test **modulated TX** (random payload) / **constant-carrier TX** (`RADIO.TEST=3`). Neither is RX |
| Stick `0x8000` mid-update reads | Not recalibration. In D mode `0x3f80` writes 16-bit values (centre `0x8000`) and the report builder shifts them **in place** `>>8`. SWD reads can land in between |
| Right stick "dead" in `stick_probe.py` | In D mode the **digital sub-mode** (`0x2000010f`, default on, **Home toggles**) maps the right stick to face buttons and forces RX/RY = `0x80` (`0x49d8`). Triggers live at `0x200001ee/ef` + button bits `0x100/0x200`, not in the stick array |
| X/D switch | `0x2000010d` = 1 for **D** (P0.10 high). The direct-button bit `0x800000` in `0x2000002c` is active-low, so it reads 0 in D mode. Our controller is in D mode, which matches the `REP 18 01 LX LY RX RY …` layout |
| README mux legend | Only the bit values / button names are right (A `0x4000`, B `0x2000`, X `0x8000`, Y `0x1000`, which match `button_map.json`). The "ch4–ch7" labels don't match the real HC4051 channels (ch4 A, ch5 B, ch6 X, ch7 Y). `0x20000034` is the **combined** debounced button word (direct + mux + triggers), not mux-only |

## ⚠️ Bond-wipe risk for the locked image

The bond record (`0x3FC00`) is **rewritten by the firmware itself** (`0x3ab0` = erase page, write 3 words + magic):
- **State 5 = deep sleep (`0x3984`):** saves the RAM host ID. With our strict lock that's always `ABCDEF`, so this is harmless.
- **State 6 = latch-off (`0x38bc`):** saves **host ID 0, bonded 0** (verified in the disassembly:
  `[sp+0]=0`, `[sp+4]=0`, then `bl 0x3ab0`). With the strict lock (`0x4860`/`0x4866` NOPs), the next boot
  compares every reply against host 0, so **the controller would never pair with the Nano again** until
  it is reflashed.
- **How it's reached:** holding **Home ~3.3 s while on** (or idle / pairing timeout / low battery) → power-down
  states. Line P0.00 (probably charger/USB detect, low–med confidence) picks state 5 vs 6.
- **Proposed fix (not applied, untested):** in `tools/make_locked_rom.py`, NOP the `bl 0x3ab0` at
  `0x3908` (4 bytes → `00 bf 00 bf`). State 6 then leaves flash untouched and the `ABCDEF` record stays.
  **Recovery if it happens:** reflash `speedlink_locked_ABCDEF.bin`.

## Not yet defined in Ghidra (worth `create_function` in a later pass)
`0x1474`–`0x19ba` (Gazell TX-attempt / ack-timeout), `0x1a08`, `0x1faa`, `0x26a2` (TIMER2 IRQ),
`0x29c`, `0x3984` (SYSTEMOFF), `0x38bc` (latch-off), `0x3ab0` (bond save), `0x57a8` (NVMC word
write), `0x50d0` (WDT IRQ), `0x5120`, UART code `0x5180`–`0x524a`. Details are in the sections below.

---


## 1. `0x00c8`–`0x0db8`: startup helpers + Gazell API layer

Two layers sit in this range:
- **Public API wrappers** (0x18c..0x766). Each maps an API enum to a raw value and returns `1`/`0`. Most refuse with `0` while Gazell is enabled (`*(*0x20000140)+0x19 != 0`, i.e. state byte `0x200003b5`). Callers are `FUN_00004700` / `FUN_00004f50`, the two app setup paths.
- **Internal setters** (0x766..0xc92). They write the RAM shadow (`0x20000368` params, `0x20000388` radio cfg) and, where it applies, the RADIO register directly.

| Address | Suggested name | What it does (1-2 lines) | Key evidence (registers/RAM/callers) | Confidence |
|---|---|---|---|---|
| 0x00c8 | `thunk_main` (keep thunk) | Tail-calls `0x5a50` through the literal at `0xcc`. | Only caller `FUN_00002e38`, which Reset_Handler reaches via the C-runtime entry at `0xc1`. So `0x5a50` is most likely `main`. | med |
| 0x00d4 | `DelayLoop_a` | Busy-wait: counts `r0` down to 0. | Caller `FUN_00003568` | high |
| 0x00f4 | `DelayLoop_b` | Same code as 0xd4 (duplicate copy). | Caller `FUN_00005b98` | high |
| 0x0134 | `DelayLoop_c` | Same code as 0xd4 (duplicate copy). | Caller `FUN_00002744` | high |
| 0x0154 | `Reset_Handler` (keep) | Sets bits 0..1 in POWER.RAMON `0x40000524` and RAMONB `0x40000554` (all RAM blocks on), calls SystemInit `0x4edc`, then jumps to the C-runtime entry `0xc1` (→ `0x2e38` → `main`). | pool `0x17c..0x188` | high |
| 0x018c | `nrf_gzll_set_xosc_ctl` | Accepts 0/1 (AUTO/MANUAL) and stores it via `0xc32` in params+0x1c. App passes 1. | Read by `FUN_000019ba` (start/stop path): when +0x1c==0 it starts HFCLK (CLOCK `0x40000000`/`0x40000100`) and busy-waits. | med |
| 0x01a6 | `gzll_set_crc_length` (no stock nrf_gzll equivalent) | Enum 0/1/2 = off / 8-bit / 16-bit → `0x766`. Out-of-range values assert. App passes 2 (16-bit CRC). | → `0x766`, assert code `0x2028e` | high |
| 0x01d0 | `nrf_gzll_set_datarate` | Enum 0=250k→RADIO.MODE 2, 1=1M→0, 2=2M→1, then `0x64c8` writes MODE and the OVERRIDE regs. App passes 0 (250 kbps). | enum remap matches nRF51 MODE encoding | high |
| 0x01f8 | `nrf_gzll_set_tx_power` | Enum 0..6 → +4, 0, -4, -8, -12, -16, -20 dBm (`4,0,0xFC,0xF8,0xF4,0xF0,0xEC`) → `0x655c` (radio cfg+0x10 and RADIO.TXPOWER). App passes 0 (+4 dBm). | exactly matches `nrf_gzll_tx_power_t` | high |
| 0x023a | `nrf_gzll_set_base_address_length` | Enum 0/1/2 → 2/3/4 bytes → `0x920` (PCNF1.BALEN). App passes 2 (4-byte base, 5-byte address). | → `0x920` | high |
| 0x027a | `nrf_gzll_set_channel_table` (one-entry wrapper) | Stores the channel byte at `0x2000013e`, then calls `FUN_00001112(&ch, 1)` (the real set_channel_table, which stores ptr+size). Refused while enabled. | Callers `0x48c0`, `0x4700`, `0x4f50`; already documented as "set channel" | high |
| (0x029c) | `gzll_event_callback` (**not a Ghidra function**) | Thumb pointer `0x29d` is passed to Gazell init (`0x362` → `0xdb8` → `0x2c2c` stores it). Switches on an event type < 6 and calls `0x63c8` / `0x101e`. | literal `0x5c0` = `0x0000029d` | med |
| 0x0362 | `nrf_gzll_init(mode)` | Calls core init `0xdb8(cb=0x29d)` and saves the state pointer at `0x20000140`. Default channel table = {10}, size 1. Mode 0 (DEVICE) → core mode 1, mode 1 (HOST) → core mode 2, via `0xd8e`. Default params: BALEN 4, TXPOWER 0 dBm, MODE 2M, 8-bit CRC, xosc AUTO, `0x1168(1)`. | Callers `0x4700(0)`, `0x4f50`; writes `0x2000013c..0x2000013f` | high |
| 0x03e0 | `nrf_gzll_enable` (wrapper) | Calls `0xf18`. That function reconfigures the radio (`0x936`), sets enabled flag `0x200003b5`=1 and kicks `0x19ba`. | Caller `FUN_00004504` (app "start radio") | high |
| 0x03e8 | `nrf_gzll_disable` (wrapper) | Calls `0xf5e` (sets a disable request at state+2 if enabled), then `0xf84`. If now disabled → `0x6398` (empty stub), otherwise `0xf5e` again. **Not a wait loop.** | Callers `0x44fc`, `0x48a0` (switch address), `0x48c0` (switch channel) | high |
| 0x0402 | `nrf_gzll_is_enabled` | Returns `!0xf84()`. `0xf84` returns 1 when enabled flag `0x200003b5`==0. | Caller `0x4504` | high |
| 0x040e | `gzll_add_packet_to_tx_fifo(pipe, data, len, no_ack)` | Entry stub that checks pipe ≤ 7, then falls through into `0x416`. | Caller `FUN_000048d8` (app TX) | high |
| 0x0416 | (body of 0x40e) | Checks len ≤ 32, that TX is allowed (`0x10a6`) and FIFO counts (`0x1096`/`0x109e` ≤ 2). Takes a buffer (`0x100a`), sets buf[0]=len and buf[1] bit0 = ack-request (set when `no_ack`==0), memcpy (`0x2ddc`), queues it (`0x1032`). | buf[1] bit0 = ESB S1 "ack requested" bit (see PCNF0 below) | high (no_ack: med) |
| 0x04a0 | `nrf_gzll_fetch_packet_from_rx_fifo(pipe, data, *len)` | If RX count > 0: peek (`0x1066`), `*len = buf[0]`, copy payload, free (`0x101e`). **No callers (dead code).** | assert `0x200e2` | med |
| 0x055a | `nrf_gzll_set_base_address_0` | Refused while enabled, then `0x8be`. | Callers `0x4700`, `0x48a0` (switch to an ID's address), `0x4f50` | high |
| 0x05d8 | `nrf_gzll_set_address_prefix_byte(pipe, prefix)` | pipe < 8, refused while enabled, then `0x7ca`. App: `(0, 0xE7)`. | → `0x7ca` | high |
| 0x05fc | `nrf_gzll_get_address_prefix_byte(pipe, *out)` | `*out = 0x10fa(pipe)`, which reads params+0x28+pipe. **No callers.** | `0x10fa` pool `0x1408` = `0x20000368` | high |
| 0x060a | `nrf_gzll_set_rx_pipes_enabled` | `0x1144(v)` writes params+0x10 (core init default `0xFFFFFFFF`). App passes 1 (pipe 0 only). | RAM `0x20000378` | med-high |
| 0x061c | `nrf_gzll_set_timeslot_period` | Refused while enabled, then `0xc92` (params+0x04 u32). Default 600 (matches Gazell's 600 µs default). App passes **2000**. | RAM `0x2000036c` | high |
| 0x063c | `nrf_gzll_set_max_tx_attempts`? | Refused while enabled, then `0xc44` (params+0x1a, **u16**). Default 16. App passes **1**. That fits the app doing its own retries (one packet per state-machine call). | RAM `0x20000382`; only writes are visible as xrefs | low-med |
| 0x0710 | unclear (`gzll_set_flag_46e`) | `0xc2a(1)` → `0x1f70(1)` sets byte `0x2000046e` (read by `FUN_00001d36` on the device mode-switch path) and sets `0x2000013f`=1. Possibly an ack-payload/sync option. | Callers `0x4700`, `0x4f50` | low |
| 0x073e | `gzll_assert_counter_inc` | `++*(u32*)0x20000138`. | Only caller `HandleGazellAssert` | high |
| 0x0766 | `gzll_radio_set_crc(len)` | Stores len at radio cfg+0x11 (`0x20000399`), then sets CRCCNF.LEN. 1 → POLY `0x107`, INIT `0xFF`. 2 → POLY `0x11021`, INIT `0xFFFF` (CRC-16-CCITT, as nRF24). 3 → INIT `0xFFFFFF`, POLY 0. Other → assert. | RADIO `0x40001534/538/53C` | high |
| 0x07ca | `gzll_radio_set_prefix(pipe, byte)` | Stores at params+0x28+pipe and writes the **bit-reversed** byte into PREFIX0 (pipes 0-3) or PREFIX1 (pipes 4-7). | RADIO `0x524/0x528` | high |
| 0x08be | `gzll_radio_set_base0(u32)` | Stores at params+0x20 and writes BASE0 with each byte bit-reversed. | RADIO `0x4000151C` | high |
| 0x0920 | `gzll_radio_set_base_length(n)` | params+0x1d = n; PCNF1.BALEN (bits 16-18) = n. | RADIO `0x40001518` | high |
| 0x0936 | `ConfigureRadioAddressChannel` (keep; better: `gzll_radio_configure`) | Full radio (re)configure, steps below. | refs listed below | high |
| 0x0c2a | `gzll_set_flag_46e` (thin wrapper) | `0x1f70(r0)` → byte `0x2000045c+0x12`. | Caller `0x710` | med |
| 0x0c32 | `gzll_params_set_xosc_ctl` | params+0x1c (`0x20000384`) = byte. | Callers `0x18c`, `0x362` | high |
| 0x0c44 | `gzll_params_set_u16_1a` (max_tx_attempts?) | params+0x1a (`0x20000382`) = u16. | Caller `0x63c` | med |
| 0x0c92 | `gzll_params_set_timeslot_period` | params+0x04 (`0x2000036c`) = u32. | Caller `0x61c` | high |
| 0x0c9e | `gzll_apply_mode_change` | Applies the requested mode (state+1) when it differs from the current one (state+0); details below. | RAM `0x2000039c/9d`, `0x200003b8..c8`, `0x200003d0`, PPI `0x4001F508/514` | med |
| 0x0d8e | `gzll_request_mode(mode)` | Critical section (cpsid/cpsie). If mode ≠ current: state+1 = mode. If disabled, apply now (`0xc9e`); if enabled, defer via `0x19ba`. | Caller `0x362` | high |
| 0x0db8 | `nrf_gzll_core_init(event_cb)` | Core init: zeroes state, sets NVIC priorities, loads the Gazell defaults and configures the radio; full sequence below. | refs listed below | high |

**0x0936 `ConfigureRadioAddressChannel` sequence:**
1. PPI CHENCLR=3 (`0x4001F508`), CH0.TEP=0.
2. Power-cycles the RADIO (`0x40001FFC` POWER = 0 then 1).
3. PCNF0: LFLEN=6, S1LEN=3, S0LEN=0. PCNF1: MAXLEN=32, STATLEN=0, BALEN from params+0x1d, ENDIAN=big, WHITEEN=0.
4. Clears pending RADIO IRQ (ICPR `0xE000E280` = 2).
5. PPI CH1: EEP = RADIO EVENTS_ADDRESS (`0x40001104`), TEP = `FUN_0000269a()` (a timer task address), CHENSET=3.
6. `0x20000148 = FUN_000027b6(0x200003b8)`.
7. Loads BASE0/BASE1/PREFIX0-1 (bit-reversed) from params, TXPOWER from `0x20000398`, CRC from `0x20000399`.
8. MODE plus OVERRIDE0-4 (`0x40001724..0x734`) from `0x2000039a`.

**0x0c9e `gzll_apply_mode_change` sequence:**
- If the current mode is 0, reconfigures the radio first (`0x936`).
- Leaving device mode: runs the `0x1ea2` / `0x1c20` / `0x1d36` teardown, PPI CHENCLR=3, `0x2744`, clears `0x200003b8..c8`.
- Loads a timer value into `0x200003d0` from params+0x08 or params+0x0c, depending on the mode.
- Sets current = requested, then calls `0x2c50`.

**0x0db8 `nrf_gzll_core_init` sequence:**
1. Zeroes state `0x2000039c..0x200003b5` and `0x200003b8..0x200003d4`.
2. Calls `0x2554`, `0x2c2c(cb)` (stores the callback and clears SWI0 pending), `0x1ac4`, `0x2d60(0)`, `0x1f90(0x200003d0)`.
3. NVIC priorities: RADIO (IPR0 byte1) = 0, TIMER2 (IPR2 byte2) = 0, SWI0 (IPR5 byte0) = `0x40` (prio 1).
4. Loads defaults:
   - params+0x00 = `0x69` (magic/"initialised")
   - +0x04 = 600, +0x08 = +0x0c = +0x10 = `0xFFFFFFFF`, +0x14 = 0
   - +0x18 = 1, +0x19 = 1, +0x1a = 16, +0x1c = 0, +0x1d = 4
   - base0 `E7E7E7E7`, base1 `C2C2C2C2`, prefixes `E7 C2 C3 C4 C5 C6 C7 C8`
   - radio cfg: txpower 0, crc 2, mode 1 (2M)
5. Mode 3 → 1 (device), then `0x936`.
6. ICPR: clears pending TIMER2 (`0x400`) and SWI0 (`0x100000`).
7. Returns the state pointer `0x2000039c`.

### Subsystem notes
- **Call flow (app setup `FUN_00004700`):**
  1. `0x362 init(DEVICE)`
  2. `0x18c xosc(1)`
  3. `0x60a rx_pipes(1)`
  4. `0x5d8 prefix(0, 0xE7)`
  5. `0x4770` (build base from ID) → `0x55a base0`
  6. `0x710`
  7. `0x23a base_len(2)` = 4 bytes
  8. `0x1f8 txpwr(0)` = +4 dBm
  9. `0x1d0 rate(0)` = 250 kbps
  10. `0x27a channel`
  11. `0x1a6 crc(2)` = 16-bit
  12. `0x63c(1)`
  13. `0x61c timeslot(2000)`
  14. `0x4504` (enable via `0x3e0`)
- **New facts worth recording:**
  - **Link setup.** TX power is **+4 dBm** (max), CRC is **16-bit CCITT** (poly `0x11021`, init `0xFFFF`), the Gazell timeslot period is **2000 µs** (default 600), and only RX pipe 0 is enabled.
  - **Packet format = nRF24 Enhanced ShockBurst.** PCNF0 is LFLEN=6 / S1LEN=3 / S0LEN=0, i.e. the nRF24 Packet Control Field: 6-bit length, 2-bit PID, 1-bit no-ack. PCNF1 is big-endian, no whitening, MAXLEN 32. All address bytes (BASE0/1, PREFIX) are **bit-reversed** before they go into RADIO registers, which makes the on-air bytes nRF24-compatible.
  - **TX packet buffer layout:** byte0 = length, byte1 = S1 (bit0 = 1 → ack requested, cleared when `no_ack`), payload from byte2. `0x40e` takes a 4th `no_ack` argument. Stock `nrf_gzll_add_packet_to_tx_fifo` takes 3 arguments, and stock nrf_gzll exposes no CRC-length setter. This library is an extended or early variant of nrf_gzll, so names in the table are best-fit, not exact.
  - **The app's 250 kbps choice is a runtime setting.** The literal OVERRIDE0-4 values per data rate are hardcoded (not read from FICR):
    - common: OVERRIDE0 `0x78005000`, OVERRIDE1 `0x5400004E`
    - 1M: `0x600C8003`, `0x00726422`, OVERRIDE4 `0x820F423E`
    - 2M: `0x600C8002`, `0x00666411`, `0x828FC0DE`
    - 250k: `0x600C8008`, `0x00726488`, `0x820F423E`
  - **Interrupt priorities:** RADIO and TIMER2 at priority 0, SWI0 (callback dispatch) at priority 1.
- **RAM structures:**
  - **`0x20000134` wrapper block:** +4 (`0x20000138`) assert counter; +8 (`0x2000013c`) u16=0; `0x2000013e` one-entry channel table; `0x2000013f` flag; +0xc (`0x20000140`) pointer to the Gazell state (`0x2000039c`).
  - **`0x2000039c` Gazell state:** +0 current mode (1=device, 2=host, 3=uninit); +1 requested mode; +2 disable-requested; +0x19 (`0x200003b5`) **enabled flag**.
  - **`0x20000368` params**, beyond the known fields: +0x00 magic `0x69`; +0x04 timeslot period; +0x08 / +0x0c per-mode timer values (default `-1`); +0x10 rx_pipes_enabled; +0x1a u16 (max_tx_attempts?); +0x1c xosc_ctl.
  - **Radio cfg (`0x20000388`):** +0x10 txpower, +0x11 crc length, +0x12 RADIO.MODE.
- **Possible mislabel outside this range:** `0xc9e` calls the function already named `AddPacketToTxFifo` (`0x2c50`) as the last step of a mode switch. The real public add-to-TX-FIFO is `0x40e`/`0x416`, so `0x2c50` is probably something else (e.g. "start timeslot/radio for current mode"). Worth re-checking.
- **Unnamed code in this range:** `0x29c` is the event callback handed to Gazell init but is not defined as a function in Ghidra (read-only here, so not created).
- **Dead code:** `0x4a0` (fetch RX) and `0x5fc` (get prefix) have no callers. The app never reads ack payloads through this API, or it does so another way.

---

## 2. `0x0f18`–`0x2a10`: Gazell link-layer core

Everything below was read-only analysis: Ghidra decompilation, literal-pool reads, local `arm-none-eabi-objdump` of regions with no function defined, and the RAM snapshot `firmware_dump/0x20000000_0x20008000_RAM.bin` for live values.
"API" means the public nrf_gzll call that the function most likely implements. The wrappers at 0x100a–0x1066 disable IRQs around the call (`cpsid`/`cpsie`), which is the old nrf_gzll pattern.

| Address | Suggested name | What it does | Key evidence | Conf |
|---|---|---|---|---|
| 0x0F18 | `nrf_gzll_enable` | If not enabled: configures the radio, asserts that a channel table is set, sets `enabled=1` and starts the timeslot engine. | Checks and sets `0x2000039c+0x19` (`0x200003b5`). Asserts `0x200003d0+4/+8` != 0 (channel table size and ptr). Calls ConfigureRadioAddressChannel, `0x2d7e`, `0x2d6a(0)`, `0x19ba`. Caller `0x3e0`. | high |
| 0x0F5E | `nrf_gzll_disable` | If enabled and no disable is pending, sets `disable_pending` (`state+2`) and kicks the engine. The actual teardown runs later in `0x1a08`. | IRQ lock; `0x2000039e=1`; calls `0x19ba`. | high |
| 0x0F84 | `nrf_gzll_is_disabled` (or `!is_enabled`) | Returns 1 if the `enabled` byte is 0. | `0x200003b5`. Callers `0x3e8`, `0x402`. | high |
| 0x1004 | `gzll_get_state_byte0` | Returns byte 0 of the Gazell state struct `0x2000039c`. Probably the mode (device/host); the snapshot holds 1. | No callers found. | low |
| 0x100A | `gzll_alloc_packet_buffer_locked` | IRQ-locked wrapper: `0x1b2a` → `0x2260` takes a buffer from the free pool. | Caller `0x416`. | med |
| 0x101E | `gzll_free_packet_buffer_locked` | IRQ-locked wrapper: `0x1d26` → `0x22bc` returns a buffer to the pool. | Caller `0x4a0`. | med |
| 0x1032 | `nrf_gzll_add_packet_to_tx_fifo` | IRQ-locked: `0x1f00(pipe, buf)` pushes the buffer. On success, if enabled and no disable is pending, kicks the engine (`0x19ba`). Returns 1/0. | `0x2000039e`, `0x200003b5`. Caller `0x416`. | high |
| 0x1066 | `nrf_gzll_fetch_packet_from_rx_fifo` | IRQ-locked: `0x1f5c(pipe)` pops RX FIFO number `pipe+8`. | Caller `0x4a0`. | high |
| 0x1096 | `gzll_tx_fifo_nonempty?` | Thunk → `0x1d2e` → `0x63e0(pipe)`. `0x63e0` is a "FIFO has packets" test, used per pipe in `0x1be0`. | Caller `0x416`. | med |
| 0x109E | `gzll_rx_fifo_nonempty?` | Thunk → `0x1b32` → `0x63e0(pipe+8)`. | Callers `0x416`, `0x4a0`. | med |
| 0x10A6 | `gzll_fifo_check_63d4` | Thunk → `0x1ef8` → `0x63d4`. `0x63d4` gates the TX push in `0x1f00`; probably a "fifo not full"/valid check. | Caller `0x416`. | low |
| 0x10FA | `nrf_gzll_get_address_prefix(pipe)` | Asserts `pipe<=7` and returns `params+0x28[pipe]`. | Params `0x20000368`. In the snapshot, `+0x28` = `E7 C2 C3 C4 C5 C6 C7 C8` (Gazell default prefixes). Caller `0x5fc`. | high |
| 0x1112 | `nrf_gzll_set_channel_table(table, size)` | Asserts both are non-zero, stores ptr at `0x200003d8` and size at `0x200003d4`, then sets the channel index to 0. | `0x200003d0` struct. Callers `0x27a` (the known "one-entry channel table" path) and `0x362`. Snapshot: size 1, table `0x2000013e`. | high |
| 0x1144 | `gzll_set_param_0x10` | `params+0x10 = arg` (`0x20000378`). In the snapshot it is 1. Which nrf_gzll setter this is (e.g. a timeslot or sync setting) is unclear. | Caller `0x60a`. | low |
| 0x1168 | `gzll_set_rssi_enable` | Asserts the radio driver is initialised (`0x20000148`), then sets radio-cfg `+0x14` (`0x200003cc`). The radio driver uses this byte to arm PPI ADDRESS→RSSISTART and read RSSISAMPLE. | `0x2940` and `0x2a10` test `cfg+0x14` before RSSI handling. Caller `0x362`. Snapshot = 1. | med |
| 0x1360 | **GazellTxSuccessCallback** (keep). More precisely: `gzll_device_radio_done_cb`, the ACK-received handler | Registered as radio-cfg callback `+0xc` (`0x200003c4` = `0x1361` in RAM). RADIO IRQ calls it after the ACK-RX window. If CRC is OK (`RADIO CRCSTATUS 0x40001400 == 1`, or `CRCCNF == 0`) and ACK length ≤ 32: stops the radio, completes the TX via `0x1c20`, and queues a TX-success event for the SWI0 callback with `{type=0, pipe, rssi, payload_in_ack (0/1), num_tx_attempts, num_channel_switches}`. Then saves the channel index and reloads timeslots-per-channel (in-sync / out-of-sync value). | `0x40001400`, `0x40001534`. Reads `0x200003a8`/`0x200003aa` (u16 counters). Writes `0x200003d0` from `params+8`/`+0xc`. Called through a pointer only; pointer loaded at `0x16a6`/`0x1708`/`0x1764`. | high |
| 0x19BA | `gzll_start_timeslot_engine` (kick) | If TIMER2 is idle: asserts `0x2d8a()==0` and schedules the timeslot callback `0x2d91` 30 µs from now. Unless `params+0x1c` is set, also writes CLOCK+0x514=1 (not documented for nRF51), starts HFCLK and waits for HFCLKSTARTED. Then starts TIMER2. | `0x40000000`/`0x40000100` HFCLK, `0x40000514`, `0x20000384`. Calls `0x25d6(0x2d91,30,0)` and `0x259c`. 5 callers (enable, disable, add-to-fifo, init). | high |
| 0x1AC4 | `gzll_link_state_init` | Initialises the packet-buffer pool (`0x21dc`) and zeroes the link state `0x200003dc`: per-pipe arrays, ack-armed bytes `0x2000014c[8]`, flags `0x2000046c/d`. Sets `0x2000046e=1`. | Caller `0xdb8` (Gazell init). | high |
| 0x1B2A | thunk → `0x2260` | Allocate a packet buffer. | | high |
| 0x1B32 | `gzll_rx_fifo_count(pipe)` | `0x63e0(pipe+8)`. | | med |
| 0x1BE0 | `gzll_select_next_tx_pipe` | If idle and no TX data is flagged yet, scans the 8 pipes round-robin (index `0x200003f0`). For the first pipe whose FIFO is non-empty it sets `tx_data_available` (`0x2000046c`) and `current_tx_pipe` (`0x200003ec`). | Callers `0x1c20`, `0x1d36`, `0x1f00`. | high |
| 0x1C20 | `gzll_device_tx_complete(success, remove)` | State must be 1 (TX) or 2. On success with a non-empty ACK payload, pushes the ACK buffer (`state+0x7c`) into RX FIFO `pipe+8` and returns 2; with an empty ACK returns 0; on failure returns 4. If `remove`, pops the sent packet from TX FIFO `pipe` and clears the per-pipe flags. Ends with `state=0` and re-selects the next pipe. | Link state `0x200003dc`; uses `0x232a` push and `0x23b6` pop. Callers `0x1360`, `0xc9e`. | high |
| 0x1CD6 | `gzll_get_current_pipe` | Returns `0x200003e0`. | | high |
| 0x1CDC | `gzll_get_current_packet` | Returns `0x200003e4` (the packet pointer handed to the TX event). | | high |
| 0x1D26 | thunk → `0x22bc` | Free a packet buffer. | | high |
| 0x1D2E | thunk → `0x63e0` | FIFO count/non-empty test. | | med |
| 0x1D36 | `gzll_host_handle_rx_packet` (PRX side) | Requires state 3 (RX). Drops duplicates by comparing `(crc24 \| PID<<24)` with the per-pipe last value at `0x200003dc+0x38+pipe*4`. Pushes the new packet into RX FIFO `pipe+8`. If an ACK payload was armed for the pipe, pops it from TX FIFO `pipe` (`*out_sent`) and peeks the next one (`0x23fe` → `*out_next_ack`). Returns 1/2/3/4. | `0x232a`, `0x23b6`, `0x23fe`, `0x22bc`. Flag `0x2000046e` = ack-payload policy. Callers `0xc9e`, `0x1a08` (flush on disable). | med-high |
| 0x1EA2 | `gzll_get_link_state` | Returns state byte `0x200003dc`. Values: 0 idle, 1 device TX, 2 device (waiting for ACK?), 3 host RX. | Callers `0x1360`, `0xc9e`, `0x1a08`. | high |
| 0x1EF8 | thunk → `0x63d4` | | | low |
| 0x1F00 | `gzll_tx_fifo_push(pipe, buf)` | If `0x63d4()` passes, `0x232a(buf, pipe)`, then `0x1be0`. Returns 1/0. | | high |
| 0x1F5C | `gzll_rx_fifo_pop(pipe)` | `0x23b6(pipe+8)`. | | high |
| 0x1F70 | `gzll_set_ack_payload_flag` | Writes `0x2000046e`. | Callers `0xc2a`, `0xdb8`. | low |
| 0x1F88 | **HandleGazellAssert** (keep) | Thunk to `0x73e`. The argument is an encoded `(module<<16)\|line` code, not a string (see notes). | 34 callers. | high |
| 0x1F90 | `gzll_channel_hop_init(cfg)` | Stores the channel-cfg pointer (`0x200003d0`) at `0x20000154` and zeroes the channel index `0x20000158` and slot counter `0x2000015c`. | Assert code `0x1002a`. Caller `0xdb8`. | high |
| 0x2176 | `gzll_set_channel_index(i)` | Asserts `i < cfg.size`, then writes `0x20000158`. | Assert code `0x100b9`. | high |
| 0x2190 | `gzll_get_channel_index` | Returns `0x20000158`. | | high |
| 0x2196 | `gzll_set_timeslot_counter(n)` | Asserts `n < cfg.timeslots_per_channel`, then writes `0x2000015c`. | Assert code `0x100c5`. | high |
| 0x21DC | `gzll_packet_pool_init` | Zeroes the 16 FIFO control triplets at `0x20000470`. Fills the 6 buffers of 34 bytes at `0x20000578` with `0xDE` and pushes them onto the free stack `0x20000560`; free count `0x20000160 = 6`. | | high |
| 0x2260 | `gzll_packet_buffer_alloc` | Pops from the free stack, writes `0xDEADDEAD` into the vacated slot, and asserts that the buffer is not duplicated and lies inside the pool. | Assert codes `0x300f6`, `0x3007d`. | high |
| 0x22BC | `gzll_packet_buffer_free(buf)` | Validates the buffer (not already free, in pool, slot == `0xDEADDEAD`) and pushes it back. | Assert codes `0x30085`/`86`/`88`. | high |
| 0x232A | `gzll_fifo_push(buf, fifo_id)` | Requires `fifo_id < 16` and a validated buffer. Returns 0 if the count is ≥3 (full), otherwise stores at the tail and returns 1. | Control `0x20000470[id*3]` = {count, tail, head}. Slot table `0x200004a0 + id*12`. | high |
| 0x23B6 | `gzll_fifo_pop(fifo_id)` | Returns the head buffer, or 0 if the FIFO is empty. | | high |
| 0x23FE | `gzll_fifo_peek(fifo_id)` | Returns the head buffer without removing it. | Assert code `0x300b7`. | high |
| 0x2554 | `gzll_timer2_init` | TIMER2: STOP, CLEAR, MODE=timer, BITMODE=16-bit, PRESCALER=4 (1 MHz, 1 µs ticks), INTENCLR=all. CAPTURE[1] then assert `CC[1]==0`. Clears and enables NVIC IRQ 10. Timer state `0x20000164={idle=1, late=0, busy=0}`, cb=0. | `0x4000A000..A510`; `0xE000E280`/`E100` bit 10. Caller `0xdb8`. | high |
| 0x259C | `gzll_timer2_start` | TIMER2 TASKS_START; `idle=0`. | `0x4000A000`. | high |
| 0x25CA | `gzll_timer2_is_idle` | Returns `0x20000164[0]`. | | high |
| 0x25D0 | `gzll_timer2_was_late` | Returns `0x20000164[1]`, which the TIMER2 ISR sets when the compare fired late or the counter wrapped. | | med |
| 0x25D6 | `gzll_timer2_schedule(cb, ticks, ref)` | One-shot: `CC[0] = ref_time + ticks` (16-bit) with INTENSET COMPARE0. `ref`: 0 = now (CAPTURE[1]), 1 = previous CC[0] (back-to-back slots), 2 = CC[2]. CC[2] is presumably a radio-event timestamp captured over PPI; PPI is set up outside this range. Asserts that the target is in the future. | `0x4000A540/544/548`, `0x4000A304/308`, `0x4000A140`. Assert codes `0x40073..0x400c9`. | high |
| 0x269A | `gzll_timer2_capture2_task_addr` | Returns `0x4000A048` (TIMER2 TASKS_CAPTURE[2]) as a PPI task endpoint. | Caller ConfigureRadioAddressChannel. | high |
| 0x2744 | `gzll_radio_stop` | RADIO: NVIC disable IRQ 1, INTENCLR=all, SHORTS=0, clears events, TASKS_DISABLE, RSSISTOP. Calls `0x134(n)`, where n depends on the previous radio state (6 / 2 / 1, purpose unclear). Resets radio state `0x20000644` (`op=3` none) and re-enables IRQ 1. | `0x40001000..0x40001308`, `0xE000E180/280/100`. Callers `0x1360`, `0x27b6`, `0xc9e`. | high |
| 0x27B6 | `gzll_radio_init(cfg)` | Saves `cfg` (`0x200003b8`) at `0x2000016c`. Sets PPI CH2 EEP = RADIO EVENTS_ADDRESS and TEP = RADIO TASKS_RSSISTART. Stops the radio, resets state, and returns the radio-state pointer `0x20000644`, which the caller stores at `0x20000148`. | `0x4001F520/524`, `0x40001104`, `0x40001014`. Caller ConfigureRadioAddressChannel. | high |
| 0x2940 | `gzll_radio_handle_disabled` | Called from the RADIO IRQ when an op finishes. `irq_count==1` (TX→RX-ACK path): state=4, done-counter++, SHORTS=3 (READY_START + END_DISABLE), INTENSET DISABLED. If RSSI is enabled, reads RSSISAMPLE into `state+0x16` and turns off PPI CH2. Then calls `cfg->cb_0xc` (= `0x1360`); if `+0x15` is set, reloads PACKETPTR. `irq_count==2`: full reset, then `cfg->cb_0x10`. | `0x40001548`, `0x4001F500/508`, `0xE000E200`. Assert codes `0xa02e7..`. | med-high |
| 0x2A10 | **RADIO_IRQHandler** (keep) | Radio state machine driven by `0x20000644` {[0] state, [1] op, +0x10 irq count, +0x18 done count}. The next state comes from the op table at `0x6c74` (16 bytes per op; +10 next state, +12 notify flag). Handles TX→RX turnaround (SHORTS / INTEN reprogramming, PPI CH2 RSSI) and calls the registered callbacks `cfg+8`/`+0xc`/`+0x10`; `0x2940` handles the end-of-op case. | `0x40001100..0x40001548`, `0x4001F504`, `0x2000016c`. | med |

### Code in range with no Ghidra function (not created, read-only)
- **0x26A2 = TIMER2_IRQHandler** (vector slot 0x68 = `0x26A3`). Disables COMPARE0, clears EVENTS_COMPARE[0], captures CC[1] and sets the `late` flag (late if `CC1 >= CC0+20`, with wrap handling around `0x4000`/`0xC000`). Clears busy and calls the scheduled callback.
- **0x269E** returns `0x4000A140` (TIMER2 EVENTS_COMPARE[0]), probably a PPI event endpoint.
- **0x1FAA = `gzll_timeslot_tick` / channel hop.** Increments the slot counter `0x2000015c`. When it reaches `cfg.timeslots_per_channel` it wraps and advances the channel index `0x20000158` modulo `cfg.size`.
- **0x2156 = `gzll_get_current_rf_channel`**: returns `table[idx]`.
- **0x1FD4..0x2154**: more channel/timeslot arithmetic (multiplies `timeslots_per_channel*(size-1)`); not analysed.
- **0x1A08 = disable completion.** Runs when `enabled` is set and a disable is requested. Stops TIMER2. Stops HFCLK (`0x40000004`) unless `params+0x1c` is set. Stops the radio, clears `enabled` and `disable_pending`, queues event type 5 (disabled) via `0x2c50`, clears PPI CH0+CH1 (CHENCLR=3), and flushes a pending host RX through `0x1d36`.
- **0x1180..0x1360**: several small getters (`bx lr`) plus routines at `0x1192`, `0x11a0`, `0x12c8`, `0x12e8`.
- **0x1474..0x19BA**: the tail of `0x1360` (switch case 2), plus device/host timeslot state-machine routines at `0x14e6`, `0x1584`, `0x15f0`, `0x1970`. These load `0x2d91` and `0x1361`, call `0x2156`, `0x1faa`, `0x25d6` and `0x2c50`, and are likely the TX-attempt/ACK-timeout logic. Worth creating functions for in a later pass.

### Subsystem notes
- **Layering.** Public API wrappers (0xF18–0x1168, IRQ-locked) → link state and FIFOs (0x1AC4–0x1F70, 0x21DC–0x23FE) → channel/timeslot counters (0x1F90–0x2196, 0x1FAA) → TIMER2 one-shot scheduler (0x2554–0x25D6, ISR 0x26A2) → low-level radio driver (0x2744–0x2A10, state `0x20000644`). Upward notifications go through radio-cfg callbacks (`cfg+0xc` = `0x1360`) and through `0x2c50`, which queues an event record for the SWI0 dispatcher at `0x2CC0`.
- **The name AddPacketToTxFifo (0x2C50, outside this range) looks wrong.** In this range it is called with 12-byte event records `{u8 type, u8 pipe, u8 rssi, u8 payload_in_ack, u32 packet, u16 tx_attempts, u16 channel_switches}`: type 0 = TX success (from `0x1360`), type 5 = disabled (from `0x1a08`). This matches `nrf_gzll_device_tx_success(pipe, tx_info)` and `nrf_gzll_disabled()`, and the queue is drained in SWI0. A better name would be `gzll_queue_callback_event`.
- **Packet memory.** 6 buffers × 34 bytes (`0x22`: length/flags + 32-byte payload, matching `NRF_GZLL_CONST_MAX_PAYLOAD_LENGTH` 32) at `0x20000578..0x20000643`. Free stack at `0x20000560` (6 ptrs, `0xDEADDEAD` = empty slot), free count at `0x20000160`.
- **FIFOs.** 16 FIFOs of depth 3: id 0–7 = TX/ACK-payload FIFO per pipe, id 8–15 = RX FIFO per pipe (pipe+8). Control bytes {count, tail, head} at `0x20000470`, slot pointers at `0x200004A0` (16×3×4).
- **Link state `0x200003DC`.** +0 state (0 idle / 1 TX / 2 / 3 RX), +4 current pipe, +8 current packet, +0xC ACK/RX buffer, +0x10 pipe with data, +0x14 round-robin index, +0x38[8] last `(crc|PID<<24)` per pipe for duplicate rejection, +0x7C RX buffer pointer, +0x80[8] per-pipe flag. Related: `0x2000014C[8]` "ack payload armed", flags `0x2000046C` (TX data available), `0x2000046D`, `0x2000046E` (ack-payload policy, default 1).
- **Gazell state `0x2000039C`.** +0 mode?, +2 disable_pending, +0xC/+0xE u16 tx_attempts / channel_switches, +0x10 saved channel index, +0x14 flag, +0x19 enabled.
- **Gazell params `0x20000368`** (from the RAM snapshot): +0 `0x69`, +4 `2000` (`0x7D0`; probably the timeslot period in µs — unconfirmed), +8/+0xC `0xFFFFFFFF` (timeslots-per-channel in-sync / out-of-sync, copied into `0x200003D0`), +0x10 1, +0x1C 1 (skips HFCLK start/stop in Gazell), +0x20 base0 `C6C2C1E7` (the pairing base `0xC1C2C6`, applied by the app), +0x24 base1 `C2C2C2C2`, +0x28 prefixes `E7 C2..C8`.
- **Channel cfg `0x200003D0`.** {timeslots_per_channel, size, table_ptr}. Snapshot: `{0xFFFFFFFF, 1, 0x2000013E}`, which confirms the app's single-channel table with hopping done above Gazell. With an infinite slot count, Gazell's own hopping (`0x1FAA`) never changes channel.
- **Radio cfg `0x200003B8`.** +0 PACKETPTR buffer (`0x20000622`), +4 `0x20000600`, +8/+0xC/+0x10 callbacks (only +0xC = `0x1361` is set), +0x14 RSSI enable (1), +0x15 reload-PACKETPTR flag.
- **Timing.** TIMER2 runs at 1 MHz with 16-bit compares. The engine starts by scheduling the slot handler `0x2D90` 30 µs after enable. CC[2] can serve as a reference point for back-to-back scheduling (mode 2) and is likely the radio-event timestamp for sync. PPI CH2 is RADIO ADDRESS → RSSISTART. PPI CH0/1 are set up elsewhere (cleared on disable).
- **Assert codes.** The argument to `HandleGazellAssert` is `(module_id<<16)|line`: module 0x01 = channel/timeslot, 0x03 = FIFO and buffer pool, 0x04 = TIMER2, 0x09 = gzll core, 0x0A = radio driver. With these, `0x73E` could be traced to identify which check failed.
- **Possible undocumented register.** `0x19BA` writes 1 to `0x40000514` (CLOCK/POWER block) before HFCLKSTART. This offset is not in the nRF51 register map; it may be an early-silicon workaround.

---

## 3. `0x2c2c`–`0x4504`: Gazell dispatch end, inputs, report builder, power, bond record

Read-only analysis (Ghidra decompile + literal pools). "word" = u32. `BTN` = combined debounced
button word at `0x20000034` (see notes).

### Function table

| Address | Suggested name | What it does | Key evidence | Conf. |
|---|---|---|---|---|
| 0x2c2c | `Gzll_CallbackQueue_Init` | Stores the callback fn pointer, clears the 10-entry event queue, enables SWI0 IRQ in NVIC. | `*0x20000668=fn`, clears `0x200006e8/ec`, `NVIC_ISER(0xE000E100)=0x100000` (IRQ20=SWI0). Caller Gazell init `0xdb8`. | high |
| 0x2c50 | `AddPacketToTxFifo` (keep; really "queue Gazell event + pend SWI0") | Copies a 12-byte event into the 10-slot ring at `0x2000066c`, bumps count, pends SWI0. | ring idx `[0x1f]`, count `0x200006ec` (assert if >9), `NVIC_ISPR(0xE000E200)=0x100000`. Callers `0xc9e`, `GazellTxSuccessCallback`. | high |
| 0x2cc0 | `SWI0_GazellCallbackDispatch` (keep) | SWI0 ISR: drains the event ring, calling the stored callback with 3 words per event, IRQs masked around dequeue. | same ring `0x20000668..`, indirect call `*0x20000668`. | high |
| 0x2d60 | `Gzll_SetTxPowerBytes` (unclear) | Writes the same byte to `0x20000170/171/172`. | Called from Gazell init `0xdb8`. | low |
| 0x2d6a | `Gzll_SetParam171` | Asserts arg ≤1, stores to `0x20000171`. | caller `0xf18`. | low |
| 0x2d7e | `Gzll_GetParam170` | Returns byte `0x20000170`. | caller `0xf18`. | low |
| 0x2d8a | `Gzll_GetParam171` | Returns byte `0x20000171`. | caller `0x19ba`. | low |
| 0x2db0 | `udiv32` | Software 32-bit unsigned divide (shift-subtract). | pure arithmetic; callers `0x526c`, `0x6350`. | high |
| 0x2ddc | `memcpy` | Word-copy if both aligned, then byte copy. | callers `0x416`, `0x4a0`, `0x4960`. | high |
| 0x2e24 | `ReadLE24` (keep doc name) | Reads a 3-byte LE ID (loop reads 4 bytes, top one shifted out by caller usage). | callers `0x4794`, `0x483c`. | high |
| 0x2e38 | `__scatterload` / C runtime init | Runs the region table `0x6ca4..0x6cc4` (copy/zero/decompress RW data), then jumps to `main` (`0x5a50` via thunk `0xc8`). | caller `Reset_Handler`. | high |
| 0x2e5c | `__decompress_rle` | ARM-linker RLE decompressor for initialised RW data (nibble lengths, literal + zero runs). | called through region table. | high |
| 0x2e98 | `ADC_ConfigRatiometric` | ADC CONFIG ← table `0x6bc4` {RES=10-bit, INPSEL=AIN×1/3, REFSEL=VDD×1/3} via `0x5b38`; INTENCLR=1. | `0x5b38` packs RES/INPSEL/REFSEL into `0x40007504`; writes `0x40007308`. Callers main, battery. | high |
| 0x2eb8 | `ADC_ConfigVBG` | Same, table `0x6bcc` {RES=10-bit, INPSEL=1/3, REFSEL=VBG 1.2 V} → absolute (battery) measurement. | `0x6bcc` refsel=0. Caller `0x33f8`. | high |
| 0x2edc | `ADC_Read(psel)` (as documented) | Sets PSEL, ENABLE, START, poll BUSY, return RESULT, clear END. | `0x40007500/04/08`, `0x40007000/100/400`. | high |
| 0x2f28 | `Mode_UpdateSwitchAndHome` | Per-tick: LED pattern ← `0x2fd4`. In **streaming (state 4)**: debounces the X/D switch (BTN bit 0x800000, >10 ticks) into `0x2000010d`; on change sets `0x2000010f=1`; in D-mode a fresh Home press (BTN 0x10000) toggles `0x2000010f`. In **pairing (state 1)**: holding Home 250 ticks sets `0x20000114=0x00ff`, `0x20000111=1` and **clears the bonded flag `0x20000007`** (forget host). | reads `0x20000005` state, `0x20000034/38` cur/prev BTN; struct `0x2000010c`. Caller main `0x5a50`. | high |
| 0x2fd4 | `Mode_GetLedMask` | Returns LED mask: `0xF` if `0x20000110`≠0; `1` in X mode; in D mode `5` if `0x2000010f`==0 else `1`. Stored to `0x20000028`. | reads `0x2000010d/0f/10`. | high |
| 0x2ffc | **`BuildInputReport`** | Builds the report at **`0x200001a0`** (the 19-byte buffer `FUN_00004514` sends, `DAT_000046fc=0x200001a0`) in one of 3 layouts by mode. Layout details in notes. | calls `0x360c` (turbo-filtered buttons → `0x20000120`), `0x3f48` (hat), `0x48e8` (clear), `0x49d8` (digital remap); reads sticks `0x2000003c`, pressures `0x200001e4`. Caller input task `0x4bb0`. | high |
| 0x33c8 | `Mode_Init` | Zeros mode/turbo state: `0x20000110/11/12`, `0x20000116`, `0x20000120`, `0x20000124/126`, `0x2000011e`. | caller main. | high |
| 0x33f8 | `Battery_Update` | States 1–3: low-pass AIN1 (`ADC_Read(2)`) into `0x2000008a`, classify level 3–6 (thresholds 0x289/0x29d/0x2b9), level 7 if GPIO IN P0.30 & P0.15 high; level must be stable 200 ticks. State 4: every 20 ticks takes 4 VBG-referenced AIN1 samples, classifies 1/2/3, keeps a 4-deep history `0x20000090..93`, lowers `0x20000084`. | ADC psel 2 = AIN1 (P0.27); `0x50000510`; struct base `0x20000078` (+0xc level, +0xd raw level). Caller LED task `0x43c0`. | med |
| 0x3568 | `Battery_InitialMeasure` | Boot: averages 17 AIN1 samples (1000-loop delay each), sets initial level 3/4/5 in `0x20000084/85`, clears counters/history. | `0x200000_84..93`, thresholds `0x2b9/0x29d`. Caller main. | med |
| 0x360c | `Turbo_Apply` | Turbo feature: while button P0.15 (BTN bit 0x20000) is held, newly pressed buttons in mask `0xFC06` toggle their turbo bits (`0x20000124` / `0x20000126` = two turbo sets, `0x2000011e` = active mask). Phase counter `0x2000011c` (0..2) blanks turbo buttons 2 of 3 ticks. Sets `0x2000011d`=1 if any turbo button held. Returns filtered button word. | reads `0x20000034/38`; mask lit `0xfc06`. Caller `0x2ffc`. | med |
| 0x36d8 | `Scale100_div256` | `x*100>>8` (percent of 255). | caller `0x4b78`. | med |
| 0x36e0 | `ScaleToU16(hi, lo, v)` | Returns `(v-lo)*65536/(hi-lo)` clamped (0 below lo, 0xFFFF above hi); 16-step binary long division. | callers mux scan, stick scan. | high |
| 0x3724 | `IdleTimer_Check` | In streaming: resets idle counter `0x20000024` on any button (`BTN & 0x9FFFF`), turbo activity (`0x2000011e`), or stick movement >±10 vs snapshot `0x20000044[4]` (and updates snapshot). At 0xB786 sets `0x2000000c|=1`, at 0xB786+18 returns 2 (sleep). Returns 3 if `0x2000000d` (host sleep request from step-4 ack). Not streaming: counter `0x20000020` > 0xDAC → return 1 (pairing timeout). | lits `0x37d4..0x3808`; only when `0x20000068` ∈ {2,4}. Caller power task `0x4a54`. | high |
| 0x380c | `PowerButton_Check` | If `0x2000011a`==2 and Home held: counter `0x2000006a`; >0x12D sets `0x2000000c|=2`, >0x13F returns 1 (power-off by long Home press). Returns 2 if battery level `0x20000084`==1 (critical). | caller `0x4a54`. | med |
| 0x3874 | `P0_00_Debounce` | Debounces BTN bit 0x100000 (P0.00, active-low): 80 ticks to assert, 30 to release; stable value at `0x20000065`. Probably charger/USB-present sense (reads "stuck low" on the bench). | struct `0x20000064..67`. Caller `0x4a54`. | low |
| 0x3a78 | `BondRecord_Load` (as documented) | Reads N words from last page+4, returns 1 if magic `0xAA558877` follows. | FICR `0x10000010/14`. | high |
| 0x3c0c | `MuxScan` (extend doc) | 10 analog button channels on AIN0 + 2 triggers on AIN2/AIN3, each auto-calibrated into a **0..255 pressure byte** at `0x200001e4[12]`; any nonzero pressure ORs its bit into BTN. See notes for channel→bit map. | P0.12/P0.13 (table `0x6c2e`) + P0.8 for L1/R1; selects P0.09/10/11; PIN_CNF[9],[10]=output (P0.10 taken from the X/D switch); max/min `0x200001b4/0x200001cc`, trigger max/min `0x20000070/74`. | high |
| 0x3e7c | `DirectButtonScan` (extend doc) | Re-sets P0.10 PIN_CNF=0xC (input+pull-up) then reads 9 active-low pins → raw `0x2000002c` (prev `0x20000030`); 3-sample majority debounce writes **all** of BTN `0x20000034` (prev copy `0x20000038`); mux scan then ORs into it. | `0x50000728`, `FUN_6444`. Callers `0x4bb0`, `0x4cd0`. | high |
| 0x3f48 | `DpadToHat` | BTN dpad bits → hat 0..7 (0=N … 7=NW), 0xF=centre. Up 0x10, Right 0x20, Down 0x40, Left 0x80. | caller `0x2ffc`. | high |
| 0x3f80 | `StickScan` (extend doc) | 4 axes AIN4..7 (table `0x6c28`), sum of 4 samples, tracks max `0x20000054`/min `0x2000005c` around centre `0x2000004c`, ±200 dead-zone, writes **16-bit** axes to `0x2000003c[4]`. X mode: signed int16 (Y axes 1,3 inverted). D mode: unsigned, centre 0x8000. | reads `0x2000010d`, `0x20000110`; `0x36e0`. Caller `0x4bb0`. | high |
| 0x4074 | `GPIO_Init` | PIN_CNF: P0.7, P0.8, P0.11, P0.16 outputs (P0.7 cleared); P0.17–20 outputs (high drive) set high = LEDs off; inputs+pull-up: P0.0, P0.10, P0.14/15, P0.21–23, P0.28/29, P0.30. | `0x50000700+4n`, OUTSET byte `0x5000050a=0x1e`, OUTCLR `0x80`. Caller main. | high |
| 0x40ec | `Input_InitState` | Clears BTN/raw words, resets mux calibration (max 0xAF0, min 0x800, pressure 0) for 12 channels, trigger cal (0xE66 / 2000). | `0x2000002c..38`, `0x200001b4/cc/e4`, `0x20000070/74`. Caller `0x492c`. | high |
| 0x4158 | `GetOwnId` (as documented) | own ID = (DEVICEID0^DEVICEID1)&0xFFFFFF → `0x20000018`. | FICR `0x10000060/64`. | high |
| 0x4174 | `Pairing_Reset` (as documented) | state=1, pairing address, LFSR seed = own ID, clears counters, flags `0x2000000c..0e`, `0x20000094/95`, **`0x20000110`=0**. | | high |
| 0x41c4 | `BondRecord_Apply` | Loads record; valid → host ID `+0x18`, bonded `+3`, `0x2000000b`, `0x2000011a` (rec+8 b2), `0x2000002a` (rec+0xC b0); top byte ≠0xAA → OUTSET P0.16 and `0x2000011a`=2. Invalid → defaults. Always `0x2000010f`=1. **Initial X/D mode `0x2000010d` = GPIO IN P0.10** (1 = high = D). Strict-window timer `+0xC`=300 when bonded. | `0x50000508/510`. Caller main. | high |
| 0x426c | `Stick_CalibrateCentre` | Calls `0x42b0`, then max = centre+0x5A3, min = centre−0x5A3, output and idle snapshot = 0x200. | `0x2000004c/54/5c/3c/44`. Caller `0x492c`. | high |
| 0x42b0 | `Stick_MeasureCentre` | 64× averaged reading of the 4 stick ADC channels → centre `0x2000004c[4]`; if outside 0x600..0xA00 uses 0x800. | table `0x6c28`, lit `0x401`. | high |
| 0x4324 | `DelayLoop(n)` | Busy loop. | | high |
| 0x4330 | `Led_Blink(mask, period)` | Counter `0x2000007c`; toggles `0x2000007d` every `period` calls; LEDs in mask on/off accordingly. | calls `0x44d4`/`0x4478`. | high |
| 0x43c0 | `Led_Task(sysState)` | Runs `Battery_Update`; if `0x2000011a`==0 all LEDs off. Streaming: LED1/LED3 off then mode mask `0x20000028` on (LED1 = X / D-digital, LED1+LED3 = D-analog, all 4 = PS3 flag). Not streaming: LED1 blinks (period 20). Switch on `sysState` (`0x20000068`): 1/2 → LED2 solid if battery level 7 (charged) else blink/50; 4 → LED2 slow blink (200) if level ≤2 (low batt) else off; 5/6 → LED2 off. Then LED4 (mask 8) fast blink (period 10) while turbo active (`0x2000011e`/`0x2000011d`); states 3/5/6 → all LEDs off. | switch table at `0x43e8` (decoded by hand), lits `0x4460..0x4474`. Caller `0x4a54`. | med |
| 0x4478 | `Led_Off(mask)` | OUTSET bit (17+n) for each set bit (LEDs active-low on P0.17..P0.20). | `0x50000508`. | high |
| 0x44a0 | `Led_Set(mask)` | Set bit → OUTCLR (on), clear bit → OUTSET (off), 4 LEDs P0.17..20. | `0x50000508/50c`. | high |
| 0x44d4 | `Led_On(mask)` | OUTCLR bit (17+n) for each set bit. | `0x5000050c`. | high |
| 0x44fc | `Gzll_Enable` (wrapper) | Calls `0x3e8` (Gazell enable/start). | callers `0x4cd0`, `0x4df0`, `0x4f50`. | med |
| 0x4504 | `Gzll_DisableAndWait` | Calls `0x3e0`→`0xf18` (disable) then spins until `0xf84` reports idle. Used before changing address/channel. | callers `0x4700`, `0x48a0`, `0x48c0`, `0x4f50`. | med |

### Code in range that Ghidra has NOT defined as functions (worth `create_function` later)
| Address | Likely role | Evidence | Conf. |
|---|---|---|---|
| 0x38bc | `PowerOff_Prepare` / "off" loop | LEDs off (`0x44a0(0)`), calls `0x49c0`, builds a bond-record image from `0x20000007`, `0x2000002a`, `0x2000011a`, `0x20000119`, `0x2000010d`, `0x2000010f` (0xAA top byte) and saves it via `0x3ab0`; pokes `0x50000764` (PIN_CNF[25]); ends in an endless 1000-delay loop. | med |
| 0x3984 | `EnterSystemOff` | PIN_CNF for all pins, wake sense on P0.23/P0.21/P0.22 (Back/Start/Home), saves bond record via `0x3ab0`, then writes 1 to `0x40000500` (POWER.SYSTEMOFF). | med |
| 0x3a5c | `Bond_ClearFlags` | Zeros `0x20000007` (bonded), `0x20000094`, `0x20000095`. | med |
| 0x3ab0 | **`BondRecord_Save(buf, n)`** — the NVMC flash WRITE | page = (CODESIZE−1)·CODEPAGESIZE; NVMC CONFIG=2, ERASEPAGE=page, poll READY, CONFIG=0; writes n words at page+4 via a word-write helper, then magic `0xAA558877` (lit `0x3b1c`). NVMC lits `0x4001e500`, `0x4001e400`. | high |
| 0x3b20 | GPIOTE IRQ / port-event handler (SDK-style) | lits `0x40006000/6100/617c/6300/6500` (GPIOTE), `0x50000500/700`, `0x20000230`. Not analysed further. | low |

### Subsystem notes

- **Input task `FUN_4bb0`** = `DirectButtonScan(0x3e7c)` → `MuxScan(0x3c0c)` → `StickScan(0x3f80)` → `BuildInputReport(0x2ffc)`; the radio state machine `0x4514` then sends 19 bytes from `0x200001a0`.
- **`0x20000034` is the combined, debounced button word** (direct pins + mux + triggers), not just the mux; `0x20000038` = previous tick. Full bit map from the code:
  `0x1` Back (P0.23) · `0x2` P0.29 (→XInput LS/L3) · `0x4` P0.28 (→RS/R3) · `0x8` Start (P0.21) · `0x10` Up · `0x20` Right · `0x40` Down · `0x80` Left · `0x100` L2/LT (AIN2) · `0x200` R2/RT (AIN3) · `0x400` L1/LB (P0.12 channel) · `0x800` R1/RB (P0.13 channel) · `0x1000` Y/△ · `0x2000` B/○ · `0x4000` A/✕ · `0x8000` X/□ · `0x10000` Home/Guide (P0.22) · `0x20000` Turbo (P0.15) · `0x100000` P0.00 (debounced separately, maybe charger sense) · `0x400000` P0.14 (unused by report) · `0x800000` X/D switch (P0.10).
  Mux channel (select P0.9=b0, P0.10=b1, P0.11=b2) → bit: ch0 Up 0x10, ch1 Left 0x80, ch2 Down 0x40, ch3 Right 0x20, **ch4 A 0x4000, ch5 B 0x2000, ch6 X 0x8000, ch7 Y 0x1000**. This differs from README (which says 0x1000=ch4, 0x4000=ch6, 0x8000=ch7). Check the README legend.
- **All 12 face/d-pad/shoulder/trigger buttons are pressure-sensitive.** `0x200001e4[12]` holds 0..255 pressures in PS3 order: Right, Left, Up, Down, △, ○, ✕, □, L1, R1, L2, R2.
- **X/D mode** (`0x2000010d`: 0 = X when P0.10 reads low, 1 = D when high; read at boot in `0x41c4`, debounced in streaming by `0x2f28`). It changes three things:
  1. **Stick format** (`0x3f80`): X = signed int16 with Y inverted; D = unsigned 0..0xFFFF, centre 0x8000. In D mode `BuildInputReport` then shifts each axis **in place** `>>8`. That is why SWD sees "low byte 0..255, rest 128". The **periodic `0x8000` reads are not recalibration**: they catch the 16-bit value between `StickScan` and the in-place shift.
  2. **Report layout** (below).
  3. **Digital/analog sub-mode in D** (`0x2000010f`, default 1, Home toggles it, set to 1 on every X/D change). When it is 1, `FUN_49d8` maps the D-pad onto left-stick axes 0/1 (0x00/0xFF) and maps the **right stick onto face buttons** (RX<0x40→X/□, >0xC0→B/○, RY<0x40→Y/△, >0xC0→A/✕), then **forces axes 2/3 to 0x80**. That explains why the right stick "changed none of the six values" in `stick_probe.py`. Triggers never touch the stick array: they go to `0x200001ee/ef` and BTN bits 0x100/0x200.
- **Stick RAM**: `0x2000003c[4]` output axes (LX, LY, RX, RY); `0x20000044[4]` = **idle-timer snapshot** (updated only when an axis moves >10 counts, in `0x3724`). That explains "v4/v5 follow the left stick slowly / stay at 137". `0x2000004c[4]` centre, `0x20000054[4]` max, `0x2000005c[4]` min.
- **Report at `0x200001a0`** (19 bytes are always sent):
  - **X mode** (XInput-style, `0x2000010d`=0): `00 14 | b2 | b3 | LT | RT | LX LY RX RY (int16 LE)`.
    b2: 0x01 Up, 0x02 Down, 0x04 Left, 0x08 Right, 0x10 Start, 0x20 Back, 0x40 L3(bit1), 0x80 R3(bit2).
    b3: 0x01 LB, 0x02 RB, 0x04 Guide/Home, 0x10 A, 0x20 B, 0x40 X, 0x80 Y. LT/RT = pressure bytes `[10]`/`[11]`.
  - **D mode** (DirectInput-style; this matches the observed `REP 18 | 01 LX LY RX RY B1 B2 …`): `01 | LX LY RX RY (u8) | b5 | b6 | b7 | L2p | R2p`.
    b5 = hat (low nibble, 0xF = centre) | 0x10 ✕/A, 0x20 ○/B, 0x40 □/X, 0x80 △/Y.
    b6: 0x01 L1, 0x02 R1, 0x04 L2, 0x08 R2, 0x10 Select/Back, 0x20 Start, 0x40 L3, 0x80 R3. b7: 0x01 Home.
  - **"PS3" layout** (if `0x20000110`≠0): report cleared to 0 / axes 0x80 / hat 0xF (`0x48e8`), then `btnA btnB hat LX LY RX RY + 12 pressure bytes` = exactly 19 bytes (generic PS3 pad format). b0: 0x01 □, 0x02 ✕, 0x04 ○, 0x08 △, 0x10 L1, 0x20 R1, 0x40 L2, 0x80 R2. b1: 0x01 Select, 0x02 Start, 0x04 L3, 0x08 R3, 0x10 Home. **No code was found that sets `0x20000110` non-zero.** Only zero-writes exist (`0x33c8`, `0x4174`). This mode looks unreachable (or set by code Ghidra hasn't defined).
- **Turbo**: hold P0.15 + press a button in mask 0xFC06 to toggle turbo on it. LED4 (P0.20) blinks while turbo is set. Turbo activity also resets the idle timer.
- **LEDs**: 4 active-low LEDs on **P0.17–P0.20** (mask bit n → P0.(17+n)). LED1 = mode / pairing blink, LED2 = battery/charge, LED3 = D-analog indicator, LED4 = turbo.
- **Power**: system state byte `0x20000068` (dispatched in `0x4a54`). Idle sleep after ~0xB786 input-task ticks, pairing timeout 0xDAC ticks, long-Home power-off (~0x13F ticks), and critical battery all lead to the System-OFF path at `0x3984` (wake on Back/Start/Home), which **saves the bond record to flash** (`0x3ab0`).
- **Battery**: AIN1 (P0.27) with VBG reference (`0x2eb8`), levels in `0x20000084/85`. Level 7 = charged (GPIO P0.30 & P0.15 high, low confidence).
- **Rumble/motor**: nothing in this range drives a motor. Candidates elsewhere: P0.7 (output, driven low at init) and P0.16 (output, set high only when the bond record's top byte ≠ 0xAA).
- Bond record extra fields (from `0x41c4`): rec+8 b1 → `0x2000000b`, b2 → `0x2000011a` (power/LED-enable state). rec+0xC b0 → `0x2000002a`, top byte → `0x20000119`.

---

## 4. `0x4514`–`0x5a50`: pairing, main loop, test mode, power states

Tick = TIMER0 compare, 0x2800 µs = **10.24 ms** (TIMER0 1 MHz, config @0x6bdc). "N ticks" below uses that unit.
Unless noted, the evidence comes from Ghidra decompile/refs. Code Ghidra has no function for was disassembled from the ROM with `arm-none-eabi-objdump`. Ghidra was only read, never changed.

| Address | Suggested name | What it does | Key evidence | Conf |
|---|---|---|---|---|
| 0x4514 | `Pairing_Step` (pairing state machine) | Sends one packet for the current step (1 pair / 2 confirm / 4 stream) and checks the ack. Matches PAIRING_PROTOCOL.md §2. New detail: stream flags byte = `X/D(0x2000010d)<<4 \| (powerState 0x2000011a & 3)<<2 \| struct+8`. | state `0x20000005`, TX buf `0x200001f0`, report `0x200001a0`, TX result `0x20000098` (1 ok/2 fail), ack-ready `0x20000099` | high |
| 0x4700 | `Gzll_AppInit` (normal radio init) | Gazell init `FUN_362(0)` → pairing base 0xC1C2C6 → 8-channel table `0x6c20` → `FUN_63c(1)`, `FUN_61c(2000)` → enable. **This is the only startup path; main always calls it.** | called only from main; literal 0xC1C2C6 @0x4764 | high |
| 0x4770 | `Gzll_SetBaseFromId` | Base address = ID bytes swapped + `0xE7` prefix byte. | (doc) | high |
| 0x4794 | `Pair_CheckAckStep2` | Ack ≥7 B, type 2, host ID or own ID matches. | (doc) | high |
| 0x47e0 | `Pair_CheckAckStep4` | Ack ≥5 B, type 4. Copies rumble bytes (`FUN_4910`), counts b1 bit0 (>60 in a row → struct+9). Sets bonded=1, window=300, fail=0. | (doc) | high |
| 0x483c | `Pair_CheckAckStep1` | Ack type 1. Learns the host ID, or enforces it while bonded and the window is open. Sets struct+5=1 and struct+6=byte. | patched at 0x4860/0x4866 | high |
| 0x48a0 | `Gzll_SwitchToId` | Gazell disable → set base from ID → retry `FUN_55a` → enable. | (doc) | high |
| 0x48c0 | `Gzll_SetChannel` | Disable → `FUN_27a(ch)` (one-entry channel table) → enable. | patched at 0x48c2 (pin ch 32) | high |
| 0x48d8 | `Gzll_SendPacket` | `FUN_40e(pipe 0, buf, len)` = add packet to the Gazell TX FIFO. | only caller 4514 | high |
| 0x48e8 | `Report_Init` | Clears the 19 B input report at `0x200001a0`: bytes 3..6 = 0x80 (4 stick axes centred), byte 2 = 0x0F (hat neutral), rest 0. | callers 2ffc, 492c | high |
| 0x4910 | `Rumble_FromAck` | Copies ack bytes 3/4 (`0x20000208/9`) → rumble levels `0x20000095/0x20000094`. | caller 47e0 | high |
| 0x492c | `Input_Init` | Rumble = 0, then `FUN_426c`, `FUN_40ec`, `Report_Init`. | main | med |
| 0x4960 | `Rumble_PwmInit` | `app_pwm_init` with 2 channels on **P0.24 / P0.25**, active-high, period 5000 µs (200 Hz), on TIMER1 (instance @0x6bec). Then `app_pwm_enable`. | config @0x6bf4 = {24,25,…,5000}, instance → 0x40009000 | high |
| 0x4994 | `Rumble_SetDuty` | `app_pwm_channel_duty_set(ch, min(duty,100))`, retried up to 10× while it returns 0x11 (NRF_ERROR_BUSY). | caller 4b78 | high |
| 0x49d8 | `Input_RemapDpadRightStick` | D-pad bits (0x20000120) force left-stick axes 0/1 to 0/0xFF. Right-stick axes 2/3 (`0x20000040/42`) beyond 0x40/0xC0 become button bits 0x1000/0x2000/0x4000/0x8000, then axes 2/3 are reset to 0x80. | caller FUN_2ffc (condition not traced) | med |
| 0x4a54 | `App_StateMachine` | Calls `FUN_380c` (Home long-press), `FUN_3724` (idle/pair timeouts), `FUN_3874` (debounced P0.00), `FUN_43c0` (LEDs). Then a switch8 on app state `0x20000068` (cases 0..6, see notes). | table @0x4a7e: 0→0x4b0c 1→0x4a88 2→0x4ac6 3→0x4aa4 4→0x4ae0 5→0x4b00 6→0x4b06 | med |
| 0x4b78 | `Rumble_Update` | If `0x20000118` (bond-record flag) ≠ 0, forces rumble off. Otherwise duty = `FUN_36d8(level)` for ch1 (0x20000095) and ch0 (0x20000094). | main loop | high |
| 0x4bb0 | `Input_ScanAll` | `FUN_3e7c` (GPIO buttons) → `FUN_3c0c` (mux+triggers) → `FUN_3f80` (sticks) → `FUN_2ffc` (build report). | main loop | high |
| 0x4be4 | `Hop_NextChannel` (LFSR) | 24-bit LFSR at struct+0xE..0x10 → channel 2..80 in struct+0. | (doc) | high |
| 0x4c68 | `TestMode_CheckAtBoot` | Samples 5× (busy-delay 2000 between samples): **Start P0.21 + Home P0.22 + Back P0.23 all held**. If all 5 samples are held → test mode = 3, channel = 2. P0.28 held → flag `+6`=1 (alternate channels). | `0x20000128` struct: +1 mode, +3 ch, +6 alt | high |
| 0x4cd0 | `TestMode_Run` | One pass of the RF test. Mode 1 → `radio_tx_carrier` (0x69c0: constant carrier, RADIO TEST reg 0x40001540=3, TXEN). Mode 2 → `radio_modulated_tx_carrier` (0x698c: random payload, SHORTS=7 continuous TX). Both at TXPOWER 4, MODE 2 (250 kbps). Mode 3 → `Gzll_TestInit(ch)` (alternate channels: 2→8, 41→40, 80→55). Then loops on 1 ms delays: every 10 ms feeds the WDT, scans buttons, runs `TestMode_Keys` and `TestMode_Leds`, until mode or channel changes. Then stops the radio, waits 50 ms. | RADIO 0x40001200/1500/1000 literals @0x69b4 | high |
| 0x4d8c | `TestMode_Leds` | LED pattern by mode (1→0x4, 2→0x1, 3→0x2). LED bit 0x8 blinks with period 10/50/100 for channel 2/41/80. | `FUN_44a0` = LEDs P0.17..20 | high |
| 0x4df0 | `TestMode_Keys` | Buttons (`0x20000034`): 0x80 → mode 1, 0x10 → mode 2, 0x20 → mode 3. 0x8000 → ch 2 (2402 MHz), 0x1000 → ch 41 (2441), 0x2000 → ch 80 (2480). **Home (0x10000) held 300 ticks → power off**: radio off, P0.16 OUTCLR, LEDs off, loops forever feeding the WDT. | 0x5000050C bit16 | high |
| 0x4ebc | `Mux_ClearSelPinCnf` | `PIN_CNF[12]` and `[13]` = 0 (P0.12/13 back to input) between mux reads. | 0x50000730/34 | high |
| 0x4edc | `SystemInit` | nRF51 SystemInit: PAN workarounds (0x40000504, 0x40006C18) and the MPU DISABLEINDEBUG write (0x40000608), chosen by part revision read from 0xF0000FE0..FEC. | caller Reset_Handler | high |
| 0x4f50 | `Gzll_TestInit(ch)` | Like 4700 but Gazell init `FUN_362(1)` and a single caller-given channel. No `63c`/`61c` calls. **Only reached from test mode 3**, so it is not a second boot path. | only caller 4cd0 | high |
| 0x4fc0 | `TickTimer_Start(adj)` | TIMER0 (`nrf_drv_timer`) periodic compare, period `0x2800-adj` µs, handler 0x5011 (sets tick flag `0x20000000`). | inst @0x6bd4 = 0x40008000, 1 MHz | high |
| 0x50c4 | `Wdt_Feed` | `nrf_drv_wdt_channel_feed(0)` (RR[0]=0x6E524635). | 0x631c | high |
| 0x50f8 | `Wdt_Init` | WDT init with config @0x6c08 {behaviour 0, reload **200 ms**, prio 1}, then channel alloc and enable. | 0x40010000/0x504/0x508 | high |
| 0x5148 | `__ARM_common_switch8` | ARMCC switch helper (keep the name). | — | high |
| 0x526c | `app_pwm_channel_duty_set` | Percent → ticks (`cycle*duty/100`) → `duty_ticks_set`. | SDK | high |
| 0x528c | `app_pwm_channel_duty_ticks_set` | Returns 8 if the PWM isn't enabled and 0x11 while busy. Picks one of four GPIOTE/PPI reconfiguration paths (0x6748/67b0/6840/68bc). | SDK | high |
| 0x5318 | `app_pwm_channel_init` | Allocates a GPIOTE channel and 2 PPI channels, wires them to the timer compare. | SDK | high |
| 0x53e4 | `app_pwm_cycle_ticks_get` | `nrf_drv_timer_capture_get(ch 2)`. | SDK | med |
| 0x540e | `app_pwm_enable` | Timer enable, state = 2. | SDK | high |
| 0x5420 | `app_pwm_init` | Timer init + PPI group + channel init, period → ticks, IRQ enable. | SDK | high |
| 0x559c | `ppi_is_app_channel_mask` (nrf_drv_ppi helper) | Returns 1 if the mask has no reserved bits (mask literal @0x55ac). | callers 5858/5f14/5f5c | med |
| 0x55b0 | `gpiote_channel_free` | Frees GPIOTE channel slot n (handler = -1, pin map 0xFF). | nrf_drv_gpiote | med |
| 0x55cc | `gpiote_channel_port_alloc` | Finds a free GPIOTE slot (0..3 task/event, 4 = port) and records pin↔slot. | nrf_drv_gpiote | med |
| 0x5610 | `gpiote_channel_get(pin)` | Returns the GPIOTE slot assigned to a pin. | nrf_drv_gpiote | med |
| 0x5620 | `Clock_HfxoStart` | CLOCK HFCLKSTARTED=0, TASKS_HFCLKSTART=1, waits for the event. | 0x40000000/0x40000100 | high |
| 0x56dc | `critical_region_enter` | Nested `cpsid i`, counter `0x200000e0`. | 7 callers | high |
| 0x56ec | `critical_region_exit` | Decrements the counter and runs `cpsie i` at 0. | — | high |
| 0x5700 | `delay_loop(n)` | Empty busy loop. | — | high |
| 0x57d4 | `radio_generate_random_packet` | RADIO PCNF/addr set up for the test. Payload `0x20000268` = 0xFE length + 254 RNG bytes. | RNG `FUN_69f4`, RADIO 0x400015xx | high |
| 0x5828 | `ppi_is_channel_allocated` | Bit test in `0x200000c4`. | nrf_drv_ppi | med |
| 0x5840 | `ppi_is_group_allocated` | Bit test in `0x200000c1`. | nrf_drv_ppi | med |
| 0x5858 | `ppi_is_app_channel` | `559c(1<<n)`. | — | med |
| 0x5866 | `ppi_is_valid_group` | `(1<<n) & 0xF`. | — | med |
| 0x5874 | `SystemInit_errata_check` | Part revision check (0xF0000FE0..FEC) used by SystemInit. | caller 4edc | high |
| 0x58bc | `ppi_is_programmable_channel` | Channel number 3..15. | — | med |
| 0x5a50 | **`main`** | Init, then the endless main loop (see notes). | via thunk 0xc8 | high |

Code in the range with no Ghidra function (objdump only):

| Addr | Role |
|---|---|
| 0x4bc4 | RTC1_IRQHandler (vector 33): clears RTC1 COMPARE0..3/TICK/OVRFLW, calls 0x6b40 (app_timer). |
| 0x4e68 | SWI1_IRQHandler (vector 37): app_timer list processing (`0x200000e4`). |
| 0x4f30 / 0x4f40 | TIMER0 / TIMER1 IRQHandlers → `nrf_drv_timer` irq 0x6220(base, idx). |
| 0x4fb0 | TickTimer_Stop (`nrf_drv_timer_disable` on TIMER0). |
| 0x5010 | Tick callback. On COMPARE0 (event 0x140): if struct+5 is set (step-1 success), clears it and restarts the timer with period `0x2800 - (struct+6 & 0x7F)` µs (one-off phase adjust from the host ack byte). Then sets `0x20000000`=1. |
| 0x5044 | UART0_IRQHandler (vector 18): RXDRDY → app_fifo put (`0x20000210`), ERROR (ERRORSRC 0x40002480), RXTO. User callback `*(0x200000a4+4)`. |
| 0x50d0 | WDT_IRQHandler (vector 32): clears TIMEOUT and calls the WDT event handler. |
| 0x5120 | WDT re-init with config @0x6c14 (10 ms reload). Used in power-down state 6 before it stops feeding. |
| 0x5164 / 0x5172 | Word memcpy / memzero (ARMCC scatter-load helpers). |
| 0x5180..0x5208 | app_uart TX-start / STARTTX / stop helpers (UART0 0x40002000). |
| 0x5210 | `NVIC_SystemReset` (SCB AIRCR = 0x05FA0004). |
| 0x5228 / 0x524a | app_fifo get / put. |

### Subsystem notes

- **Boot flow:** Reset_Handler 0x154 → `SystemInit` 0x4edc → ARMCC `__main` (scatter-load) → thunk 0xc8 → **`main` 0x5a50**.
  `main` calls, in order: GPIO init `4074` (P0.16 and P0.7 as outputs, P0.7 driven low; LEDs P0.17..20 as outputs and off; pull-ups on the buttons), HFXO start `5620`, tick timer `4fc0(0)`, rumble PWM `4960`, own ID `4158`, Gazell init `4700`, pairing reset `4174`, `2e98`, `3568`, input init `492c`, bond-record load `41c4`, `33c8`, WDT 200 ms `50f8`, test-mode check `4c68`.
- **Main loop** (no sleep/WFE, busy-polls):
  - While test mode `0x20000129` ≠ 0, loop in `TestMode_Run`.
  - Otherwise wait for the 10.24 ms tick flag `0x20000000`.
  - Each tick:
    1. Power-on latch logic (below).
    2. If app state `0x20000068` ∈ {2, 4}, run `Pairing_Step` 4514.
    3. `Input_ScanAll`.
    4. `FUN_2f28` (X/D switch and Home handling).
    5. `Rumble_Update`.
    6. `App_StateMachine` 4a54.
    7. Feed the WDT.
- **Startup-path question answered:** `FUN_4700` is the only boot path. `FUN_4f50(ch)` runs only from RF-test mode 3. Its `FUN_362` argument is 1 there (0 in normal boot) and it uses one fixed channel. It does not depend on the X/D switch.
- **RF test / factory mode:**
  - Entered by holding **Start + Home + Back** (P0.21/P0.22/P0.23) at power-up. Hold P0.28 too for the alternate Gazell channels.
  - In the mode, the buttons with mask 0x80 / 0x10 / 0x20 pick unmodulated carrier / modulated random TX / Gazell.
  - The buttons with mask 0x8000 / 0x1000 / 0x2000 pick 2402 / 2441 / 2480 MHz.
  - The LEDs show the mode and blink at a rate that depends on the channel.
  - Holding Home ~3 s powers off (P0.16 low).
  - It is the Nordic SDK `radio_test` example code (+4 dBm, 250 kbps). Regulatory test mode, not a debug backdoor.
- **Power management (NEW):**
  - **P0.16 is very likely the power-hold latch** (high = stay on). Test-mode power-off and app state 6 both drive it low and then idle.
  - **Power state `0x2000011a`:** 0 = not latched, 1 = Home held, 2 = on.
    - At boot it comes from the bond-record misc top byte (`+0x0C>>24`): 0xAA → 0, anything else → 2, with P0.16 set right away (resume after SYSTEMOFF).
    - In `main`, while the state is 0, holding **Home (P0.22, bit 0x10000 of `0x20000034`) for 300 ticks (~3 s)** sets P0.16, so the user must hold Home ~3 s to power on.
    - The state is also sent to the host in stream flags bits 2..3. While the state is 0, `FUN_43c0` keeps the LEDs off.
  - **Long-press Home while on:** `FUN_380c` returns 1 after >0x13F ticks (~3.3 s) → state machine → state 3 (clears the bond flag 0x20000007 and rumble) → power-down states.
  - **Idle timeout** (`FUN_3724`, while streaming):
    - The counter at `0x20000024` restarts on any button press or a stick move of more than ±10.
    - At ≥0xB786 ticks (~8 min) it sets a flag in 0x2000000c, and at +0x12 more ticks it returns 2.
    - Outside streaming, `0x20000020` > 0xDAC ticks (~36 s) returns 1, which looks like a pairing/search timeout.
  - **App state 5 (0x3984) = deep sleep:**
    - Stops Gazell and the tick timer, and sets every pin to disconnected input except P0.16.
    - Arms GPIO SENSE wake-up on P0.00/P0.21/P0.22/P0.23. P0.00 sense polarity depends on its current level.
    - Writes the bond record with "resume" (top byte ≠ 0xAA, power state 2), waits 2 ms, then **POWER.SYSTEMOFF = 1 (0x40000500)**.
  - **App state 6 (0x38bc) = latch-off:**
    - Rumble and LEDs off, power state 0, bond record saved with 0xAA, Gazell stopped.
    - P0.25 low, P0.7 high, **P0.16 low** (power cut).
    - If still powered (e.g. external supply), polls Home every 1 s. On a fresh press it calls 0x5120 and stops feeding the WDT, so the **200 ms WDT resets** the chip.
  - **P0.00** (bit 0x100000, README calls it "stuck low") is debounced by `FUN_3874` (80/30 ticks). It steers the app state: state 0 picks 5 (SYSTEMOFF) vs 6 (latch-off) on it. **Probably a charger / USB-power detect line, not a button** (low-med).
- **Rumble (NEW):** two motors on PWM **P0.24 / P0.25**, 200 Hz (TIMER1 + GPIOTE + PPI via app_pwm). Duty comes from the host's **step-4 ack bytes 3 and 4** (`0x20000095`→ch1, `0x20000094`→ch0) through `FUN_36d8`. It is forced off when `0x20000118` (bond-record +0x08 byte) is set. A custom host can drive rumble through those 2 ack bytes.
- **Buttons word `0x20000034` is not mux-only:** `FUN_3e7c` writes a 3-sample-debounced copy of the direct GPIO buttons into it (bit 0x10000 = P0.22 Home, 0x100000 = P0.00, …). `FUN_3c0c` ORs the mux bits in. `0x20000038` = previous sample (edge detection). The README's "mux bitmask" label needs this correction.
- **Right stick explanation (NEW, med):** `FUN_49d8` (called from report builder `FUN_2ffc` in some mode) turns the right stick (axes 2/3) into button bits and re-centres the axes to 0x80. It also maps d-pad bits onto left-stick axes 0/1. This matches the README observation that the right stick changed none of the axis values. Check which mode/flag `FUN_2ffc` uses (likely the X/D switch or an analog toggle).
- **UART0:** a full app_uart_fifo driver and UART0_IRQHandler are linked in (0x5044, 0x5180..0x524a, init near 0x65fc). No defined function references the UART globals, and the stock firmware's boot sequence never starts the UART. Likely dead/debug code (med).
- **Timers:** tick on TIMER0 (10.24 ms, phase-nudged once after step-1 pairing success using a host ack byte), PWM on TIMER1, Gazell on TIMER2, app_timer on RTC1 + SWI1. WDT 200 ms, fed once per main-loop pass.

---

## 5. `0x5b38`–`0x69f4`: Nordic SDK drivers (HAL)

Most of this range is **Nordic nRF51 SDK driver code, compiled in almost unchanged**. It includes
nrf_adc, nrf_delay, nrf_drv_common (IRQ), nrf_drv_gpiote, nrf_drv_ppi, nrf_drv_timer, nrf_drv_wdt and
**app_pwm**. It also has parts of the Gazell HAL (radio bitrate/TX power) and Nordic's `radio_test` example
(`radio_disable`, `radio_tx_carrier`, `radio_modulated_tx_carrier`). The SDK names below follow the SDK
8–10 API. Error codes match the SDK: 0=SUCCESS, 4=NO_MEM, 7=INVALID_PARAM, 8=INVALID_STATE,
0x85=MODULE_ALREADY_INITIALIZED, 0x11=BUSY (app_pwm).

**No function in this range touches NVMC.** The flash writer is in *undefined* code at `0x3ab0`
and `0x57a8` (see Subsystem notes).

| Address | Suggested name | What it does | Key evidence | Conf |
|---|---|---|---|---|
| 0x5b38 | `nrf_adc_configure` | Builds ADC CONFIG from {resolution, input scaling, reference, ext ref}, disables ADC, then writes CONFIG while keeping PSEL. | CONFIG `0x40007504` (`&0xff00 \| cfg`); calls 5b78(0). Callers 2e98/2eb8 (ADC init). | high |
| 0x5b78 | `nrf_adc_input_select` | CONFIG.PSEL = arg<<8; ENABLE = (arg!=0). | `0x40007500` ENABLE, `0x40007504` CONFIG. | high |
| 0x5b98 | `nrf_delay_ms` | Loops n × `FUN_000000f4(999)` (delay_us). | Pool `0x3e7`=999. Caller 4cd0 (radio-test sweep) and the undefined code at 0x3a26. | high |
| 0x5bb4 | `nrf_drv_common_irq_enable(IRQn, prio)` | Sets the NVIC priority (IPR, or SCB SHPR for negative IRQn), then ICPR clear-pending and ISER enable. | `0xE000E400`, `0xE000ED00`+0x1C, `0xE000E280`, `0xE000E100`. Callers: gpiote_init (IRQ 6), timer_init, wdt_init (IRQ 16). | high |
| 0x5c14 | `nrf_drv_gpiote_init` | Returns 8 if already initialised. Otherwise: 32 pin→channel slots = 0xFF, clears 5 user slots via 55b0, enables GPIOTE_IRQn(6) at prio 1, INTENSET = PORT (bit31), sets the init flag. | `0x40006304`=0x80000000. State at `0x20000250` (+0x15 = `0x20000265` init flag, pin map at `0x20000244..`). Caller: app_pwm_init 5420. | high |
| 0x5c68 | `nrf_drv_gpiote_is_init` | Returns the init flag at `0x20000265`. | | high |
| 0x5c78 | `nrf_drv_gpiote_out_init(pin, cfg)` | If task_pin: allocates a GPIOTE channel and sets CONFIG[ch] = PSEL(pin)\|POLARITY\|OUTINIT. Then PIN_CNF[pin]=3 (output) and OUTSET/OUTCLR to the initial state. | GPIOTE CONFIG `0x40006510+4ch` (mask `0xffece0ff`), PIN_CNF `0x50000700`, OUTSET `0x50000508`, OUTCLR `0x5000050C`. Pin map `0x20000230+0x14`. | high |
| 0x5d0c | `nrf_drv_gpiote_out_task_addr_get(pin)` | Returns `0x40006000 + 4*ch` (TASKS_OUT[ch]). | Pool `0x40006000`. Used as the PPI task endpoint by app_pwm. | high |
| 0x5d20 | `nrf_drv_gpiote_out_task_enable(pin)` | Sets CONFIG[ch].MODE = Task (3). | CONFIG `0x40006510+4ch`. | high |
| 0x5d50 | `nrf_gpiote_task_force / outinit set(pin, state)` | CONFIG[ch] bit20 (OUTINIT) = state. | Caller 6748 (app_pwm 0%/100% duty). | high |
| 0x5d80 | `nrf_drv_gpiote_out_task_trigger(pin)` | TASKS_OUT[ch] = 1. | `0x40006000+4ch`. | high |
| 0x5d98 | `nrf_drv_gpiote_out_uninit(pin)` | Frees the channel if it is in task mode, clears the slot (0xFF), PIN_CNF = 2 (disconnected input). | `0x50000700`. Caller app_pwm_uninit 6670. | high |
| 0x5dc8 | `nrf_drv_ppi_channel_alloc(&ch)` | Takes the first free channel from mask `0xFFF8` (ch 3..15) inside a critical section; sets the bit in the alloc mask. | Alloc mask `0x200000c4`. CS = 56dc/56ec. | high |
| 0x5e1c | `nrf_drv_ppi_channel_assign(ch, eep, tep)` | CH[ch].EEP/TEP = eep/tep after checks (0xE = NULL). | `0x4001F510 + 8ch`. | high |
| 0x5e5c | `nrf_drv_ppi_channel_disable(ch)` | CHENCLR = 1<<ch. | `0x4001F508`. | high |
| 0x5e94 | `nrf_drv_ppi_channel_enable(ch)` | CHENSET = 1<<ch. | `0x4001F504`. | high |
| 0x5ecc | `nrf_drv_ppi_channel_free(ch)` | CHENCLR, then clears the alloc bit. | `0x4001F508`, `0x200000c4`. | high |
| 0x5f04 | `nrf_drv_ppi_channel_include_in_group(ch, grp)` | Wrapper: 5f14(1<<ch, grp). | | high |
| 0x5f14 | `nrf_drv_ppi_channels_include_in_group(mask, grp)` | CHG[grp] \|= mask (critical section). | `0x4001F800 + 4grp`. | high |
| 0x5f5c | `nrf_drv_ppi_channels_remove_from_group(mask, grp)` | CHG[grp] &= ~mask. | `0x4001F800`. | high |
| 0x5fa4 | `nrf_drv_ppi_group_alloc(&grp)` | Takes the first free group of 4; group mask at `0x200000c1`. | | high |
| 0x5ff4 | `nrf_drv_ppi_group_disable(grp)` | TASKS_CHG[grp].DIS = 1. | `0x4001F004 + 8grp`. | high |
| 0x6018 | `nrf_drv_ppi_group_enable(grp)` | TASKS_CHG[grp].EN = 1. | `0x4001F000 + 8grp`. | high |
| 0x6048 | `nrf_drv_ppi_group_free(grp)` | Group DIS, then clears the alloc bit. | `0x4001F004`, `0x200000c1`. | high |
| 0x6090 | `nrf_drv_ppi_init` | Returns 0x85 if already initialised, else sets the state byte. | `0x200000c0`. | high |
| 0x60a8 | `nrf_drv_timer_capture_get(inst, ch)` | Reads CC[ch]. | `p_reg+0x540+4ch`. Caller 53e4 (app_pwm_cycle_ticks_get). | high |
| 0x60b6 | `nrf_drv_timer_clear(inst)` | TASKS_CLEAR = 1. | `+0x00C`. | high |
| 0x60be | `nrf_drv_timer_compare(inst, ch, cc, int_en)` | INTENSET/INTENCLR bit(16+ch), CC[ch] = cc. | `+0x304`/`+0x308`, `+0x540`. | high |
| 0x60e8 | `nrf_drv_timer_compare_event_address_get(inst, ch)` | Returns `p_reg + 0x140 + 4ch`. | Used as the PPI EEP by app_pwm. | high |
| 0x60f6 | `nrf_drv_timer_compare_int_disable(inst, ch)` | INTENCLR = 0x10000<<ch. | `+0x308`. | high |
| 0x6108 | `nrf_drv_timer_compare_int_enable(inst, ch)` | Clears EVENTS_COMPARE[ch], then INTENSET. | `+0x140`, `+0x304`. | high |
| 0x612c | `nrf_drv_timer_disable(inst)` | TASKS_SHUTDOWN = 1; state = INITIALIZED(1). | `+0x010`. State array `0x200000ac`. | high |
| 0x6140 | `nrf_drv_timer_enable(inst)` | TASKS_START = 1; state = POWERED_ON(2). | `+0x000`. Callers 4fc0 (TIMER0 tick), 540e (app_pwm_enable). | high |
| 0x6154 | `nrf_drv_timer_extended_compare(inst, ch, cc, shorts, int_en)` | SHORTS &= ~(0x101<<ch); SHORTS \|= mask; then compare(). | `+0x200`. | high |
| 0x6184 | `nrf_drv_timer_init(inst, cfg, handler)` | Returns 8 if already initialised. Enables the IRQ (5bb4), stores the handler/context, writes MODE, BITMODE, PRESCALER. Default cfg at `0x6c4c` = {16 MHz, timer, 32-bit, prio 3}. | `+0x504`, `+0x508`, `+0x510`. 7 if handler is NULL. | high |
| 0x6268 | `nrf_drv_timer_uninit(inst)` | NVIC ICER, clears the handler, disable, SHORTS &= ~0xF0F, INTENCLR for CC0..3, state = 0. | `0xE000E180`, `0xf0f`. | high |
| 0x62cc | `nrf_drv_timer_us_to_ticks(inst, us)` | us × (16 MHz >> PRESCALER). | Reads PRESCALER `+0x510`. | high |
| 0x62e4 | `nrf_drv_wdt_channel_alloc(&id)` | Next reload-request ID (<8); RREN \|= 1<<id. | WDT RREN `0x40010508`. State `0x200000c8`. | high |
| 0x631c | `nrf_drv_wdt_channel_feed(id)` | RR[id] = `0x6E524635`. | `0x40010600`. Called via 50c4 (feed wrapper). | high |
| 0x6330 | `nrf_drv_wdt_enable` | INTENSET = TIMEOUT, TASKS_START = 1, state = 2. | `0x40010304`, `0x40010000`. | high |
| 0x6350 | `nrf_drv_wdt_init(cfg, handler)` | CONFIG = behaviour, CRV = reload_ms×32768/1000, WDT_IRQn(16) priority. The SDK default cfg `0x6c5c` = {behaviour 1, 2000 ms} is **unused**. The real caller `0x50f8` passes `0x6c08` = {behaviour 0 = pause in sleep & debug halt, **200 ms**, prio 1} (verified). | `0x4001050C`, `0x40010504`; 2db0 = udiv. Caller 50f8 (wdt setup: init + alloc + enable). | high |
| 0x6398 | `empty_stub` | `bx lr` only (default hook). | Caller 3e8 (Gazell area). | med |
| 0x63d4 | `gzll_get_word_20000160` (unclear) | Returns `*(u32*)0x20000160`. | Callers 1ef8/1f00 (Gazell). | low |
| 0x63e0 | `gzll_table_lookup(idx≤15)` (unclear) | Asserts idx<16 (assert id `0x300c8`), returns byte 0 of the 3-byte entry at `0x20000470+3*idx`. | Callers 1b32/1be0/1d2e/1d36 (Gazell FIFO/pipe code). | low |
| 0x6434 | `gpio_pin_clear` (existing) | OUTCLR = 1<<pin. | `0x5000050C`. | high |
| 0x6444 | `gpio_pin_read` (existing) | (IN>>pin)&1. | `0x50000510`. | high |
| 0x6454 | `gpio_pin_read` (duplicate) | Same as 6444; separate copy used by 4c68. | `0x50000510`. | high |
| 0x6464 | `gpio_pin_set` (existing) | OUTSET = 1<<pin. | `0x50000508`. | high |
| 0x6474 | `nrf_gpio_range_cfg_input(first, last, pull)` | PIN_CNF[first..last] = pull<<2 (input, connected). | `0x50000700`. Caller 4074 (GPIO init). | high |
| 0x64c8 | `gzll_radio_set_bitrate(mode)` | Writes RADIO MODE (0=1M, 1=2M, 2=250k) and the per-mode undocumented override registers `0x40001724..0x734` (values from pool `0x6530..0x6558`). Stores the mode at `0x2000039a`. | `0x40001510`, `0x40001724`–`0x40001734`. Callers 1d0, 362. | high |
| 0x655c | `gzll_radio_set_txpower(p)` | TXPOWER = p; stores it at `0x20000398`. | `0x4000150C`. Callers 1f8, 362. | high |
| 0x6608 | `nrf_timer_pan73_workaround(p_timer, en)` | Writes the hidden register `TIMERx+0xC0C` for TIMER0/1/2 (nRF51 PAN 73 "TIMER event lost"). | `0x40008C0C`/`0x40009C0C`/`0x4000AC0C`. Caller app_pwm_init. | high |
| 0x6640 | `nrf_drv_gpiote_pin_is_task_output` (approx.) | Returns 1 if the pin's slot holds a channel number < 4. | Pin map `+0x14`. | med |
| 0x6658 | `app_pwm_channel_ppi_disable(inst, ch)` | Disables the 2 PPI channels of PWM channel ch. | cb+ch*0xC+8/9 → 5e5c. | high |
| 0x6670 | `app_pwm_uninit(inst)` | Frees the PPI channels/group and GPIOTE outputs, then timer_uninit. | | high |
| 0x66f0 | `app_pwm_ppi_disable_shared(inst)` | Disables the 2 shared PPI channels (cb+0x20/0x21). | | high |
| 0x6710 | `app_pwm_ready_tick_handler` (timer CC2 IRQ callback) | Counts down pending updates; at 0 disables the CC2 int and calls the user ready_callback. | No direct xrefs (fn pointer `0x6705`-ish stored by 4960/5420). Uses `0x200000d4`. | med |
| 0x6748 | `app_pwm_duty_set_0_or_100(inst, ch, ticks)` | Duty 0% or 100%: drives the pin statically via OUTINIT (5d50); no toggling. | Called by 528c when the new value is 0 or ≥period. | med |
| 0x67b0 | `app_pwm_transition_static_to_toggle` | Switches from 0/100% to a normal duty: reprograms PPI so the toggles start synchronised to the period. | PPI group `0x4001F800`, `0x4001F000`. | med |
| 0x6840 | `app_pwm_transition_toggle_to_static` | Switches from a normal duty to 0/100%. | | med |
| 0x68bc | `app_pwm_transition_toggle_to_toggle` | Changes between two non-zero duties glitch-free, using CC3 and the PPI group. | CC3 compare event, group EN `0x4001F000`. | med |
| 0x695c | `radio_disable` | SHORTS=0, EVENTS_DISABLED=0, TEST=0, TASKS_DISABLE=1, waits for DISABLED, clears it. | `0x40001200`, `0x40001110`, `0x40001540`, `0x40001010`. | high |
| 0x698c | `radio_modulated_tx_carrier(txpower, mode, channel)` | radio_disable; builds a random packet (57d4 → RNG); SHORTS=7 (READY_START\|END_DISABLE\|DISABLED_TXEN, i.e. back-to-back TX); TXPOWER, MODE, FREQUENCY; TASKS_TXEN. | `0x40001200`=7, `0x4000150C/510/508`, `0x40001000`. Caller 4cd0. | high |
| 0x69c0 | `radio_tx_carrier(txpower, mode, channel)` | **Unmodulated constant carrier.** SHORTS=READY_START; TXPOWER/MODE/FREQUENCY; **TEST (0x540) = 3** (CONSTCARRIER\|PLLLOCK); TASKS_TXEN. | `0x40001540`=3, `0x40001000`. **Corrects the docs: this is not an RX starter.** | high |
| 0x69f4 | `rng_get_byte` | VALRDY=0, START, polls VALRDY, returns VALUE. | `0x4000D100/D000/D508`. Only caller 57d4 (test-packet generator). | high |

### Subsystem notes

- **Flash write path (bond-record WRITER): found, outside this range, in undefined code.**
  - `0x57a8` = `nvmc_write_word(addr, val)`: CONFIG=1, wait READY, `*addr=val`, wait, CONFIG=0, wait.
    It uses NVMC `0x4001E504`/`0x4001E400`.
  - `0x3ab0` = `bond_record_save(words, n)`. It computes page = (FICR.CODESIZE−1)×CODEPAGESIZE =
    `0x3FC00`, sets CONFIG=2, writes ERASEPAGE=page, sets CONFIG=0. It then writes `n` words at page+4… and
    **magic `0xAA558877` after them** (`n=3`: +4, +8, +0xC; magic at +0x10). This mirrors the reader `FUN_00003a78`.
    It has two callers, both in undefined code reached from the main mode dispatcher `FUN_00004a54`
    (switch8 at 0x4a7a, mode byte `0x20000068`):
    - **Mode 5 → `0x3984` = save the bond, then go to System OFF.**
      - Sets all PIN_CNF (except P0.16) to 2 (disconnected).
      - Configures wake-up sense with pull-up and SENSE=Low on P0.21/22/23 (Start/–/Back) and on P0.00.
        P0.00's sense polarity depends on mux bit20 (`0x20000034`). Done via undefined helper `0x6400` =
        `nrf_gpio_cfg_sense_input(pin, pull, sense)`.
      - Writes the record. +4 = host ID (`0x2000001c` = pairing struct+0x18). +8 = struct+3 (bonded) \|
        struct+7<<8 \| 0x02<<16. +0xC = 0x01 \| [`0x2000010d`]<<8 \| [`0x2000010f`]<<16.
      - Then `nrf_delay_ms(2)` and **POWER.SYSTEMOFF (`0x40000500`) = 1**.
      - So the bond is written to flash on every power-off, not when pairing completes.
    - **Mode 6 → `0x38bc`**: unbinds.
      - Clears struct+3 / `0x2000002a` / `0x2000011a`, sets `0x20000119`=0xAA.
      - Writes the record {host 0, flags 0, `0xAA000000`\|[`0x2000010f`]<<16\|[`0x2000010d`]<<8}. This exactly
        matches the stock dump `+0xC = AA010100` with host=0, so the stock record was written by this path.
      - Then sets P0.25 as output (low), OUTSET P0.7, OUTCLR P0.16.
      - Then loops forever every 1000 ms while mode==6. It feeds the WDT (50c4) and reads GPIO IN bit 22.
      - Purpose (charging/park/unpair state?) is unclear.
- **Vibration motor = app_pwm, 2 channels, on P0.24 and P0.25, using TIMER1.**
  - Config at `0x6bf4`: pins 0x18/0x19, period 5000 µs (200 Hz), both active-high.
  - Instance `0x6bec` = {cb `0x2000017c`, timer instance `0x6be4` → TIMER1 `0x40009000`}.
  - Init `FUN_00004960` → `FUN_00005420` (app_pwm_init) → `FUN_0000540e` (enable).
  - Duty is set by `FUN_00004994(ch, 0..100%)` → 526c → 528c (app_pwm_channel_duty_set), called from
    `FUN_00004b78`. That function presumably maps the host's rumble bytes from the step-4 ack (unverified).
  - The PWM uses GPIOTE tasks + PPI channels/groups + TIMER1 CC0..3, plus the PAN-73 workaround.
- **Timers:**
  - TIMER0 (`0x6bd4` instance) is the app tick. `FUN_00004fc0` sets CC0 = us_to_ticks(10240 − x) with
    COMPARE0_CLEAR and interrupt, i.e. a periodic ~10.24 ms tick.
  - TIMER1 runs PWM.
  - TIMER2 is Gazell's (IRQ `0x26A2`).
  - RTC1 (`0x40011000`) is referenced at 0x56c8 and 0x6a4c+ (app_timer-like code, outside this range).
- **Watchdog is enabled.** **200 ms** timeout, behaviour 0 = **paused during sleep and debugger halt**
  (cfg `0x6c08`, verified; an earlier draft said 2 s / runs in sleep, which was the unused SDK default at `0x6c5c`).
  1 reload channel, fed via `FUN_000050c4` (from 4cd0, 4df0, the 5a50 main loop, and the mode-6 loop).
  Custom firmware that enables the WDT must feed it every <200 ms. SWD halts are safe.
- **Radio test mode** (`FUN_00004cd0`):
  - Uses Nordic's radio_test primitives: 695c disable, 698c modulated TX with random payload (57d4 fills
    PCNF/BASE/PREFIX/CRC and a 254-byte RNG packet at `0x20000268`), 69c0 constant carrier via the TEST
    register, and `nrf_delay_ms` for dwell.
  - **Correction:** 0x69c0 is constant-carrier TX, not RX.
- **Gazell radio HAL in range:** 64c8 bitrate (with nRF51 undocumented override regs `0x40001724..34`),
  655c TXPOWER. Undefined getters at 0x64a4/0x64b0/0x64bc return `0x20000388` +0x11/+0x12/+0x10.
- **LED:** no dedicated LED driver in this range. The only extra output drives found are P0.7 (set) and P0.16
  (clear) in mode 6, and P0.16 is excluded from the System-OFF pin disconnect. Treat P0.7/P0.16 as LED
  candidates (low confidence).
- **UART0:** undefined code at `0x6580` (called from 0x508e) writes UART0 ENABLE (`0x40002500`)=4 and
  TASKS_STARTRX (`0x40002000`). This is app_uart / nrf_drv_uart state handling (UART0 IRQ is at `0x5044`).
- **Undefined functions in/near the range** (no Ghidra function yet; worth creating):
  - `0x639c` (calls 0x4a0, sets a flag at `0x20000098`); `0x63bc`/`0x63c8` (set `0x20000098` = 2/1).
  - `0x6400` gpio_cfg_sense_input; `0x6414` gpio sense set (PIN_CNF bits 16–17).
  - `0x6490` GPIOTE event check (`0x40006000+off`==1); `0x6570` RADIO EVENTS_ADDRESS check.
  - `0x6580` UART state; `0x3ab0` bond save; `0x57a8` nvmc_write_word; `0x5710`, `0x5750` (app_timer list code).
  - `0x38bc` mode 6; `0x3984` sleep/save.

---
