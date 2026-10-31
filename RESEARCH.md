# Reference links & prior art (Gazell / nRF51)

Background gathered 2026-10-31. Conclusions here are current; see `FIRMWARE_ANALYSIS.md`
for what the dump actually showed (stock Gazell, **no key, no crypto**).

## Speedlink-specific
- Nothing public: no teardown, protocol dump, or dongle recreation for any Speedlink
  2.4 GHz gamepad. This work is original.

## Nordic Gazell
- Gazell Link Layer guide (channel table, timeslot, host/device):
  https://infocenter.nordicsemi.com/topic/com.nordic.infocenter.sdk5.v12.0.0/gzll_02_user_guide.html
- Reference Gazell host that dumps packets over UART:
  https://github.com/NordicPlayground/nrf51-ble-gzll-device-uart
- `gzp` pairing library (this controller does **not** use it — no crypto in our firmware):
  gzp.c https://github.com/wangdong/cpod/blob/master/lib/nrf24/gazell/common/gzp.c ·
  docs https://docs.nordicsemi.com/r/bundle/sdk_nrf5_v16.0.0/page/lib_gzp.html
- To re-create the dongle: flash Nordic's stock Gazell **host** example onto an nRF52840
  dongle (stock Gazell + default params → pairs out-of-box). The Nano+nRF24 cannot
  host-sync Gazell.

## nRF51 SWD dump / unlock (used here)
- **nrfsec** — non-destructive readback-protection bypass + mass-erase:
  https://github.com/buildxyz-git/nrfsec ·
  https://www.optiv.com/blog/automated-unlocking-nrf51-series-socs-nrfsec
- Prior art: Include Security 2015 (Cortex-M0 read bypass)
  https://blog.includesecurity.com/2015/11/firmware-dumping-technique-for-an-arm-cortex-m0-soc/ ·
  Pentest Partners 2018 (mass-erase route)
  https://www.pentestpartners.com/security-blog/nrf51822-code-readout-protection-bypass-a-how-to

## nRF24 sniffing (RF phase, verify only)
- gr-nordic (GNU Radio + Wireshark ESB dissector): https://github.com/BastilleResearch/gr-nordic
- MouseJack (unencrypted-HID flaw; N/A here): https://www.bastille.net/research/mousejack
- Sniffing primer: https://hackaday.com/2014/08/05/sniffing-nrf24l01-traffic-with-wireshark
