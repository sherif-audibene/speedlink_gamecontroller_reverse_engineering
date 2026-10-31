#!/usr/bin/env python3
"""
Desktop GUI button/stick mapper for the Speedlink controller over SWD (tkinter).

Reads the stock firmware's decoded state out of RAM and lets you name every
control by pressing it and typing a label.

Workflow:
  1. Run it. Top bar shows SWD connection status.
  2. Press & hold a button on the controller (or push one stick fully one way).
     Its tile lights up green and it becomes the "Selected" signal.
  3. Type a name in the box and press Enter (or click Assign).
  4. Repeat for every control. Everything autosaves to button_map.json.

RAM map (stock firmware):
  0x2000002c direct-GPIO buttons | 0x20000034 mux buttons | 0x2000003c 4x stick axes

Prereq: stock firmware flashed. Run in your own shell (USB access):
  <scratchpad>/venv/bin/python tools/mapper_gui.py
"""
import time, struct, json, os, threading, queue
import tkinter as tk
from tkinter import ttk
from pyocd.core.helpers import ConnectHelper
from pyocd.core.exceptions import TransferError

FREQ = 400000
MAP_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "button_map.json")
DIRECT = {0x8:"P0.21", 0x1:"P0.23", 0x10000:"P0.22", 0x4:"P0.28", 0x2:"P0.29",
          0x400000:"P0.14", 0x800000:"P0.10", 0x20000:"P0.15"}  # P0.00 stuck-low: excluded
MUX = {0x10:"ch0", 0x80:"ch1", 0x40:"ch2", 0x20:"ch3",
       0x1000:"ch4", 0x2000:"ch5", 0x4000:"ch6", 0x8000:"ch7"}
CENTER = 0x8000
STICK_THRESH = 0x3000

# fixed signal order for the UI grid
SIG_DIRECT = [f"direct:{p}" for p in DIRECT.values()]
SIG_MUX    = [f"mux:{c}" for c in MUX.values()]
SIG_AXIS   = [f"axis{i}{s}" for i in range(4) for s in "+-"]


def active_signals(d, m, ax):
    out = set()
    for b, pin in DIRECT.items():
        if d & b: out.add(f"direct:{pin}")
    for b, ch in MUX.items():
        if m & b: out.add(f"mux:{ch}")
    for i, v in enumerate(ax):
        if v >  STICK_THRESH: out.add(f"axis{i}+")
        if v < -STICK_THRESH: out.add(f"axis{i}-")
    return out


class Reader(threading.Thread):
    """Background SWD reader -> pushes state snapshots into a queue."""
    def __init__(self, q):
        super().__init__(daemon=True)
        self.q = q
        self._stop = threading.Event()

    def connect(self):
        s = ConnectHelper.session_with_chosen_probe(target_override="nrf51", frequency=FREQ)
        s.open(); t = s.board.target
        t.reset_and_halt(); t.resume(); time.sleep(0.4)
        return s, t

    def run(self):
        s = t = None
        while not self._stop.is_set():
            if t is None:
                try:
                    s, t = self.connect()
                    self.q.put(("status", "connected"))
                except Exception as e:
                    self.q.put(("status", f"no link ({type(e).__name__}) - retrying"))
                    time.sleep(0.8); continue
            try:
                d = t.read32(0x2000002c)
                m = t.read32(0x20000034) & 0xFFFF
                ax = [a - CENTER for a in struct.unpack("<4H", bytes(t.read_memory_block8(0x2000003c, 8)))]
                self.q.put(("state", (active_signals(d, m, ax), ax)))
            except TransferError:
                self.q.put(("status", "link dropped - reconnecting"))
                try: s.close()
                except Exception: pass
                t = None; time.sleep(0.4)
            time.sleep(0.02)

    def stop(self): self._stop.set()


