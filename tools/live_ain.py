#!/usr/bin/env python3
# Resilient 8-channel ADC monitor (AIN0..7). Shows live changes.
# Run while bridging the mux output (HC4051 pin3) to GND to find its MCU pin.
import time
from pyocd.core.helpers import ConnectHelper
from pyocd.core.exceptions import TransferError
pinmap=[26,27,1,2,3,4,5,6]   # AIN0..7 -> P0.xx
BASE=0x20001008
def connect():
    s=ConnectHelper.session_with_chosen_probe(target_override="nrf51",
            frequency=400000, connect_mode="attach")
    s.open(); s.board.target.halt(); return s,s.board.target
s,t=connect()
base=[t.read32(BASE+i*4)&0x3FF for i in range(8)]
print("idle AINs:", {("AIN%d/P0.%d"%(i,pinmap[i])):base[i] for i in range(8)})
print("Bridge mux pin3 -> GND (or move sticks). Ctrl-C to stop.\n")
last=base[:]; errs=0
try:
    while True:
        try:
            v=[t.read32(BASE+i*4)&0x3FF for i in range(8)]; errs=0
        except TransferError:
            errs+=1
            if errs>5:
                try: s.close()
                except: pass
                time.sleep(0.3)
                try: s,t=connect(); errs=0
                except Exception: time.sleep(0.4)
            else: time.sleep(0.05)
            continue
        for i in range(8):
            if abs(v[i]-base[i])>70 and abs(v[i]-last[i])>40:
                print("  AIN%d (P0.%d): %d -> %d"%(i,pinmap[i],base[i],v[i]))
        last=v; time.sleep(0.03)
except KeyboardInterrupt:
    print("stopped")
finally:
    try: s.close()
    except: pass
