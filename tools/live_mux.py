#!/usr/bin/env python3
# Live HC4051 mux-channel monitor. Run while bridging face/D-pad button pads.
import time
from pyocd.core.helpers import ConnectHelper
from pyocd.core.exceptions import TransferError
s=ConnectHelper.session_with_chosen_probe(target_override="nrf51",frequency=400000,connect_mode="attach")
s.open(); t=s.board.target; t.halt()
BASE=0x20001008
base=[t.read32(BASE+i*4)&0x3FF for i in range(8)]
print("idle mux channels:",base)
print("Bridge a face/D-pad button's pads; watching 8 mux channels. Ctrl-C to stop.\n")
last=base[:]
try:
  while True:
    try: v=[t.read32(BASE+i*4)&0x3FF for i in range(8)]
    except TransferError: time.sleep(0.05); continue
    for i in range(8):
        if abs(v[i]-base[i])>60 and abs(v[i]-last[i])>30:
            print(f"  CH{i}: {base[i]} -> {v[i]}")
    last=v; time.sleep(0.05)
except KeyboardInterrupt: print("stopped")
finally:
    try: s.close()
    except: pass
