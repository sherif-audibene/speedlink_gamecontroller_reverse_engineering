import serial, time, sys
dur=int(sys.argv[1]) if len(sys.argv)>1 else 12
label=sys.argv[2] if len(sys.argv)>2 else "scan"
s=serial.Serial("/dev/cu.wchusbserial1110",115200,timeout=1)
s.setDTR(False);s.setRTS(False);time.sleep(0.05)
s.setDTR(True);s.setRTS(True);time.sleep(0.4)
s.reset_input_buffer()
tot=[0]*126; sweeps=0; end=time.time()+dur
while time.time()<end:
    ln=s.readline().decode(errors="replace").strip()
    if not ln.startswith("SCAN"): continue
    sweeps+=1
    for tok in ln.split()[1:]:
        try: ch,c=tok.split("="); tot[int(ch)]+=int(c)
        except: pass
s.close()
import json
# save raw totals for later diff
with open(f"/private/tmp/claude-501/-Users-sherifhamad/b6b63606-993a-4b03-8a2f-d89c673cadf2/scratchpad/{label}.json","w") as f:
    json.dump({"dur":dur,"sweeps":sweeps,"tot":tot},f)
pairs=sorted(((c,ch) for ch,c in enumerate(tot) if c),reverse=True)
print(f"[{label}] {sweeps} sweeps in {dur}s. Top busy channels (ch: hits, freq MHz):")
for c,ch in pairs[:15]:
    print(f"  ch{ch:>3} ({2400+ch} MHz): {c}")
if not pairs: print("  (no carrier activity detected on any channel)")
