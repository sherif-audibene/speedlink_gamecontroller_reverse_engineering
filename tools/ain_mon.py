import time, sys
from pyocd.core.helpers import ConnectHelper
dur=int(sys.argv[1]) if len(sys.argv)>1 else 20
pinmap=[26,27,1,2,3,4,5,6]
s=ConnectHelper.session_with_chosen_probe(target_override="nrf51", frequency=500000, connect_mode="attach")
s.open(); t=s.board.target
BASE=0x20001008
base=[t.read32(BASE+i*4)&0x3FF for i in range(8)]
mn=base[:]; mx=base[:]
end=time.time()+dur
while time.time()<end:
    for i in range(8):
        v=t.read32(BASE+i*4)&0x3FF
        if v<mn[i]: mn[i]=v
        if v>mx[i]: mx[i]=v
    time.sleep(0.02)
s.close()
print("AIN  pin   idle  min  max  swing")
for i in range(8):
    sw=mx[i]-mn[i]
    flag=" <== MOVES" if sw>80 else ""
    print(f"AIN{i} P0.{pinmap[i]:02d}  {base[i]:4d} {mn[i]:4d} {mx[i]:4d}  {sw:4d}{flag}")
