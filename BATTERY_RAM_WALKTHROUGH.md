# Walkthrough: finding the battery level in RAM

A worked example of the whole reverse-engineering loop on one question: **where does the
controller keep its battery level, and how do we read it?**

It covers:
- reading the docs
- reading Ghidra output (`iVar`, `DAT_`, literal pools, base + offset)
- building a struct in Ghidra
- checking everything on the real hardware over SWD

See `LEARNING_GUIDE.md` for the general study plan and `FIRMWARE_FUNCTIONS.md` for the full
function list.

---

## 1. The answer first

| RAM address | Type | Name | Meaning |
|---|---|---|---|
| `0x20000068` | u8 | system state | 1/2 pairing, 4 streaming, 5/6 off. Tells you which level scale applies |
| `0x2000007c` | u8 | `blink_cnt` | LED blink tick counter (`Led_Blink`), **not battery** |
| `0x2000007d` | u8 | `blink_phase` | LED blink on/off phase (`0x00`/`0xFF`), **not battery** |
| `0x20000084` | u8 | `level` | **Battery level.** States 1–3: 3..6 (7 = charging). Streaming: 1..3 (1 = critical, forces power-off) |
| `0x20000085` | u8 | `raw_level` | Candidate level; must hold 200 ticks before it is copied to `level` |
| `0x20000086` | u8 | `samples` | VBG sample counter (streaming) |
| `0x2000008a` | u16 | `filtered` | Low-pass filtered ADC reading of AIN1 (P0.27) |
| `0x2000008c` | u16 | `stable_cnt` | Stability counter; `0xFF` = level confirmed |
| `0x2000008e` | u16 | `vbg_sum` | Sum of VBG-referenced samples (streaming) |
| `0x20000090..93` | u8[4] | `history` | Last 4 streaming levels |

`0x20000078..7b` and `0x2000007e..83` have **no references** in the code; they are unused.

**ADC → level** (states 1–3, from `Battery_Update` `0x3472..0x3496`):

| `filtered` | level |
|---|---|
| ≤ 648 | 3 |
| 649 – 669 | 4 |
| 670 – 696 | 5 |
| ≥ 697 | 6 |
| P0.30 and P0.15 both high | 7 (charging, low confidence) |

Measured on the hardware: `adc=687 → level 5`, and later `688 → level 5`, with `stable_cnt = 0xFF`.

---

## 2. Reading it live: `tools/battery_mon.py`

```
<venv>/bin/python tools/battery_mon.py
```
Output:
```
state=2 level=5 raw_level=5 adc=687 (~2.42 V at pin) hist=[3, 3, 3, 3]
```

- It connects with `connect_mode="attach"`. The default connect **halts the CPU**, and a halted
  CPU means a silent radio.
- SWD at 100 kHz. The hand-soldered link is flaky when faster.
- The voltage shown is **only an estimate**. It assumes the 1.2 V reference and the 1/3 input
  scaling. In states 1–3 the firmware may measure against VDD instead, and the resistor divider on
  P0.27 has not been measured. Calibrate against a multimeter.
- If the ST-Link powers the board, the reading probably reflects the ST-Link's 3.3 V rather than
  the battery. For a true value, run on battery with only SWDIO, SWDCLK and GND connected.

### Troubleshooting the connection

| Symptom | Cause / fix |
|---|---|
| Script hangs, no output | No probe found: pyocd waits for one. Plug in the ST-Link (`pyocd list` to check) |
| `STLink error (9): Get IDCODE error` / "Target not detected" | The chip does not answer. (1) Controller asleep: System-OFF disables SWD, so press Home and run within seconds. (2) Replug the ST-Link; clones get stuck. (3) Reseat SWDIO (pin 23), SWDCLK (pin 24), GND, check about 3.3 V on VDD |
| `get_target_voltage()` returns `None` | Normal on clones: the voltage-sense pin is not wired. Proves nothing |

---

## 3. Dumping the whole RAM

nRF51822 QFAC = **32 KB of RAM at `0x20000000..0x20007FFF`**.

```
pyocd commander -t nrf51 -f 100k -M attach \
  -c "savemem 0x20000000 0x8000 captures/ram.bin"
```

For a consistent snapshot, halt during the read and resume afterwards. The radio drops for a moment:
```
pyocd commander -t nrf51 -f 100k -M attach -c "halt" "savemem 0x20000000 0x8000 captures/ram.bin" "go"
```

