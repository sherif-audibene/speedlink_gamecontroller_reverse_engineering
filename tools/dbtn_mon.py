import time
from pyocd.core.helpers import ConnectHelper
btnpins=[0,10,14,15,21,22,23,28,29]
mask=0
for p in btnpins: mask|=(1<<p)
s=ConnectHelper.session_with_chosen_probe(target_override="nrf51", frequency=500000, connect_mode="attach")
s.open(); t=s.board.target; t.halt()
IN=0x50000510
base=t.read32(IN)&mask
print(f"idle (button bits)=0x{base:08X}; high pins:", [p for p in btnpins if base>>p&1])
print("Press buttons; reporting pin that goes 0:")
last=base; end=time.time()+45
while time.time()<end:
    v=t.read32(IN)&mask
    if v!=last:
        went0=(base|v)^v & base  # bits that are 0 now but 1 in base
        went0=base & ~v
        downs=[p for p in btnpins if went0>>p&1]
        if downs: print(f"  pressed -> P0.{','.join('%02d'%p for p in downs)}")
        last=v
    time.sleep(0.01)
s.close(); print("done")
