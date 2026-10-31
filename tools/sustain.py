import serial,time,glob,sys
P=sorted(glob.glob("/dev/cu.wchusbserial*")+glob.glob("/dev/cu.usbserial*"))[0]
s=serial.Serial(P,115200,timeout=0.2)
s.setDTR(False);s.setRTS(False);time.sleep(0.05);s.setDTR(True);s.setRTS(True);time.sleep(0.6);s.reset_input_buffer()
ack=sys.argv[1] if len(sys.argv)>1 else "E9740380004800000000DB01000000000445"
dur=float(sys.argv[2]) if len(sys.argv)>2 else 40
s.write(b"Z\n");time.sleep(0.1)
s.write(("K"+ack+"\n").encode());time.sleep(0.1)
print(f">>> POWER ON + MASH BUTTONS. ack={ack}  ({dur}s)")
t=time.time(); news=set()
while time.time()-t<dur:
    ln=s.readline().decode(errors="replace").strip()
    if ln.startswith("NEW"):
        p=ln.split(':',1)[-1]
        if p not in news:
            news.add(p); print(f"{int((time.time()-t)):3d}s {ln}")
print("distinct packet types seen:",len(news))
for p in sorted(news): print("  ",p)
s.close()
