#!/usr/bin/env python3
"""
Interactive button/stick mapper for the Speedlink controller over SWD.

Reads the stock firmware's decoded state from RAM (see live_report.py) and walks
you through naming every control:

  1. It waits for the controller to be idle.
  2. You press & hold ONE button (or push ONE stick fully in one direction).
  3. It identifies the exact signal, waits for release, and asks for a name.
  4. It saves the name -> signal into button_map.json after every entry.

Commands at the name prompt:
  <name>   save this control under that name
  s        skip (don't name this one)
  u        undo the last saved entry
  l        list the current map
  q        quit and write the final map

Prereq: stock firmware flashed; run in your own shell (USB access):
  <scratchpad>/venv/bin/python tools/map_buttons.py
"""
import time, struct, json, os, sys
from pyocd.core.helpers import ConnectHelper
from pyocd.core.exceptions import TransferError

FREQ = 400000
MAP_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "button_map.json")

# direct-GPIO bitmask @0x2000002c : bit -> pin  (P0.00/0x100000 is stuck-low, excluded)
DIRECT = {0x8:"P0.21", 0x1:"P0.23", 0x10000:"P0.22", 0x4:"P0.28", 0x2:"P0.29",
          0x400000:"P0.14", 0x800000:"P0.10", 0x20000:"P0.15"}
# mux bitmask @0x20000034 : bit -> HC4051 channel
MUX = {0x10:"ch0", 0x80:"ch1", 0x40:"ch2", 0x20:"ch3",
       0x1000:"ch4", 0x2000:"ch5", 0x4000:"ch6", 0x8000:"ch7"}
CENTER = 0x8000
STICK_THRESH = 0x3000   # how far a stick must move to count as "pushed"

def connect():
    s = ConnectHelper.session_with_chosen_probe(target_override="nrf51", frequency=FREQ)
    s.open(); t = s.board.target
    t.reset_and_halt(); t.resume(); time.sleep(0.4)
    return s, t

class Link:
    """pyocd wrapper that auto-reconnects on a flaky SWD link."""
    def __init__(self): self.s, self.t = connect()
    def _recover(self):
        try: self.s.close()
        except Exception: pass
        time.sleep(0.4)
        while True:
            try: self.s, self.t = connect(); return
            except Exception: time.sleep(0.6)
    def sample(self):
        while True:
            try:
                d = self.t.read32(0x2000002c)
                m = self.t.read32(0x20000034) & 0xFFFF
                ax = struct.unpack("<4H", bytes(self.t.read_memory_block8(0x2000003c, 8)))
                return d, m, [a - CENTER for a in ax]
            except TransferError:
                self._recover()

def active_signals(d, m, ax):
    """Return list of (signal_id, human_label) currently active."""
    out = []
    for b, pin in DIRECT.items():
        if d & b: out.append((f"direct:{pin}", f"direct {pin} (bit 0x{b:X})"))
    for b, ch in MUX.items():
        if m & b: out.append((f"mux:{ch}", f"mux {ch} (bit 0x{b:X})"))
    for i, v in enumerate(ax):
        if v >  STICK_THRESH: out.append((f"axis{i}+", f"stick axis {i} + ({v:+d})"))
        if v < -STICK_THRESH: out.append((f"axis{i}-", f"stick axis {i} - ({v:+d})"))
    return out

def wait_idle(link, settle=0.15):
    t0 = time.time()
    while True:
        d, m, ax = link.sample()
        if not active_signals(d, m, ax):
            if time.time() - t0 > settle: return
        else:
            t0 = time.time()
        time.sleep(0.01)

def capture_one(link):
    """Wait for exactly one stable signal; return (sig_id, label) or None if ambiguous."""
    # wait for something to appear
    while True:
        d, m, ax = link.sample()
        sig = active_signals(d, m, ax)
        if sig: break
        time.sleep(0.01)
    # debounce / stabilize ~80ms, collect union of what's active
    seen = {}
    t0 = time.time()
    while time.time() - t0 < 0.12:
        d, m, ax = link.sample()
        for sid, lbl in active_signals(d, m, ax):
            seen[sid] = lbl
        time.sleep(0.01)
    if len(seen) == 1:
        sid = next(iter(seen)); return sid, seen[sid]
    if len(seen) == 0:
        return None
    # more than one -> ambiguous
    return ("__AMBIG__", list(seen.values()))

def load_map():
    if os.path.exists(MAP_PATH):
        try:
            with open(MAP_PATH) as f: return json.load(f)
        except Exception: pass
    return {}

def save_map(m):
    with open(MAP_PATH, "w") as f: json.dump(m, f, indent=2)

def show_map(m):
    if not m:
        print("   (map is empty)"); return
    print("   current map (name -> signal):")
    for name, sid in m.items():
        print(f"     {name:<16} = {sid}")

def main():
    print("Connecting to the controller over SWD...")
    link = Link()
    mapping = load_map()          # name -> signal_id
    history = []                  # for undo
    if mapping:
        print(f"Loaded existing map ({len(mapping)} entries) from {MAP_PATH}")
        show_map(mapping)
    print("\n=== MAPPER READY ===")
    print("For each control: PRESS & HOLD one button (or push one stick fully one way),")
    print("then RELEASE when asked. Commands at the prompt: s=skip u=undo l=list q=quit\n")

    while True:
        wait_idle(link)
        print(">>> Press ONE control now (hold ~1s)...", flush=True)
        res = capture_one(link)
        if res is None:
            continue
        sid, lbl = res
        if sid == "__AMBIG__":
            print(f"    Detected several at once: {', '.join(lbl)}")
            print("    Press just ONE (push a stick straight, not diagonal). Try again.\n")
            continue
        print(f"    Detected: {lbl}")
        print("    Release it now...", flush=True)
        wait_idle(link)
        try:
            name = input(f"    Name for this control [{sid}] (s/u/l/q): ").strip()
        except EOFError:
            name = "q"
        if name == "q":
            break
        if name == "l":
            show_map(mapping); print(); continue
        if name == "s" or name == "":
            print("    skipped.\n"); continue
        if name == "u":
            if history:
                last = history.pop(); mapping.pop(last, None)
                save_map(mapping); print(f"    undid '{last}'.\n")
            else:
                print("    nothing to undo.\n")
            continue
        # save
        if sid in mapping.values():
            dup = [k for k, v in mapping.items() if v == sid]
            print(f"    note: {sid} was already '{dup[0]}' -> remapping to '{name}'")
            for k in dup: mapping.pop(k, None)
        mapping[name] = sid
        history.append(name)
        save_map(mapping)
        print(f"    saved: {name} = {sid}   ({len(mapping)} total)\n")

    print("\n=== FINAL MAP ===")
    show_map(mapping)
    save_map(mapping)
    print(f"\nWritten to {MAP_PATH}")

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt:
        print("\ninterrupted — map saved so far.")
