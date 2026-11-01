# Firmware flowcharts (stock ROM logic)

Flowcharts of the stock nRF51822 firmware, using the function names now applied in the Ghidra
project (`FIRMWARE_FUNCTIONS.md`, `tools/ghidra_names.json`). The diagrams are pre-rendered PNGs
(GitHub's live Mermaid viewer kept hanging on this page). Their Mermaid sources are in
`docs/flowcharts/*.mmd`. Re-render with `mmdc -i X.mmd -o X.png -s 2 -b white` (mermaid-cli). Confidence follows the function reference. Section 3 (app power states) was
decoded by hand from the jump table at `0x4a7e` and is **medium** confidence. In particular, the
meaning of "EXT" (debounced P0.00, probably external power / charger detect) is not hardware-verified.

---

## 1. Boot and main loop

![1_boot_main_loop](docs/flowcharts/1_boot_main_loop.png)

<sub>Mermaid source: [`docs/flowcharts/1_boot_main_loop.mmd`](docs/flowcharts/1_boot_main_loop.mmd)</sub>

## 2. Layers (who calls whom)

![2_layers](docs/flowcharts/2_layers.png)

<sub>Mermaid source: [`docs/flowcharts/2_layers.mmd`](docs/flowcharts/2_layers.mmd)</sub>

## 3. App power state machine (`App_StateMachine` 0x4a54, state byte `0x20000068`)

Inputs each tick:
- **LONG** = `PowerButton_Check` (Home held > ~3.3 s)
- **TIMEOUT** = `IdleTimer_Check` (pairing ~36 s / idle ~8 min)
- **EXT** = `P0_00_Debounce_maybe` (debounced P0.00, probably external power)

`Pairing_Step` (the radio) only runs in states **2** and **4**.

![3_power_states](docs/flowcharts/3_power_states.png)

<sub>Mermaid source: [`docs/flowcharts/3_power_states.mmd`](docs/flowcharts/3_power_states.mmd)</sub>

> ⚠️ **Locked-image consequence.** On battery, **holding Home to switch off (state 4 → 6)** saves
> **host ID 0**. Stock firmware is fine with that: it re-learns any host on the next pairing (the stock
> dump has host 0 for exactly this reason). The strict lock (`0x4860`/`0x4866` NOPs) is not: after
> such a power-off the controller rejected the Nano until it was reflashed (confirmed on hardware).
> **Fixed:** the locked image NOPs `bl BondRecord_Save` at `0x3908` (`00 bf 00 bf`), verified:
> Home power-off → power on reconnects. The diagram above shows the stock logic.

## 4. Pairing / streaming (`Pairing_Step` 0x4514, one packet per call)

![4_pairing](docs/flowcharts/4_pairing.png)

<sub>Mermaid source: [`docs/flowcharts/4_pairing.mmd`](docs/flowcharts/4_pairing.mmd)</sub>

## 5. Input → report pipeline (`Input_ScanAll` 0x4bb0, every tick)

![5_input_pipeline](docs/flowcharts/5_input_pipeline.png)

<sub>Mermaid source: [`docs/flowcharts/5_input_pipeline.mmd`](docs/flowcharts/5_input_pipeline.mmd)</sub>
