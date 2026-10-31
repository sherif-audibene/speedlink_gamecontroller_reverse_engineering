import serial,time,glob,sys
P=sorted(glob.glob("/dev/cu.wchusbserial*")+glob.glob("/dev/cu.usbserial*"))[0]
s=serial.Serial(P,115200,timeout=0.3)
s.setDTR(False);s.setRTS(False);time.sleep(0.05);s.setDTR(True);s.setRTS(True);time.sleep(0.5);s.reset_input_buffer()
# optional setup commands passed as args, e.g. "K E7E7E7E7E7"
for cmd in sys.argv[2:]:
    s.write((cmd+"\n").encode()); time.sleep(0.1)
dur=float(sys.argv[1]) if len(sys.argv)>1 else 15
t0=time.time(); last=None; run=0
print("POWER ON CONTROLLER NOW")
while time.time()-t0<dur:
    ln=s.readline().decode(errors="replace").strip()
    if not ln: continue
    ms=int((time.time()-t0)*1000)
    if ln==last: run+=1; continue
    if run: print(f"      (prev x{run+1})"); run=0
    print(f"{ms:6d}ms {ln}"); last=ln
if run: print(f"      (prev x{run+1})")
s.close()