**Finding unknown variables by diffing:** dump, change one thing (hold a button, move a stick),
dump again, then `cmp -l ram1.bin ram2.bin`. The bytes that changed are the ones that store it.

### Viewing it in VS Code

1. Install the **Hex Editor** extension (`ms-vscode.hexeditor`), then open `ram.bin` with it.
2. **File offset = RAM address − `0x20000000`.** Battery level `0x20000084` is at offset `0x84`.
3. **`Ctrl+G`** (also on macOS) → Go to Offset.
4. Each row is 16 bytes: offset `0x84` = row `00000080`, column `04`.
5. Multi-byte values are **little-endian**: bytes `B0 02` = `0x02B0` = 688.
6. The **Data Inspector** decodes from the cursor onwards. On a 1-byte field, read the `uint8`
   row. Its `uint16` row would combine two unrelated bytes (e.g. `05 05` → 1285).

What our dump showed:
```
00000080  00 00 00 00 [05][05] 00 00 00 00 [B0 02][FF 00] 00 00
00000090  [03 03 03 03] ...
          level=5  raw=5        filtered=688  stable=0xFF   history
```
Other recognisable spots: `0x1A0` = 19-byte input report, `0x1F0` = radio TX buffer
(`84 09 00 14 …`, where `0x84` is the report type the Nano prints in `REP` lines).

---

## 4. How the address was found

Nothing new was reverse-engineered for this. The first step was **search what is already known**:
```
grep -i "batt\|vbat\|adc" *.md tools/*
```
→ `FIRMWARE_FUNCTIONS.md:340` (`Battery_Update 0x33f8`), `:341` (`Battery_InitialMeasure 0x3568`),
`:333–335` (ADC config/read), `:401` (summary), `tools/ghidra_names.json`.

### Why "ADC input 2" means the battery

1. **`2` = AIN1.** The nRF51 ADC selects its input with a one-hot bitmask (1=AIN0, 2=AIN1,
   4=AIN2…). `ADC_Read` (`0x2edc`) writes its argument straight into that field. Source: the nRF51
   Reference Manual.
2. **AIN1 = pin P0.27.** A fixed chip pin mapping (`custom_fw/ainscan.c:15`).
3. **AIN1 = battery is an inference from behaviour, not from a schematic:**
   - **Elimination.** AIN0 = button mux, AIN2/3 = triggers, AIN4–7 = sticks. AIN1 is the only
     one left.
   - **Absolute reference.** The AIN1 code switches the ADC to the fixed 1.2 V bandgap (VBG),
     which only makes sense for measuring an absolute voltage. Sticks use a VDD-relative reference.
   - **Battery-style processing.** Slow low-pass filter, thresholds into levels, 200-tick stability.
   - **Consequences.** It drives LED2's low-battery blink (`Led_Task 0x43c0`) and level 1 forces
     power-off (`PowerButton_Check 0x380c`).

Confidence: **medium**. The hardware reading confirms the addresses and the thresholds, not the
wiring. To prove it physically:
- buzz P0.27 to battery + (through the divider), or
- vary a bench supply in place of the battery and watch `filtered` follow it.

---

## 5. Reading Ghidra's names

Ghidra only sees machine code. It invents names from what it can tell.

### Variables
| Name | Meaning |
|---|---|
| `iVar1` | signed **i**nt variable #1 (the number is just a counter) |
| `uVar2` | **u**nsigned int |
| `bVar9` | **b**yte (u8) |
| `sVar`, `cVar`, `pVar` | short, char, pointer |
| `puVar4` | **p**ointer to **u**nsigned / undefined |
| `pLVar1` | pointer to a struct whose name starts with `L` (here `LedBatt *`) |
| `param_1` | function argument 1 (arrives in register `r0`) |
| `in_r3` | a value read from register `r3` that the function never set. Usually means a callee's parameter count was guessed wrong; often junk |

### Types
| Type | Meaning |
|---|---|
| `undefined1` / `undefined2` / `undefined4` | size known (1/2/4 bytes), type unknown. Not an error, just "please tell me" |
| `x & 0xffff` | the original was a 16-bit variable. The CPU computes in 32 bits and the compiler truncates |

### Addresses
Unnamed things are named after **their own address**:

