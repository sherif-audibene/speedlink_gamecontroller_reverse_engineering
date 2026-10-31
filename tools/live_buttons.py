#!/usr/bin/env python3
# Resilient live button monitor over ST-Link/SWD (tolerates flaky wiring).
# Motor-safe: 9 known button pins = input+pullup, all other pins driven LOW.
import time
from pyocd.core.helpers import ConnectHelper
from pyocd.core.exceptions import TransferError
BTN=[0,10,14,15,21,22,23,28,29]
IN=0x50000510

def connect():
    s=ConnectHelper.session_with_chosen_probe(target_override="nrf51",
            frequency=400000, connect_mode="attach")
    s.open(); t=s.board.target; t.halt()
    t.write32(0x5000050C,0xFFFFFFFF)
    t.write32(0x50000518,0xFFFFFFFF)
    for p in BTN: t.write32(0x50000700+p*4,0x0C)
    return s,t

s,t=connect()
base=t.read32(IN)
print("idle GPIO IN = 0x%08X  (high button pins: %s)"%(base,[p for p in BTN if base>>p&1]))
print("Press / BRIDGE a button's pads. Ctrl-C to stop.\n")
last=base; errs=0
try:
    while True:
        try:
            v=t.read32(IN); errs=0
        except TransferError:
            errs+=1
            if errs>5:
                print("  (link dropped - reconnecting...)")
                try: s.close()
                except: pass
                time.sleep(0.3)
                try: s,t=connect(); errs=0
                except Exception: time.sleep(0.5)
            else:
                time.sleep(0.05)
            continue
        if v!=last:
            low =[i for i in range(32) if (base>>i&1) and not(v>>i&1)]
            high=[i for i in range(32) if not(base>>i&1) and (v>>i&1)]
            m="  IN=0x%08X"%v
            if low:  m+="   PRESSED(->0): P0.%s"%low
            if high: m+="   released(->1): P0.%s"%high
            print(m); last=v
        time.sleep(0.02)
except KeyboardInterrupt:
    print("\nstopped")
finally:
    try: s.close()
    except: pass
