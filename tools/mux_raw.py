import time, sys
from pyocd.core.helpers import ConnectHelper
dur=int(sys.argv[1]) if len(sys.argv)>1 else 20
s=ConnectHelper.session_with_chosen_probe(target_override="nrf51", frequency=500000, connect_mode="attach")
s.open(); t=s.board.target
BASE=0x20001008
end=time.time()+dur; last=None
while time.time()<end:
    vals=[t.read32(BASE+i*4)&0x3FF for i in range(8)]
    if vals!=last:
        print("CH:", vals)
        last=vals
    time.sleep(0.1)
s.close(); print("done")
