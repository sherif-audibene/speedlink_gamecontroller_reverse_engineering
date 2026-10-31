# Research findings — prior art on Gazell pairing & nRF51 firmware dumping

> **CORRECTION (resolved after this doc was written):** Dumping + reversing the firmware
> showed there is **NO AES key and no crypto of any kind** on this controller — so the
> "extract the key" / "try the default gzp key" goals below do **not** apply (section 3's
> `gzp_secret_key[16]` claim is wrong — no such key is in the dump). The RF link is **stock
> Nordic Gazell with default parameters**; the app-level beacon format is Speedlink's own but
> unencrypted. The Nano+nRF24 still can't host-sync Gazell, so we read the inputs by
> reprogramming the chip over SWD instead. See `FIRMWARE_ANALYSIS.md` and `STATUS.md`.
> The still-useful parts below: the **nrfsec SWD dump** method (section 3) and the Gazell
> background. Kept for reference.

Searched 2026-10-31. Goal: has anyone cracked a Speedlink gamepad / recreated its lost
dongle, or reversed Nordic Gazell pairing / extracted a key?

## Bottom line
- **Speedlink-specific:** nothing public. No teardown, protocol dump, or dongle recreation
  for any Speedlink 2.4GHz gamepad. This integration would be original work.
- **The two hard sub-problems are solved in general:**
  1. Gazell `gzp` pairing crypto is open source and its **default key is published**.
  2. nRF51822 flash is **non-destructively dumpable** over SWD even with readback protection on.

## 1. Gazell gzp pairing crypto (MOST IMPORTANT)
Three factory-preset params compiled into BOTH device and dongle firmware:
- **16-byte secret key** `GZP_SECRET_KEY` — SDK default (PUBLIC):
  `{1, 23, 45, 57, 26, 68, 12, 64, 13, 73, 13, 62, 26, 45, 12, 77}`
- **5-byte pairing address** `GZP_ADDRESS` (not secret)
- **3-byte validation ID** `GZP_VALIDATION_ID = {0x32, 0x53, 0x66}` (SDK default, not secret)

How it works (from public gzp.c):
- Secret key is a hardcoded `#define`; **no runtime API to change it** → vendors must edit
  source. Many ship the default. TRY THE DEFAULT FIRST.
- `gzp_crypt()` builds a 16-byte AES key per phase: ID_EXCHANGE uses secret key alone;
  KEY_EXCHANGE uses secret key + Host ID; DATA_EXCHANGE uses dynamic key + Host ID.
- Session token = IV (zero-padded to 16B). **AES-128 ECB as a keystream** (encrypt IV,
  XOR with data) → encryption == decryption; token reuse under one key leaks plaintext XOR.
- Post-pairing: host generates random Host ID + dynamic key (len = 16 − validation-ID len = 13B).

Sources:
- gzp.c source: https://github.com/wangdong/cpod/blob/master/lib/nrf24/gazell/common/gzp.c
- Docs: https://docs.nordicsemi.com/r/bundle/sdk_nrf5_v16.0.0/page/lib_gzp.html
- Config defaults: https://nrfconnectdocs.nordicsemi.com/ncs/latest/nrf/doxygen/html/gzp__config_8h.html

### CONFIRMED: this controller does NOT use stock gzp pairing (checked 2026-10-31)
Compared our captures against the real gzp.h packet format. Stock gzp device->host packets
ALWAYS start with a command byte 0x00-0x07 and are 1/4/6/17 bytes (max 17). Ours:
- `E9 74 03 80 00 48 00 00 00 00 DB 01 00 00 00 00 04 45` = first byte 0xE9, length **18**
  (both the command byte AND the length are invalid for gzp).
- `5A` = command byte 0x5A (gzp 1-byte cmds must be 0/1/4/7).
Payload genuinely starts at E9 (CRC validated with 3-byte addr 010276 immediately before it).
=> Speedlink uses a PROPRIETARY protocol over the Gazell *link layer*, not Nordic's gzp.
CONSEQUENCES: the public default gzp key is irrelevant; a Python gzp host will NOT pair this
device. The realistic path is the nRF51822 SWD firmware dump (section 3) to read Speedlink's
actual pairing logic + any key.

## 2. Emulating a Gazell HOST (to replace the dongle)
- Gazell supports legacy nRF24Lxx host mode (host cycles channel table). Link Layer guide:
  https://infocenter.nordicsemi.com/topic/com.nordic.infocenter.sdk5.v12.0.0/gzll_02_user_guide.html
- Reference host that dumps packets over UART:
  https://github.com/NordicPlayground/nrf51-ble-gzll-device-uart
- Gotcha: all three gzp params + channel table + timeslot must match EXACTLY, else
  `GZP_ID_RESP_FAILED`: https://devzone.nordicsemi.com/f/nordic-q-a/52734
- Easiest native path (needs hardware): flash nRF5 Gazell SDK onto an nRF52840 dongle as host.

### No-purchase path (preferred here)
Do the gzp crypto in **Python on the laptop**, using our existing `nrf24_pair` Nano harness
as a dumb radio bridge. Gazell's REQUEST→FETCH split gives time for a Python round-trip to
compute the AES response and load it as the ack payload before the FETCH. No AES on the
ATmega168, nothing to buy.

## 3. Dumping the nRF51822 key (if default fails)
- **nrfsec** (pip): halts locked chip over SWD, finds a read gadget, dumps flash/RAM/UICR/FICR
  **with protection still on** (non-destructive `read -a`). Demonstrated on nRF51822.
  https://github.com/buildxyz-git/nrfsec  ·  https://www.optiv.com/blog/automated-unlocking-nrf51-series-socs-nrfsec
- Prior art: Include Security 2015 (Cortex-M0 read bypass)
  https://blog.includesecurity.com/2015/11/firmware-dumping-technique-for-an-arm-cortex-m0-soc/
  ; Pentest Partners 2018 (mass-erase route — destroys fw, use nrfsec read instead)
  https://www.pentestpartners.com/security-blog/nrf51822-code-readout-protection-bypass-a-how-to
- nRF51 SWD can't be fully disabled; readback bypass works regardless of APPROTECT. Not
  glitch-hardened (unlike nRF52) → no voltage glitching needed. Needs ~$3 ST-Link clone.
  **(This part was done successfully with `nrfsec` — the dump is in `firmware_dump/`.)**
- ~~Key lives in flash as `gzp_secret_key[16]`~~ — **WRONG: the dump contains no key and no
  crypto at all (see `FIRMWARE_ANALYSIS.md`). There was nothing to extract.**

## 4. Mousejack / nRF24 tooling (sniff/verify only — does NOT break Gazell crypto)
- MouseJack: https://www.bastille.net/research/mousejack (unencrypted-HID flaw, N/A to encrypted Gazell)
- gr-nordic (GNU Radio + Wireshark ESB dissector) to capture/decode our beacons:
  https://github.com/BastilleResearch/gr-nordic
- Sniffing primer: https://hackaday.com/2014/08/05/sniffing-nrf24l01-traffic-with-wireshark

## Recommended attack plan (cheapest → surest)
1. **Try the default key** via Python gzp host over the Nano bridge (free). First verify our
   captured packets against gzp.c format.
2. If that fails, **dump the controller** with nrfsec over SWD (~$3 adapter), extract the real
   key + params, retry.
3. Use gr-nordic/Crazyradio to confirm address/channel-hop/timeslot timing if needed.
