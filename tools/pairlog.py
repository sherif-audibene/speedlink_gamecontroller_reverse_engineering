# Drive arduino/nrf24_pair and log NEW packets with timestamps.
# Usage: pairlog.py [sec] [cmd ...]   e.g.  pairlog.py 20 R2 AC6C2C1E7E7 P
#   (R2 = 250 kbps, A... = listen address; that pair = the controller's pairing link)
# Waits for the sketch's "ready" banner first - before that fix, commands sent right
# after the DTR reset were swallowed by the bootloader. Look for the "ok:<cmd>" echo.
import serial,time,glob,sys
P=sorted(glob.glob("/dev/cu.wchusbserial*")+glob.glob("/dev/cu.usbserial*"))[0]
s=serial.Serial(P,115200,timeout=0.3)
s.setDTR(False);s.setRTS(False);time.sleep(0.05);s.setDTR(True);s.setRTS(True);time.sleep(0.5);s.reset_input_buffer()
# wait for the sketch banner, else commands get eaten by the bootloader
t0=time.time()
while time.time()-t0<5:
    ln=s.readline().decode(errors="replace").strip()
    if ln: print(ln)
    if "ready" in ln: break
# optional setup commands passed as args, e.g. "AC6C2C1E7E7"
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
