import serial,time,glob,sys
from collections import Counter
dur=float(sys.argv[1]) if len(sys.argv)>1 else 15
label=sys.argv[2] if len(sys.argv)>2 else "cap"
def bits(b):
    o=[]
    for x in b:
        for k in range(7,-1,-1): o.append((x>>k)&1)
    return o
def b2i(bl):
    v=0
    for x in bl: v=(v<<1)|x
    return v
def b2by(bl): return b2i(bl).to_bytes(len(bl)//8,'big')
def crc16(bl):
    crc=0xFFFF
    for bit in bl:
        t=bit^((crc>>15)&1); crc=(crc<<1)&0xFFFF
        if t: crc^=0x1021
    return crc
def recover(b):
    B=bits(b); n=len(B); out=[]
    for AW in (3,4,5):
        ab=AW*8
        for off in range(0,n-(ab+9+16)):
            plen=b2i(B[off+ab:off+ab+6])
            if plen==0 or plen>32: continue
            end=off+ab+9+plen*8
            if end+16>n: continue
            if crc16(B[off:end])==b2i(B[end:end+16]):
                out.append((b2by(B[off:off+ab]).hex(), b2by(B[off+ab+9:end]).hex()))
    return out
P=sorted(glob.glob("/dev/cu.wchusbserial*")+glob.glob("/dev/cu.usbserial*"))[0]
s=serial.Serial(P,115200,timeout=1)
s.setDTR(False);s.setRTS(False);time.sleep(0.05);s.setDTR(True);s.setRTS(True);time.sleep(0.5);s.reset_input_buffer()
end=time.time()+dur; seen=Counter()
while time.time()<end:
    ln=s.readline().decode(errors="replace").strip()
    if not ln.startswith("2M"): continue
    try:
        _,rest=ln.split(None,1); _,hexs=rest.split(":"); b=bytes.fromhex(hexs)
        if len(b)==32:
            for a,p in recover(b): seen[(a,p)]+=1
    except: pass
s.close()
# filter likely-real: addr appears with count>=3
addrcount=Counter()
for (a,p),c in seen.items(): addrcount[a]+=c
print(f"[{label}] CRC-valid (addr,payload) seen >=2x:")
for (a,p),c in seen.most_common(20):
    if c>=2: print(f"  x{c:>3} addr={a} len{len(p)//2:>2} {p}")
