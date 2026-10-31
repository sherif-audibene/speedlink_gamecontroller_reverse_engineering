import serial,time,glob
P=sorted(glob.glob("/dev/cu.wchusbserial*")+glob.glob("/dev/cu.usbserial*"))[0]
s=serial.Serial(P,115200,timeout=0.2)
# one reset at open
s.setDTR(False);s.setRTS(False);time.sleep(0.05);s.setDTR(True);s.setRTS(True);time.sleep(0.6);s.reset_input_buffer()
def drain(dur):
    out=[];t=time.time()
    while time.time()-t<dur:
        ln=s.readline().decode(errors="replace").strip()
        if ln: out.append(ln)
    return out
print(">>> POWER ON THE CONTROLLER NOW; leave it on. Waiting 5s...")
base=drain(5)
print("baseline packet types:", sorted(set(l.split('R',1)[-1] for l in base if l.startswith('NEW'))) or "[see below]")
for l in base:
    if l.startswith("NEW"): print("  base",l)
candidates=["AABBCCDDEE","010276","762001","E7E7E7E7E7","5A","01","00","E9740380","0102760102","FFFFFFFFFF"]
for c in candidates:
    s.write(b"Z\n"); time.sleep(0.1)
    s.write(("K"+c+"\n").encode()); time.sleep(0.1)
    lines=drain(5)
    news=[l for l in lines if l.startswith("NEW")]
    ticks=[l for l in lines if l.startswith("tick")]
    newpkts=sorted(set(l.split(':',1)[-1] for l in news))
    print(f"\n[K={c}] NEW types: {newpkts if newpkts else 'none(still E974/5A loop)'}")
    for l in news[:6]: print("   ",l)
s.close()
