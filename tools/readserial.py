import serial, time, sys
s=serial.Serial("/dev/cu.wchusbserial1110", 115200, timeout=1)
s.setDTR(False); s.setRTS(False); time.sleep(0.05)
s.setDTR(True);  s.setRTS(True);  time.sleep(0.3)
s.reset_input_buffer()
dur=int(sys.argv[1]) if len(sys.argv)>1 else 8
end=time.time()+dur; n=0
while time.time()<end:
    ln=s.readline().decode(errors="replace").strip()
    if ln: print(ln); n+=1
print(f"--- {n} lines in {dur}s ---")
s.close()
