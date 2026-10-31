#!/usr/bin/env python3
"""
Find the real stick-axis bytes in RAM empirically.

Dumps a RAM window repeatedly while you move the sticks, tracks the min/max of
every byte, and reports which offsets actually move -> those are the live axes.

Run in your own shell (USB access):
  <scratchpad>/venv/bin/python tools/diag_sticks.py

Then: when it says GO, move BOTH sticks in full circles for ~20 s. DO NOT press
any buttons (so only stick bytes change).
"""
import time, struct
from pyocd.core.helpers import ConnectHelper
from pyocd.core.exceptions import TransferError

BASE = 0x20000020
LEN  = 0x90           # 0x20000020 .. 0x200000af
FREQ = 400000

def connect():
    s = ConnectHelper.session_with_chosen_probe(target_override="nrf51", frequency=FREQ)
    s.open(); t = s.board.target
    t.reset_and_halt(); t.resume(); time.sleep(0.4)
    return s, t

def read(t):
    return bytes(t.read_memory_block8(BASE, LEN))

def main():
    s, t = connect()
    print("connected. Collecting idle baseline (keep sticks CENTERED, no buttons)...", flush=True)
    time.sleep(0.3)
    base = None
    for _ in range(20):
        try: base = read(t); break
        except TransferError: time.sleep(0.2)
    mins = list(base); maxs = list(base)
    print("\n   >>> GO <<<  move BOTH sticks in full circles for 20 s (NO buttons)\n", flush=True)
    end = time.time() + 20
    while time.time() < end:
        try: d = read(t)
        except TransferError:
            try: s.close()
            except Exception: pass
            time.sleep(0.3)
            try: s, t = connect()
            except Exception: pass
            continue
        for i, b in enumerate(d):
            if b < mins[i]: mins[i] = b
            if b > maxs[i]: maxs[i] = b
        time.sleep(0.02)
    print("offset  idle  min  max  range   <- bytes that move = stick axes / inputs")
    for i in range(LEN):
        rng = maxs[i] - mins[i]
        if rng >= 8:
            print(f"  0x{BASE+i:08X}  {base[i]:3d}  {mins[i]:3d}  {maxs[i]:3d}   {rng:3d}")
    # also interpret as 16-bit LE pairs that move
    print("\n16-bit LE words that move:")
    for i in range(0, LEN-1, 2):
        lo = struct.unpack('<H', bytes([mins[i], mins[i+1]]))[0]
        hi = struct.unpack('<H', bytes([maxs[i], maxs[i+1]]))[0]
        idle = struct.unpack('<H', bytes([base[i], base[i+1]]))[0]
        if hi - lo >= 16:
            print(f"  0x{BASE+i:08X}  idle=0x{idle:04X}  min=0x{lo:04X}  max=0x{hi:04X}")
    s.close()

if __name__ == "__main__":
    main()
