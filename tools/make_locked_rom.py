#!/usr/bin/env python3
"""
Build a stock-firmware image locked to ONE host ID (see PAIRING_PROTOCOL.md).

  - writes the bond record at 0x3FC00 (host ID, bonded=1, magic)
  - NOPs the two "learn any host" branches in FUN_0000483c (0x4860, 0x4866)
    (--soft skips the NOPs: bonded but re-pairable after the window)
  - pins the radio to ONE channel (32): FUN_000048c0 `mov r4,r0` -> `movs r4,#32`.
    Stock hops every packet (24-bit LFSR FUN_00004be4, channel 2..80, state 1 uses
    table 8,16..64 @0x6c20); a one-channel nRF24 host can't follow that reliably.
  - state 2 (confirm) and state 4 (stream) failures retry instead of resetting
    (FUN_00004514 0x45f0 / 0x4624 -> return @0x4610). Needed for a host parked on
    one channel: after the address switch the controller restarts its hop table.

Does NOT flash. Flash the output with (100 kHz + chip erase: 400 kHz timed out mid-erase):
  pyocd flash -t nrf51 -f 100k -e chip --base-address 0x0 <out.bin>
Restore stock: same command with firmware_dump/0x00000000_0x00040000_ROM.bin

Usage:
  python3 tools/make_locked_rom.py ABCDEF [-o out.bin] [--soft]
  python3 tools/make_locked_rom.py --selftest
"""
import argparse, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STOCK = ROOT / "firmware_dump/0x00000000_0x00040000_ROM.bin"

BOND = 0x3FC00
MAGIC = 0xAA558877
NOP = b"\x00\xbf"
STRICT = {0x4860: (b"\x0e\xd1", NOP),   # bne 0x4880 (not bonded -> learn any host)
          0x4866: (b"\x0b\xd0", NOP)}   # beq 0x4880 (window==0 -> learn any host)
# ponytail: state 2 now retries forever on the host addr; fine while locked to one host
RETRY = {0x45f0: (b"\x71\xd0", b"\x0e\xd0"),   # beq 0x46d6 (tx failed)  -> beq 0x4610
         0x4624: (b"\x57\xe0", b"\xf4\xe7"),   # b   0x46d6 (no reply)   -> b   0x4610
         # state 4: give up after >254 failed rounds (~3 s) instead of >16 (~0.2 s):
         # long enough for the host's 1.5 s silence-advance, still self-recovers.
         0x46a0: (b"\x10\x28", b"\xfe\x28"),   # cmp r0,#0x10 -> cmp r0,#0xfe
         # ponytail: fixed channel = no interference dodging; follow the LFSR if needed
         0x48c2: (b"\x04\x46", b"\x20\x24")}   # mov r4,r0 -> movs r4,#32 (channel)


def build(rom: bytes, host_id: int, soft: bool = False) -> bytes:
    assert len(rom) == 0x40000, "expected full 256 KB dump"
    assert 0 < host_id <= 0xFFFFFF, "host ID must be non-zero 24-bit"
    img = bytearray(rom)
    for off, (orig, new) in ({} if soft else STRICT).items() | RETRY.items():
        cur = bytes(img[off:off + 2])
        if cur not in (orig, new):  # refuse to patch an unknown image
            raise SystemExit(f"unexpected bytes at {off:#x}: {cur.hex()}")
        img[off:off + 2] = new
    # +0x00 left as-is; +0x04 host ID, +0x08 bonded flag, +0x0C misc, +0x10 magic
    img[BOND + 4:BOND + 0x14] = struct.pack("<4I", host_id, 1, 0xAA010100, MAGIC)
    return bytes(img)


def selftest():
    rom = STOCK.read_bytes()
    out = build(rom, 0xABCDEF)
    assert out[0x4860:0x4862] == NOP and out[0x4866:0x4868] == NOP
    assert out[0x45f0:0x45f2] == b"\x0e\xd0" and out[0x4624:0x4626] == b"\xf4\xe7"
    assert out[0x46a0:0x46a2] == b"\xfe\x28" and out[0x48c2:0x48c4] == b"\x20\x24"
    assert struct.unpack_from("<4I", out, BOND + 4) == (0xABCDEF, 1, 0xAA010100, MAGIC)
    diff = [i for i in range(len(rom)) if rom[i] != out[i]]
    patched = {o + k for o in (*STRICT, *RETRY) for k in (0, 1)}
    assert all(i in patched or BOND <= i < BOND + 0x14 for i in diff), diff
    assert build(out, 0xABCDEF) == out  # idempotent on an already-patched image
    soft = build(rom, 0x123456, soft=True)
    assert soft[0x4860:0x4868] == rom[0x4860:0x4868]
    print(f"selftest ok ({len(diff)} bytes changed)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("host_id", nargs="?", help="24-bit host ID in hex, e.g. ABCDEF")
    ap.add_argument("-o", "--out")
    ap.add_argument("--soft", action="store_true", help="bond only, no strict patch")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.host_id:
        ap.error("host_id required")
    hid = int(a.host_id, 16)
    out = Path(a.out or ROOT / f"prebuilt_hex/speedlink_locked_{hid:06X}.bin")
    out.write_bytes(build(STOCK.read_bytes(), hid, a.soft))
    print(f"wrote {out}  host_id={hid:06X}  strict={not a.soft}")


if __name__ == "__main__":
    sys.exit(main())