| Name | Meaning |
|---|---|
| `DAT_0000435c` | data stored **at** `0x435c` |
| `DAT_20000084` | data stored **at** `0x20000084` |
| `FUN_00003f80` | function starting at `0x3f80` |
| `LAB_0000434a` | jump target (label) at `0x434a` |
| `PTR_g_led_batt_0000435c` | a **pointer** at `0x435c`, pointing to `g_led_batt` (after typing it) |

### Two kinds of `DAT_`, two meanings

**ROM (`DAT_0000xxxx`): usually a pointer.** Look at its **value**:
```
address 0x435c:  78 00 00 20   → read backwards (little-endian) → 0x20000078
```
The Listing shows the value for you: `ldr r2,[DAT_0000435c]   = 20000078h`. In the Decompiler,
hover the name.

**RAM (`DAT_2000xxxx`): the variable itself.** `DAT_20000084` *is* the battery level byte.

---

## 6. Literal pools and base + offset (why `0x84` never appears)

A Thumb instruction cannot hold a full 32-bit address. So the compiler:
1. stores the address as data next to the function (a **literal pool**),
2. loads it with `ldr rX, [pc, #offset]`,
3. reaches neighbouring variables as **base register + small offset**.

`Battery_Update` (`0x33f8`):
```
0x33fc  ldr  r5, [pc, #0x15c]   ; r5 = 0x20000090   ← only address stored in the code
0x3400  mov  r4, r5
0x3406  subs r4, #0x18          ; r4 = 0x20000078
...
0x34d0  strb r1, [r4, #0xc]     ; store byte at 0x20000078 + 0xc = 0x20000084  ← level
```

**`0x20000084` only exists while the CPU runs**, as base + offset. That's why searching the code
for `0x84` finds nothing: search for the base (`0x20000090` / `0x20000078`) and follow the
offsets. The Listing shows Ghidra's computed address after `=>`: `strh r1,[r4,#0x14]=>DAT_2000008c`.

Why compilers do this: the file's `static` variables sit next to each other. One 4-byte base +
2-byte `[r4,#imm]` instructions are much smaller than a full address for every variable.

### Every access in `Battery_Update`

| Instruction | Offset | Address | Field |
|---|---|---|---|
| `0x3440 bl 0x2edc` (r0=2) | | | `ADC_Read(AIN1)` |
| `0x3454 strh r0,[r4,#0x12]` | +0x12 | `0x2000008a` | `filtered` (`strh` = store halfword) |
| `0x349e strb r0,[r4,#0xd]` | +0xd | `0x20000085` | `raw_level` (`strb` = store byte) |
| `0x34d0 strb r1,[r4,#0xc]` | +0xc | `0x20000084` | `level` |
| `0x34a0 strh r6,[r4,#0x14]` | +0x14 | `0x2000008c` | `stable_cnt` |
| `0x34c2 strb r7,[r5]…[r5,#3]` | +0x18.. | `0x20000090..93` | `history` reset to 3 |

### The level logic, instruction by instruction
```
0x3444  lsrs r0, r0, #4          ; adc / 16
0x3448  ldrh r0, [r4, #0x12]     ; old filtered
0x344c  subs r0, r0, r1          ; old - old/16
0x3450  adds r0, r0, r1          ; + adc/16      → slow low-pass filter
0x3454  strh r0, [r4, #0x12]     ; → 0x2000008a

0x3472  movs r1,#0x57; lsls #3   ; 0x2b8 = 696:  > 696 → level 6
0x3480  ldr  r1, =0x29d          ; 669:          > 669 → level 5
0x348a  movs r1,#0x51; lsls #3   ; 0x288 = 648:  > 648 → level 4, else 3

0x3498  ldrb r1, [r4, #0xd]      ; same as raw_level?
0x349e  strb r0, [r4, #0xd]      ;   no  → store new raw_level, reset counter
0x34a6  cmp  r0, #0xc8           ;   yes → held 200 ticks?
0x34c6  movs r0,#0xff; strh …    ;         stable_cnt = 0xFF
0x34d0  strb r1, [r4, #0xc]      ;         level = raw_level
```

### The same in the Decompiler

The decompiler's pointer `puVar4` = `0x20000090` (= `history`), so fields show as **negative**
offsets:

