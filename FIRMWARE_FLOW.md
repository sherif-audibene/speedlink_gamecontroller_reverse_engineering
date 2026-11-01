# Firmware flowcharts (stock ROM logic)

Flowcharts of the stock nRF51822 firmware, using the function names now applied in the Ghidra
project (`FIRMWARE_FUNCTIONS.md`, `tools/ghidra_names.json`). The diagrams are Mermaid (they
render on GitHub). Confidence follows the function reference. Section 3 (app power states) was
decoded by hand from the jump table at `0x4a7e` and is **medium** confidence. In particular, the
meaning of "EXT" (debounced P0.00, probably external power / charger detect) is not hardware-verified.

---

## 1. Boot and main loop

```mermaid
flowchart TD
    R["Reset_Handler 0x154"] --> SI["SystemInit 0x4edc<br/>(errata, clocks)"]
    SI --> SL["__scatterload 0x2e38<br/>(RW init, RLE decompress)"]
    SL --> M["main 0x5a50"]
    M --> I1["GPIO_InitPins 0x4074<br/>LEDs P0.17-20 off, P0.16 latch, pull-ups"]
    I1 --> I2["Clock_HfxoStart · TickTimer_Start (TIMER0 10.24 ms)<br/>Rumble_PwmInit (TIMER1 PWM P0.24/25)"]
    I2 --> I3["GetOwnId 0x4158<br/>own ID = DEVICEID0 ^ DEVICEID1"]
    I3 --> I4["Gzll_AppInit 0x4700<br/>250 kbps, pairing addr C1C2C6, ch table 8..64"]
    I4 --> I5["Pairing_Reset · Input_Init · BondRecord_Apply 0x41c4<br/>(host ID, bonded, power state, X/D from flash)"]
    I5 --> I6["Wdt_Init 200 ms · TestMode_CheckAtBoot"]
    I6 --> TM{"Start+Home+Back<br/>held at boot?"}
    TM -- yes --> T["TestMode_Run 0x4cd0 loop<br/>(Nordic radio_test: carrier / modulated / Gazell)"]
    TM -- no --> W{"10.24 ms<br/>tick flag?"}
    W -- no --> W
    W -- yes --> L1["Power-on latch:<br/>hold Home 300 ticks (~3 s) → P0.16 high"]
    L1 --> L2{"app state<br/>2 or 4?"}
    L2 -- yes --> PS["Pairing_Step 0x4514<br/>(one radio packet, §4)"]
    L2 -- no --> IN
    PS --> IN["Input_ScanAll 0x4bb0<br/>(§5 → 19-byte report)"]
    IN --> MS["Mode_UpdateSwitchAndHome 0x2f28<br/>X/D switch, Home = analog toggle"]
    MS --> RU["Rumble_Update 0x4b78<br/>duty from host ack bytes 3/4"]
    RU --> SM["App_StateMachine 0x4a54<br/>(§3, also runs Led_Task)"]
    SM --> WD["Wdt_Feed 0x50c4"]
    WD --> W
```

## 2. Layers (who calls whom)

```mermaid
flowchart LR
    subgraph APP["Speedlink application 0x2e24–0x5a50"]
        main --> App_StateMachine
        main --> Input_ScanAll
        main --> Pairing_Step
        Input_ScanAll --> BuildInputReport
        Pairing_Step --> Gzll_SendPacket
        Pairing_Step --> Gzll_SwitchToId
        Pairing_Step --> Gzll_SetChannel
        App_StateMachine --> Led_Task
        App_StateMachine --> EnterSystemOff["EnterSystemOff 0x3984"]
        App_StateMachine --> PowerOff_Prepare["PowerOff_Prepare 0x38bc"]
        EnterSystemOff --> BondRecord_Save["BondRecord_Save 0x3ab0 (NVMC)"]
        PowerOff_Prepare --> BondRecord_Save
    end
    subgraph GZLL["Nordic Gazell 0x018c–0x2d5c"]
        Gzll_SendPacket --> gzll_add_packet_to_tx_fifo
        gzll_add_packet_to_tx_fifo --> gzll_start_timeslot_engine
        RADIO_IRQHandler --> GazellTxSuccessCallback
        GazellTxSuccessCallback --> gzll_queue_callback_event
        gzll_queue_callback_event -. "pend SWI0" .-> SWI0_GazellCallbackDispatch
    end
    subgraph HAL["Nordic SDK drivers 0x5b38–0x69f4"]
        nrf_drv_timer_init
        app_pwm_init
        nrf_drv_wdt_init
        ADC["nrf_adc_* / ADC_ReadChannel"]
    end
    SWI0_GazellCallbackDispatch -. "tx result + ack payload" .-> Pairing_Step
    Input_ScanAll --> ADC
    Gzll_SetChannel --> nrf_gzll_set_channel_table
```

## 3. App power state machine (`App_StateMachine` 0x4a54, state byte `0x20000068`)

Inputs each tick:
- **LONG** = `PowerButton_Check` (Home held > ~3.3 s)
- **TIMEOUT** = `IdleTimer_Check` (pairing ~36 s / idle ~8 min)
- **EXT** = `P0_00_Debounce_maybe` (debounced P0.00, probably external power)

`Pairing_Step` (the radio) only runs in states **2** and **4**.

