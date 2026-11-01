#!/usr/bin/env python3
"""Reapply tools/ghidra_names.json to an open Ghidra program via the GhidraMCP plugin HTTP API.

  python3 tools/apply_ghidra_names.py [http://127.0.0.1:8089]
Then save the program in Ghidra (Ctrl+S).
"""
import json, sys, urllib.request
from pathlib import Path

base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8089"
names = json.loads((Path(__file__).parent / "ghidra_names.json").read_text())
fails = []
for addr, name in names.items():
    body = json.dumps({"function": "0x%08x" % int(addr, 16), "new_name": name}).encode()
    req = urllib.request.Request(base + "/rename_function", data=body,
                                 headers={"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=20))
    if r.get("status") != "success":
        fails.append((addr, name, r.get("error") or r.get("message")))
print(f"renamed {len(names) - len(fails)}/{len(names)}")
for f in fails:
    print("failed:", *f)
