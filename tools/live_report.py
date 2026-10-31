#!/usr/bin/env python3
"""
Live button readout for the Speedlink controller over SWD.

Runs the controller's OWN stock firmware and reads its decoded button state
straight out of RAM. The stock firmware handles the HC4051 mux + sticks for us.

  RAM 0x2000002c = direct-GPIO buttons  (Start/Back/etc, see DIRECT below)
  RAM 0x20000034 = mux buttons          (face buttons/shoulders/d-pad)
  RAM 0x2000003c = 4x uint16 stick axes (center 0x8000, see FUN_00003f80)

Prerequisite: stock firmware flashed:
  pyocd flash -t nrf51 -f 400k --base-address 0x0 \
     firmware_dump/0x00000000_0x00040000_ROM.bin

Run it (USB needs your shell, so via `!` in Claude Code or a normal terminal):
  <scratchpad>/venv/bin/python tools/live_report.py

Press buttons one at a time and note which bit/channel lights up, then tell me
the name for each -> we finalize the map. Ctrl-C to quit.
"""
import time, struct
from pyocd.core.helpers import ConnectHelper
from pyocd.core.exceptions import TransferError

FREQ = 400000
# direct-GPIO bitmask @0x2000002c : bit -> pin (pressed = bit set)
DIRECT = {0x8:"P0.21", 0x1:"P0.23", 0x10000:"P0.22", 0x4:"P0.28", 0x2:"P0.29",
          0x400000:"P0.14", 0x800000:"P0.10/switch", 0x20000:"P0.15"}
# NOTE: P0.00 (0x100000) reads stuck-low on this board -> excluded (not a button)
# mux bitmask @0x20000034 : bit -> HC4051 channel
MUX = {0x10:"ch0", 0x80:"ch1", 0x40:"ch2", 0x20:"ch3",
       0x1000:"ch4", 0x2000:"ch5", 0x4000:"ch6", 0x8000:"ch7"}

def connect():
    s = ConnectHelper.session_with_chosen_probe(target_override="nrf51", frequency=FREQ)
    s.open(); t = s.board.target
    t.reset_and_halt(); t.resume(); time.sleep(0.4)
    return s, t

CENTER = 0x8000
DEAD = 0x1800   # stick deadband around center before we report deflection

def sticks(t):
    raw = struct.unpack("<4H", bytes(t.read_memory_block8(0x2000003c, 8)))
    return [a - CENTER for a in raw]  # signed offset from center

def main():
    s, t = connect()
    print("Live. Press buttons / move sticks (Ctrl-C to quit):", flush=True)
    last = None
    while True:
        try:
            d = t.read32(0x2000002c); m = t.read32(0x20000034) & 0xFFFF
            ax = sticks(t)
        except TransferError:
            try: s.close()
            except Exception: pass
            time.sleep(0.4)
            try: s, t = connect()
            except Exception: time.sleep(0.6)
            continue
        names = [DIRECT[b] for b in DIRECT if d & b] + [MUX[b] for b in MUX if m & b]
        stk = [f"AX{i}={v:+d}" for i, v in enumerate(ax) if abs(v) > DEAD]
        key = (tuple(sorted(names)), tuple(stk))
        if key != last:
            last = key
            parts = []
            if names: parts.append("BTN: " + ", ".join(sorted(names)))
            if stk:   parts.append("STK: " + ", ".join(stk))
            print("  " + ("  |  ".join(parts) if parts else "--idle--"), flush=True)
        time.sleep(0.015)

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print("\nbye")