```mermaid
stateDiagram-v2
    [*] --> S0: reset / wake
    S0: 0 · boot / wake decision
    S1: 1 · idle on EXT (radio off)
    S2: 2 · active on EXT (radio on)
    S3: 3 · shutting down (bond flag cleared)
    S4: 4 · active on battery (radio on)
    S5: 5 · deep sleep (EnterSystemOff 0x3984)
    S6: 6 · latch-off (PowerOff_Prepare 0x38bc)

    S0 --> S4: fresh Home / Back / Start press,<br/>or resume flag (power state 2)
    S0 --> S1: EXT = 1
    S0 --> S5: ~1 s, nothing pressed, P0.00 bit set
    S0 --> S6: ~1 s, nothing pressed, P0.00 bit clear

    S1 --> S3: LONG or EXT = 0
    S1 --> S2: otherwise

    S2 --> S3: LONG
    S2 --> S4: EXT = 0
    S2 --> S1: TIMEOUT

    S3 --> S5: EXT = 0 and Home released
    S3 --> S2: EXT ≠ 0 and fresh Home press

    S4 --> S2: EXT = 1
    S4 --> S6: LONG (EXT = 0)
    S4 --> S5: TIMEOUT

    S5 --> [*]: SYSTEMOFF · bond saved WITH host ID<br/>wake on Back/Start/Home/P0.00 = reset
    S6 --> [*]: P0.16 low (power cut) · bond saved with HOST ID 0<br/>if still powered: Home → WDT reset
```

> ⚠️ **Locked-image consequence.** On battery, **holding Home to switch off (state 4 → 6)** saves
> **host ID 0**. Stock firmware is fine with that: it re-learns any host on the next pairing (the stock
> dump has host 0 for exactly this reason). The strict lock (`0x4860`/`0x4866` NOPs) is not: after
> such a power-off the controller rejects the Nano until it is reflashed. Fixes, both untested:
> - NOP `bl BondRecord_Save` at `0x3908` (`00 bf 00 bf`).
> - Build with `--soft`. The controller then re-learns `ABCDEF` from the Nano.

## 4. Pairing / streaming (`Pairing_Step` 0x4514, one packet per call)

```mermaid
flowchart TD
    E["Pairing_Step"] --> H["Hop_NextChannel 0x4be4<br/>24-bit LFSR → ch 2..80<br/>(patched: always ch 32)"]
    H --> ST{"pairing state<br/>0x20000005"}

    ST -- 1 --> P1["Gzll_SetChannel(table 8,16..64)<br/>send A1 · ownID · LFSR on PAIRING addr C1C2C6"]
    P1 --> A1{"ack type 01?<br/>Pair_CheckAckStep1 0x483c"}
    A1 -- "host ID ok<br/>(stock: learn any if not bonded)" --> G2["Gzll_SwitchToId(hostID)<br/>state = 2"]
    A1 -- no / no ack --> R1["return (retry next tick)"]

    ST -- 2 --> P2["send 82 · ownID · hostID on HOST addr"]
    P2 --> A2{"ack type 02 with hostID or ownID?<br/>Pair_CheckAckStep2 0x4794"}
    A2 -- yes --> G4["Gzll_SwitchToId(ownID)<br/>state = 4"]
    A2 -- no --> F2["stock: Pairing_Reset → state 1<br/>(patched: return, retry)"]

    ST -- 4 --> P4["send 84 · flags · 19-byte report on OWN addr<br/>(retransmit: header |= 0x10)"]
    P4 --> A4{"ack type 04?<br/>Pair_CheckAckStep4 0x47e0"}
    A4 -- yes --> OK["Rumble_FromAck (bytes 3/4)<br/>bonded = 1, fail count = 0"]
    A4 -- no --> F4{"fail rounds > limit?<br/>stock 16 · patched 254"}
    F4 -- yes --> RS["Pairing_Reset → state 1"]
    F4 -- no --> R4["return"]
```

## 5. Input → report pipeline (`Input_ScanAll` 0x4bb0, every tick)

```mermaid
flowchart LR
    D["DirectButtonScan 0x3e7c<br/>GPIO: Start, Back, Home, L3, R3,<br/>Turbo, X/D switch, P0.00<br/>3-sample debounce"] --> BTN[("buttons word<br/>0x20000034")]
    MX["MuxScan 0x3c0c<br/>HC4051 via ADC AIN0:<br/>d-pad, A/B/X/Y, L1/R1, L2/R2<br/>+ 0..255 pressure bytes"] --> BTN
    SK["StickScan 0x3f80<br/>AIN4..7, 4× averaged,<br/>auto-calibrated"] --> AX[("axes<br/>0x2000003c")]
    BTN --> TB["Turbo_Apply 0x360c"]
    TB --> B["BuildInputReport 0x2ffc"]
    AX --> B
    B --> XD{"X/D switch<br/>0x2000010d"}
    XD -- X --> XR["XInput-style:<br/>00 14 · buttons · LT RT · int16 sticks"]
    XD -- D --> DM{"digital sub-mode?<br/>0x2000010f (Home toggles)"}
    DM -- "on (default)" --> RM["Input_RemapDpadRightStick 0x49d8<br/>right stick → face buttons, RX/RY = 0x80"]
    DM -- off --> DR
    RM --> DR["DirectInput-style:<br/>01 · LX LY RX RY · hat+face · buttons · Home · L2 R2"]
    XR --> REP[("19-byte report<br/>0x200001a0")]
    DR --> REP
    REP --> PS["Pairing_Step state 4<br/>→ 84 packet to host"]
```