| Decompiler | Address | Field |
|---|---|---|
| `puVar4[-0xc]` | `0x84` | `level` |
| `puVar4[-0xb]` | `0x85` | `raw_level` |
| `puVar4[-10]` | `0x86` | `samples` |
| `puVar4 + -4` (ushort) | `0x8c` | `stable_cnt` (`= 0xff` when stable) |
| `puVar4 + -2` (ushort) | `0x8e` | `vbg_sum` |
| `puVar4[0..3]` | `0x90..93` | `history` |

---

## 7. Building a struct in Ghidra

Giving the variables names turns `DAT_… + -0xc` into `->level`.

### 7.0 Make sure RAM exists
**Window → Memory Map.** Needs a block `RAM`, start `0x20000000`, length `0x8000`, uninitialized,
R+W. Add with the green **+** if missing. (Ours is there.)

### 7.1 Create the struct
1. **Window → Data Type Manager** (bottom-left panel).
2. Right-click the program folder (`0x00000000_0x00040000_ROM.bin`) → **New → Structure…**
3. Name it `LedBatt`, Size `0x1c`, Enter.
4. Per field: double-click **DataType**, type it, Enter; double-click **Name**, type it, Enter.

| Offset | Type | Name |
|---|---|---|
| `0x4` | `byte` | `blink_cnt` |
| `0x5` | `byte` | `blink_phase` |
| `0xc` | `byte` | `level` |
| `0xd` | `byte` | `raw_level` |
| `0xe` | `byte` | `samples` |
| `0x12` | `ushort` | `filtered` |
| `0x14` | `ushort` | `stable_cnt` |
| `0x16` | `ushort` | `vbg_sum` |
| `0x18` | `byte[4]` | `history` |

   A `ushort` takes 2 rows (the next row vanishes, as expected). Size must stay `0x1c`; if it
   grows, undo.
5. Click the blue **disk** icon (Apply).

### 7.2 Apply it to RAM
`G` → `20000078` → `T` → `LedBatt` → `L` → `g_led_batt`.

The Listing now shows `g_led_batt.level` etc., each with its XREFs (who reads `(R)` / writes `(W)`).

### 7.3 Make the Decompiler use it
The decompiler only shows field names once it knows a **constant is a pointer to the struct**:
`G` → the literal-pool address (`435c` for `Led_Blink`) → `T` → `LedBatt *`.

Before:
```c
bVar2 = *(char *)(DAT_0000435c + 4) + 1;
```
After:
```c
bVar2 = PTR_g_led_batt_0000435c->bBlink_cnt + 1;
```
(The Ghidra MCP plugin adds a type prefix: `b` = byte.)

**Limit:** `Battery_Update`'s constant (`0x355c`) points to `0x20000090`, the **middle** of the
struct. Typing it `LedBatt *` would make Ghidra think the struct starts at `0x90`, and every
field name would be wrong. Keep reading `puVar4[-0xc]` as `level` there, or rename `puVar4` →
`history`.

### 7.4 Navigating
| Action | How |
|---|---|
| Jump to an address | `G`, type address |
| Follow a reference | double-click it (e.g. `Led_Blink:00004334(R)`) |
| All references to something | right-click → References → Show References to (`Ctrl+Shift+F`) |
| Go back | `Alt+←` |
| Rename / retype | `L` / `Ctrl+L` |
| Fix a function's parameters | right-click → Edit Function Signature |

---

## 8. Plot twist: `0x78` is not a battery struct

The struct started at `0x78` only because the code computes `0x90 − 0x18`. That's arithmetic,
not proof. Checking every reference to `0x78..0x93`:

| Range | Used by |
|---|---|
| `0x78..0x7b` | nothing |
| `0x7c`, `0x7d` | `Led_Blink` only |
| `0x7e..0x83` | nothing |
| `0x84..0x93` | `Battery_Update`, `Battery_InitialMeasure`, `PowerButton_Check` |

And `Led_Blink` loads **its own copy** of `0x20000078` (`DAT_0000435c`). Conclusion: LED and
battery code are probably **one C file** (`Led_Task` calls `Battery_Update`), and the compiler
placed that file's `static` variables together under one base. Hence the name `LedBatt`.

### `Led_Blink` (`0x4330`)
```c
void Led_Blink(byte led_mask, byte period) {
    g_led_batt.blink_cnt++;
    if (g_led_batt.blink_cnt > period) {        // waited long enough
        g_led_batt.blink_cnt   = 0;
        g_led_batt.blink_phase = ~blink_phase;  // 0x00 <-> 0xFF
    }
    if (blink_phase) Led_On(led_mask); else Led_Off(led_mask);
}
```
`led_mask` bits 0–3 = LEDs on P0.17–P0.20 (active-low: `Led_On` writes GPIO OUTCLR, `Led_Off`
OUTSET). `period` is 20 / 50 / 200 from `Led_Task`.

