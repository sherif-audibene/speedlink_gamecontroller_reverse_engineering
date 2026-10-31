import time, sys
from pyocd.core.helpers import ConnectHelper
lo=int(sys.argv[1]); hi=int(sys.argv[2]); dur=int(sys.argv[3]) if len(sys.argv)>3 else 30
sess=ConnectHelper.session_with_chosen_probe(target_override="nrf51", frequency=500000, connect_mode="halt")
sess.open(); t=sess.board.target
t.halt()
PINCNF=0x50000700; OUTCLR=0x5000050C; IN=0x50000510
# pins lo..hi -> input no-pull; all others -> output low (safe, never all float)
t.write32(OUTCLR,0xFFFFFFFF)
for n in range(31):
    t.write32(PINCNF+n*4, 0x0C if lo<=n<=hi else 0x01)  # 0=input nopull, 1=output
t.write32(OUTCLR,0xFFFFFFFF)
mask=0
for n in range(lo,hi+1): mask|=(1<<n)
base=t.read32(IN)&mask
print(f"watching P0.{lo:02d}-P0.{hi:02d}  baseline=0x{base:08X}")
print("Press buttons ONE AT A TIME; I'll report the pin whose bit goes 0:")
last=base; end=time.time()+dur
while time.time()<end:
    v=t.read32(IN)&mask
    if v!=last:
        went0=base & ~v
        bits=[n for n in range(lo,hi+1) if went0>>n&1]
        if bits: print(f"  pressed -> P0.{','.join('%02d'%b for b in bits)}  (IN=0x{v:08X})")
        last=v
    time.sleep(0.015)
sess.close(); print("done")
