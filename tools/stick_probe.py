#!/usr/bin/env python3
"""
Guided stick/trigger probe: which RAM value moves, and how, for each direction.

Reads the 6 x u16 (LE) values at 0x2000003c..0x47 over SWD WITHOUT halting the core.
At rest each is 0x0080. Reads occasionally land mid-update (a value briefly reads 0x8000,
in array order, ~every 10 s = periodic recalibration), so we only keep values
seen twice in a row and report the median while you hold each move.

  <venv>/bin/python tools/stick_probe.py
Prompts each move; press Enter, then HOLD it fully until "release".
"""
import time, struct, statistics
from pyocd.core.helpers import ConnectHelper

MOVES = ["REST (hands off)",
         "LEFT stick RIGHT", "LEFT stick LEFT", "LEFT stick UP", "LEFT stick DOWN",
         "RIGHT stick RIGHT", "RIGHT stick LEFT", "RIGHT stick UP", "RIGHT stick DOWN",
         "LEFT trigger (fully)", "RIGHT trigger (fully)"]


def read6(t):
    return struct.unpack("<6H", bytes(t.read_memory_block8(0x2000003c, 12)))


def sample(t, secs=2.0):
    vals, prev, end = [], None, time.time() + secs
    while time.time() < end:
        v = read6(t)
        if v == prev:          # settled, not a mid-update read
            vals.append(v)
        prev = v
        time.sleep(0.02)
    return tuple(int(statistics.median(c)) for c in zip(*vals)) if vals else None


def main():
    s = ConnectHelper.session_with_chosen_probe(target_override="nrf51", frequency=400000,
                                                connect_mode="attach")
    s.open(); t = s.board.target
    xd = t.read32(0x2000002c) & 0x800000  # X/D mode switch (P0.10), direct-button bit
    print(f"X/D switch bit (0x800000) = {1 if xd else 0}")
    rows = []
    for m in MOVES:
        input(f"\n>> {m}: press Enter, then hold it ")
        time.sleep(0.5)
        v = sample(t)
        print("   release." if m != MOVES[0] else "   ok.")
        rows.append((m, v))
    s.close()
    rest = rows[0][1]
    print("\nmove                   " + " ".join(f"  v{i}  " for i in range(6)))
    for m, v in rows:
        cells = [f"{x:5d}{'*' if x != r else ' '} " for x, r in zip(v, rest)] if v else ["  n/a"]
        print(f"{m:22s} " + " ".join(cells))
    print("\n* = differs from rest. v0..v5 = u16 LE at 0x2000003c + 2*i")


if __name__ == "__main__":
    main()