`param_1` first looked unused. It just stays in `r0` and goes into `Led_On`/`Led_Off`, which
Ghidra had typed `(void)`. Fixing their signatures to `(byte led_mask)` made it visible.

---

## 9. Bonus: reading a decompiled function (`StickScan`, `0x3f80`)

### Resolving the constants first
| Ghidra | Value | Meaning |
|---|---|---|
| `DAT_0000405c` | `0x6c28` → bytes `10 20 40 80` | ADC input per axis: AIN4..7 (one-hot) |
| `DAT_00004060` | `0x20000054` | `max[4]` |
| `DAT_00004060 + 8` | `0x2000005c` | `min[4]` |
| `DAT_00004060 - 8` | `0x2000004c` | `centre[4]` (measured at boot) |
| `DAT_00004060 - 0x18` | `0x2000003c` | `out[4]` (what `live_report.py` reads) |
| `DAT_00004064` | `0xfffffd67` = −665 | range margin |
| `DAT_00004068` | `0x2000010d` | X/D mode switch |
| `DAT_0000406c` | `0x20000110` | PS3 flag |
| `DAT_00004070` | `0xffff` | for axis inversion |

`iVar10 = uVar8 * 2` is the byte offset of element `i` in a `ushort` array. ±8 / −0x18 jump to the
neighbouring arrays (4 × 2 bytes = 8).

### Cleaned up
```c
void StickScan(void) {
  for (uint8_t i = 0; i < 4; i++) {
    uint16_t v = 0;
    for (int n = 0; n < 4; n++) v += ADC_Read(AXIS_ADC[i]);   // 4-sample sum

    if (v > max[i]) max[i] = v;                                // auto-calibrate
    if (v < min[i]) min[i] = v;

    uint16_t dz_hi = centre[i] + 200, dz_lo = centre[i] - 200; // dead zone
    uint16_t top = max[i] - 665,     bottom = min[i] + 665;    // easy full deflection

    if (!x_d_switch && !ps3_flag) {                            // X mode: signed int16
      if      (v > dz_hi)  o = ScaleToU16(top, dz_hi, v) >> 1;
      else if (v >= dz_lo) o = 0;
      else                 o = (ScaleToU16(dz_lo, bottom, v) >> 1) + 0x8000;
      if (o && (i == 1 || i == 3)) o = 0xFFFF - o;             // flip Y axes
    } else {                                                   // D mode: centre 0x8000
      if      (v > dz_hi)  o = (ScaleToU16(top, dz_hi, v) >> 1) + 0x8000;
      else if (v < dz_lo)  o = ScaleToU16(dz_lo, bottom, v) >> 1;
      else                 o = 0x8000;
    }
    out[i] = o;
  }
}
```
`ScaleToU16(hi, lo, v)` maps `lo..hi` → `0..65535` (clamped). `in_r3` disappears once its
signature is fixed to 3 parameters.

---

## 10. The method, in four moves

1. **Search before analysing.** The answer was already in `FIRMWARE_FUNCTIONS.md`.
2. **Know the chip's reference manual.** "2 = AIN1" and "VBG = absolute voltage" are datasheet
   facts.
3. **Reason by elimination and behaviour.** Every other ADC input had a job; this one filters,
   classifies, blinks the low-battery LED and forces power-off.
4. **Make the hardware prove it.** `adc=687 → level 5` confirmed the addresses. When it fails,
   suspect the setup (asleep, power, wiring, stuck probe) before the theory.

## 11. Exercises

1. Without this file: from `ADC_Read` (`0x2edc`), list its callers and arguments, map each to a
   pin, and pick out the battery.
2. Find who reads `0x20000068` (system state) and write its state table.
3. Prove AIN1 = battery physically (bench supply sweep, watch `filtered`).
4. Calibrate: one multimeter reading + one `filtered` value → work out the P0.27 divider ratio,
   then fix `VOLTS_PER_COUNT` in `tools/battery_mon.py`.
5. Use RAM diffing (section 3) to find a variable nobody has decoded yet.