class App:
    def __init__(self, root):
        self.root = root
        root.title("Speedlink Controller Mapper")
        root.geometry("760x560")
        self.mapping = self.load_map()   # sig_id -> name
        self.selected = None             # currently selected signal to name
        self.prev_active = set()
        self.tiles = {}                  # sig_id -> (frame, name_label)
        self.q = queue.Queue()

        # ---- top status bar ----
        top = ttk.Frame(root, padding=8); top.pack(fill="x")
        self.status = ttk.Label(top, text="starting...", foreground="#888")
        self.status.pack(side="left")
        ttk.Button(top, text="Reset map", command=self.reset_map).pack(side="right")

        # ---- selected + name entry ----
        sel = ttk.Frame(root, padding=(8, 0)); sel.pack(fill="x")
        ttk.Label(sel, text="Selected:").pack(side="left")
        self.sel_lbl = ttk.Label(sel, text="(press a control)", font=("TkDefaultFont", 12, "bold"),
                                 foreground="#0a0")
        self.sel_lbl.pack(side="left", padx=6)
        self.name_var = tk.StringVar()
        self.entry = ttk.Entry(sel, textvariable=self.name_var, width=22)
        self.entry.pack(side="left", padx=6)
        self.entry.bind("<Return>", lambda e: self.assign())
        ttk.Button(sel, text="Assign", command=self.assign).pack(side="left")
        ttk.Button(sel, text="Clear this", command=self.clear_selected).pack(side="left", padx=4)

        # ---- signal grid ----
        grid = ttk.Frame(root, padding=8); grid.pack(fill="both", expand=True)
        self._column(grid, 0, "Direct buttons", SIG_DIRECT)
        self._column(grid, 1, "Mux buttons", SIG_MUX)
        self._column(grid, 2, "Stick axes", SIG_AXIS)
        for c in range(3): grid.columnconfigure(c, weight=1)

        # ---- footer ----
        foot = ttk.Frame(root, padding=8); foot.pack(fill="x")
        self.axinfo = ttk.Label(foot, text="axes: --", foreground="#888")
        self.axinfo.pack(side="left")
        self.count = ttk.Label(foot, text="")
        self.count.pack(side="right")

        self.refresh_tiles()
        self.reader = Reader(self.q); self.reader.start()
        root.after(40, self.pump)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _column(self, parent, col, title, sigs):
        f = ttk.LabelFrame(parent, text=title, padding=6)
        f.grid(row=0, column=col, sticky="nsew", padx=4)
        for sig in sigs:
            tile = tk.Frame(f, bd=1, relief="solid", bg="#2a2a2a", cursor="hand2")
            tile.pack(fill="x", pady=2)
            idl = tk.Label(tile, text=sig, bg="#2a2a2a", fg="#ccc", anchor="w", width=10)
            idl.pack(side="left", padx=4, pady=3)
            nml = tk.Label(tile, text="", bg="#2a2a2a", fg="#6cf", anchor="e")
            nml.pack(side="right", padx=6)
            for w in (tile, idl, nml):
                w.bind("<Button-1>", lambda e, s=sig: self.select(s))
            self.tiles[sig] = (tile, idl, nml)

    # ---------- mapping persistence ----------
    def load_map(self):
        if os.path.exists(MAP_PATH):
            try:
                with open(MAP_PATH) as f:
                    data = json.load(f)
                # accept {sig:name}; if it looks like {name:sig}, invert
                if data and all(v in (SIG_DIRECT + SIG_MUX + SIG_AXIS) for v in data.values()):
                    return {v: k for k, v in data.items()}
                return data
            except Exception:
                return {}
        return {}

    def save_map(self):
        with open(MAP_PATH, "w") as f:
            json.dump(self.mapping, f, indent=2)

    def reset_map(self):
        self.mapping = {}; self.save_map(); self.refresh_tiles()

    # ---------- actions ----------
    def select(self, sig):
        self.selected = sig
        self.sel_lbl.config(text=sig)
        cur = self.mapping.get(sig, "")
        self.name_var.set(cur)
        self.entry.focus_set(); self.entry.select_range(0, "end")

    def assign(self):
        if not self.selected: return
        name = self.name_var.get().strip()
        if not name: return
        # a name maps to exactly one signal: drop it from any other signal
        for s in [s for s, n in self.mapping.items() if n == name and s != self.selected]:
            del self.mapping[s]
        self.mapping[self.selected] = name
        self.name_var.set(""); self.save_map(); self.refresh_tiles()

    def clear_selected(self):
        if self.selected and self.selected in self.mapping:
            del self.mapping[self.selected]; self.save_map(); self.refresh_tiles()
        self.name_var.set("")

    # ---------- rendering ----------
    def refresh_tiles(self):
        for sig, (tile, idl, nml) in self.tiles.items():
            nml.config(text=self.mapping.get(sig, ""))
        named = len(self.mapping)
        total = len(self.tiles)
        self.count.config(text=f"{named} named / {total} signals   ->  {MAP_PATH}")

    def set_active(self, active, ax):
        for sig, (tile, idl, nml) in self.tiles.items():
            on = sig in active
            bg = "#1f7a1f" if on else "#2a2a2a"
            fg = "#fff" if on else "#ccc"
            if sig == self.selected:
                tile.config(bg="#b58900");
            else:
                tile.config(bg=bg)
            idl.config(bg=tile.cget("bg"), fg=fg)
            nml.config(bg=tile.cget("bg"))
        self.axinfo.config(text="axes: " + "  ".join(f"AX{i}={v:+6d}" for i, v in enumerate(ax)))

    def pump(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "status":
                    ok = payload == "connected"
                    self.status.config(text=("● " + payload), foreground="#2a2" if ok else "#c33")
                elif kind == "state":
                    active, ax = payload
                    # auto-select on a fresh single press (rising edge)
                    new = active - self.prev_active
                    if len(new) == 1:
                        self.select(next(iter(new)))
                    self.prev_active = active
                    self.set_active(active, ax)
        except queue.Empty:
            pass
        self.root.after(40, self.pump)

    def on_close(self):
        self.reader.stop(); self.save_map(); self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
