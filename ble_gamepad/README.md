# BLE Gamepad firmware (nRF51822)

Turns the Speedlink controller's nRF51822 into a **Bluetooth Low Energy HID
gamepad** that pairs directly with a PC/Mac/phone — no dongle, no Gazell.
Built by adapting Nordic's `ble_app_hids_mouse` example (nRF5 SDK 12.3 + S130).

## Status (2026-10-31)

- ✅ **BLE proven working on this chip.** The stock HID-mouse example (built here)
  paired with the PC as `Nordic_Mouse`. Confirms: BLE works, the internal **RC
  oscillator** works (board has no 32 kHz crystal), S130 + our build/flash pipeline
  all good.
- ✅ **Gamepad pairs** as `Speedlink_Pad` (BLE HID gamepad appearance).
- ⚠️ **BLOCKER — vibration motor buzzes once connected, and the pad isn't yet seen
  by the browser Gamepad API.** Root cause of the buzz: the input scan reconfigures
  GPIO (mux selects / analog / button pull-ups) and, once connected, the SoftDevice
  radio interrupts preempt the scan mid-read, leaving pins in a non-low state long
  enough to engage the motor driver. Driving all pins low (no scanning) is silent
  (proven by the mouse build and `custom_fw/safe_hold`).
  **Not yet solved.** Isolation tests (see `custom_fw/diag_*.c`) showed NO single
  static pin group triggers it (analog-float, direct pull-ups, selects-high each
  silent individually) — so it's the *combination* and/or the dynamic scan activity.

## Files
- `main.c` — the gamepad application (modified mouse example). Key changes vs stock:
  - HID report map → 16 buttons + 4 axes (X,Y,Z,Rz); single input report (ID 1, 6 bytes).
  - RC oscillator clock config (no crystal on this board).
  - Motor-safe: all GPIO driven low at boot; scan restores pins low after each read.
  - `scan_inputs()` — ports the stock scan (8 mux buttons via selects P0.09/10/11 +
    ADC AIN0; 7 direct-GPIO buttons; 4 analog sticks on AIN4..7 = P0.03..06).
  - 15 ms repeating app-timer calls the scan + `ble_hids_inp_rep_send`.
  - Device name `Speedlink_Pad`, appearance HID gamepad.
- `speedlink_gamepad_app.hex` — built application (flash at its own addresses, above SD).
- `s130_nrf51_2.0.1_softdevice.hex` — Nordic S130 SoftDevice (flash at 0x0).
- `gamepad_nrf51.ld` — linker script (app runs above the SoftDevice, ~0x1B000).

## Toolchain / build
- **SDK:** nRF5 SDK **12.3.0** (last with nRF51 support).
- **Compiler:** Arm GNU toolchain **gcc-arm-none-eabi 10.3-2021.10** (bundles newlib;
  Homebrew's `arm-none-eabi-gcc` has no C library and can't build the SDK).
- Point `components/toolchain/gcc/Makefile.posix` at the toolchain:
  ```
  GNU_INSTALL_ROOT := /path/to/gcc-arm-none-eabi-10.3-2021.10
  GNU_VERSION := 10.3.1
  GNU_PREFIX := arm-none-eabi
  ```
- Drop `main.c` over `examples/ble_peripheral/ble_app_hids_mouse/main.c`, then:
  ```
  cd examples/ble_peripheral/ble_app_hids_mouse/pca10028/s130/armgcc && make
  ```

## Flash (chip already SWD-unlocked)
```
pyocd erase  -t nrf51 -f 400k --chip
pyocd flash  -t nrf51 -f 400k s130_nrf51_2.0.1_softdevice.hex
pyocd flash  -t nrf51 -f 400k speedlink_gamepad_app.hex
pyocd reset  -t nrf51 -f 400k
```

## Restore to stock controller (undo all of this)
```
pyocd flash -t nrf51 -f 400k -e chip --base-address 0x0 \
   ../firmware_dump/0x00000000_0x00040000_ROM.bin
```

## To finish (next time)
1. Solve the motor buzz: find the exact pin/combination that engages the driver
   (continue the `diag_combo.c` bisection), or hold the motor-enable pin low in an
   ISR-safe way. Simplest likely fix: keep the motor-control pin(s) driven low
   permanently and never include them in the scan.
2. Once silent, verify the gamepad enumerates in the browser Gamepad API
   (hardwaretester.com/gamepad) and map buttons/axes using `button_map.json`.
