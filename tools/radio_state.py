#!/usr/bin/env python3
"""
Snapshot the controller's LIVE radio config over SWD (stock/locked firmware running).
Prints RADIO registers + Gazell params + pairing state, and the nRF24 equivalent.

  <venv>/bin/python tools/radio_state.py [samples]

RAM map (see PAIRING_PROTOCOL.md):
  0x20000004 pairing struct (+1 state, +3 bonded, +0x14 own ID, +0x18 host ID)
  0x20000368 Gazell params (+0x1d base len, +0x20 base0, +0x24 base1, +0x28 prefixes)
  0x20000398 radio cfg (+0 txpower, +1 crc len, +2 mode)
"""
import sys, time, struct
from pyocd.core.helpers import ConnectHelper

R = 0x40001000
REGS = {"FREQUENCY": 0x508, "TXPOWER": 0x50C, "MODE": 0x510, "PCNF0": 0x514,
        "PCNF1": 0x518, "BASE0": 0x51C, "BASE1": 0x520, "PREFIX0": 0x524,
        "PREFIX1": 0x528, "TXADDRESS": 0x52C, "RXADDRESSES": 0x530,
        "CRCCNF": 0x534, "CRCPOLY": 0x538, "CRCINIT": 0x53C, "STATE": 0x550}
MODES = {0: "1Mbit", 1: "2Mbit", 2: "250kbit", 3: "BLE1M"}


def bitrev(b):
    return int(f"{b:08b}"[::-1], 2)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    s = ConnectHelper.session_with_chosen_probe(target_override="nrf51", frequency=100000)
    s.open(); t = s.board.target
    try:
        t.resume()
    except Exception:
        pass
    for i in range(n):
        time.sleep(0.7)
        t.halt()  # consistent snapshot; resume immediately after
        r = {k: t.read32(R + o) for k, o in REGS.items()}
        pair = bytes(t.read_memory_block8(0x20000004, 0x20))
        gz = bytes(t.read_memory_block8(0x20000368, 0x34))
        t.resume()
        print(f"--- sample {i}")
        for k, v in r.items():
            print(f"  {k:12s} {v:08x}" + (f"  ({MODES.get(v, '?')})" if k == "MODE" else ""))
        balen = (r["PCNF1"] >> 16) & 7
        print(f"  pair state={pair[1]} bonded={pair[3]} ownID={pair[0x14:0x17][::-1].hex()}"
              f" hostID={pair[0x18:0x1b][::-1].hex()}")
        print(f"  gzll baselen={gz[0x1d]} base0={struct.unpack_from('<I', gz, 0x20)[0]:08x}"
              f" base1={struct.unpack_from('<I', gz, 0x24)[0]:08x} prefixes={gz[0x28:0x30].hex()}")
        # nRF24 view of logical address TXADDRESS: undo per-byte bit swap; on air =
        # prefix then base MSByte-first; nRF24 uint64 is on-air bytes LSByte-first.
        la = r["TXADDRESS"] & 7
        base = r["BASE0"] if la == 0 else r["BASE1"]
        pre = (r["PREFIX0"] if la < 4 else r["PREFIX1"]) >> (8 * (la & 3)) & 0xFF
        air = [bitrev(pre)] + [bitrev(base >> (8 * (3 - k)) & 0xFF) for k in range(balen)]
        print(f"  TX logical addr {la}, on-air bytes {bytes(air).hex()}"
              f" -> nRF24 A{bytes(air[::-1]).hex().upper()} @ {MODES.get(r['MODE'])}"
              f" ch{r['FREQUENCY']}")
    s.close()


if __name__ == "__main__":
    main()
