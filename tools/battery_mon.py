#!/usr/bin/env python3
"""
Live battery readout from the stock firmware's RAM over SWD (attach, no halt).

  0x20000084  u8   battery level (Battery_Update 0x33f8 / Battery_InitialMeasure 0x3568)
                   states 1-3: 3..6 by ADC, 7 = charged; streaming (state 4): 1..3, 1 = critical -> power-off
  0x20000085  u8   raw (unconfirmed) level, must stay stable 200 ticks before it becomes 0x84
  0x2000008a  u16  low-pass filtered AIN1 (P0.27) ADC result, 10-bit
                   states 1-3: <649 -> 3, 649..668 -> 4, 669..696 -> 5, >=697 -> 6
                   (seen on hw: adc=687 -> level 5)
  0x20000090  4xu8 level history (streaming only)
  0x20000068  u8   system state (1/2 pairing, 4 streaming, 5/6 off)

Run (USB needs your shell):
  <venv>/bin/python tools/battery_mon.py
"""
import time
from pyocd.core.helpers import ConnectHelper

# ponytail: ADC thresholds from FIRMWARE_FUNCTIONS.md (0x289/0x29d/0x2b9), mapping
# raw -> volts depends on the divider on P0.27, not measured yet. Calibrate against a multimeter.
VOLTS_PER_COUNT = 1.2 * 3 / 1023   # VBG 1.2 V ref, AIN 1/3 prescale -> volts at the pin

s = ConnectHelper.session_with_chosen_probe(target_override="nrf51", frequency=100000,
                                            connect_mode="attach")  # halting = radio silent
s.open(); t = s.board.target
try:
    while True:
        b = bytes(t.read_memory_block8(0x20000084, 16))   # 0x84..0x93
        level, raw_level = b[0], b[1]
        adc = b[6] | b[7] << 8                            # 0x8a
        hist = list(b[12:16])                             # 0x90..0x93
        state = t.read8(0x20000068)
        print(f"state={state} level={level} raw_level={raw_level} adc={adc} "
              f"(~{adc * VOLTS_PER_COUNT:.2f} V at pin) hist={hist}", flush=True)
        time.sleep(0.5)
except KeyboardInterrupt:
    pass
finally:
    s.close()
