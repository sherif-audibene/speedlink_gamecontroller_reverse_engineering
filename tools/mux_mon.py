import time, sys
from pyocd.core.helpers import ConnectHelper
dur=int(sys.argv[1]) if len(sys.argv)>1 else 40
s=ConnectHelper.session_with_chosen_probe(target_override="nrf51", frequency=500000, connect_mode="attach")
s.open(); t=s.board.target
BASE=0x20001008
base=[t.read32(BASE+i*4)&0x3FF for i in range(8)]
print("idle channels:", base)
print("Press buttons ONE AT A TIME; reporting channel + value when it deviates >40:")
last=[0]*8; end=time.time()+dur
while time.time()<end:
    for i in range(8):
        v=t.read32(BASE+i*4)&0x3FF
        if abs(v-base[i])>40 and abs(v-last[i])>20:
            print(f"  CH{i}: {base[i]} -> {v}   (button on mux channel {i})")
            last[i]=v
    time.sleep(0.03)
s.close(); print("done")
