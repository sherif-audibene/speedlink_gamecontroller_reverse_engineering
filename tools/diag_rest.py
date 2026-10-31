#!/usr/bin/env python3
"""
Measure stick REST jitter — is the controller noisy, or was it our reading?

Samples the 4 stick-axis bytes (0x3c,0x3e,0x40,0x42, 8-bit, center ~128) for 8 s
with the sticks UNTOUCHED, and reports min/max/mean/stdev per axis.

  stdev ~0-2, range <=4   -> essentially clean; normal ADC noise, deadband handles it
  bigger                  -> real analog noise on that stick (pot/wiring), still real

Run in your own shell (USB access), DO NOT touch the sticks:
  <scratchpad>/venv/bin/python tools/diag_rest.py
"""
import time, statistics
from pyocd.core.helpers import ConnectHelper
from pyocd.core.exceptions import TransferError

FREQ = 400000
OFFS = [0x2000003c, 0x2000003e, 0x20000040, 0x20000042]

def connect():
    s = ConnectHelper.session_with_chosen_probe(target_override="nrf51", frequency=FREQ)
    s.open(); t = s.board.target
    t.reset_and_halt(); t.resume(); time.sleep(0.4)
    return s, t

def main():
    s, t = connect()
    print("connected. Hands OFF the sticks. Sampling rest jitter for 8 s...", flush=True)
    samples = [[], [], [], []]
    end = time.time() + 8
    n = 0
    while time.time() < end:
        try:
            blk = bytes(t.read_memory_block8(0x2000003c, 8))
        except TransferError:
            continue
        for i, b in enumerate((blk[0], blk[2], blk[4], blk[6])):
            samples[i].append(b)
        n += 1
        time.sleep(0.01)
    print(f"\n{n} samples. Rest jitter per axis (byte value 0..255):")
    print(" axis   addr        min  max  range  mean   stdev")
    for i, off in enumerate(OFFS):
        v = samples[i]
        print(f"  AX{i}   0x{off:08X}  {min(v):3d}  {max(v):3d}   {max(v)-min(v):3d}   "
              f"{statistics.mean(v):5.1f}  {statistics.pstdev(v):5.2f}")
    s.close()

if __name__ == "__main__":
    main()
