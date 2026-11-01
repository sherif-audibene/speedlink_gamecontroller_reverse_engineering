#!/usr/bin/env python3
"""
Watch the controller's pairing handshake live over SWD (no halting).
Shows what the controller RECEIVED in the ack payload of its pairing request.

  <venv>/bin/python tools/peek_pairing.py [seconds]

RAM (from FUN_00004514 / FUN_0000483c literal pools):
  0x20000005 state (1 pair, 2 confirm, 4 stream)
  0x20000098 tx result (1 = acked, 2 = failed)
  0x20000099 rx-data flag (ack payload arrived)
  0x2000009c rx length (u32)
  0x20000205 rx buffer (ack payload bytes)
"""
import sys, time
from pyocd.core.helpers import ConnectHelper


def main():
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 20
    # attach = don't halt the core (the default 'halt' freezes the radio -> no traffic)
    s = ConnectHelper.session_with_chosen_probe(target_override="nrf51", frequency=100000,
                                                connect_mode="attach")
    s.open(); t = s.board.target
    t.resume()  # in case an earlier session left it halted
    t0 = time.time(); last = None
    while time.time() - t0 < dur:
        st = t.read8(0x20000005)
        txr, rxf = t.read8(0x20000098), t.read8(0x20000099)
        ln = t.read32(0x2000009c)
        buf = bytes(t.read_memory_block8(0x20000205, 8)).hex()
        cur = (st, txr, rxf, ln, buf)
        if cur != last:
            print(f"{time.time()-t0:6.2f}s state={st} txres={txr} rxflag={rxf} rxlen={ln} rxbuf={buf}",
                  flush=True)
            last = cur
        time.sleep(0.02)
    s.close()


if __name__ == "__main__":
    main()
