# Learning guide: how to get good at firmware reverse engineering

How the skills used in this project can be learned. Most of what worked here was **method, not
magic**, and there were plenty of mistakes along the way:
- the 2 Mbps assumption
- a debug tool that froze the CPU
- an ack-flush race

What fixed them was a **verification loop**: guess → test against the real hardware → correct.
That loop can be learned.

## 1. Foundations (what makes everything else readable)
- **C and how it compiles.** Read a function in C and in ARM Thumb assembly side by side.
  Compile small C files with `arm-none-eabi-gcc -O2 -S` and read the `.s` output: loops,
  switch tables, struct access, function calls.
- **Embedded basics.** Memory-mapped registers, interrupts and vector tables, linker scripts,
  the startup code that runs before `main`. Write bare-metal code for one board without any library.
- **Read datasheets and reference manuals.** Half of this project was "what does writing `2` to
  `0x40001510` mean?" The nRF51 Reference Manual answered it (`RADIO.MODE` = 250 kbps).
  Get comfortable looking up any register address.
- **Protocol basics:** SPI, UART, I²C, and for radio, ESB/Gazell, CRC, preambles and addressing.

## 2. Tools to get fluent with
- **Ghidra:** importing raw binaries (pick the language and base address), recognising literal pools,
  renaming and retyping as you go, cross-references. The skill is "follow the reference", not
  "read everything".
- **SWD/JTAG with pyOCD or OpenOCD:** read and write memory live, halt and step, dump flash.
  **Reading a live peripheral register beat hours of static analysis in this project.**
- **A logic analyser** (a ~€10 Saleae clone + PulseView) for SPI/UART/I²C, and an **SDR or an nRF24
  sniffer** for radio.
- **Python for glue:** small scripts that poll, diff and log. Almost every breakthrough here
  came from a ~30-line script (`tools/radio_state.py`, `tools/peek_pairing.py`, `tools/stick_probe.py`).

## 3. Practice path (in order)
1. Flash and debug your own code on a cheap board (nRF52 DK, Blue Pill, RP2040). Break it on
   purpose and find the bug with the debugger.
2. **Reverse your own compiled firmware.** Build a small program, strip it, load it in Ghidra and
   recover the function names. You know the answer, so you get feedback.
3. **Crackmes / CTFs:** microcorruption.com (embedded-style, excellent), pwn.college's reversing
   modules, and the "hardware" categories of CTFs.
4. **A real device you own** with debug pads: an old fitness tracker, a wireless mouse or keyboard
   (MouseJack-style research), a cheap smart plug. Dump it, map it, document it, exactly like this repo.

## 4. Habits that mattered most in this project
- **Treat every conclusion as a hypothesis with a test.** "The Nano can't be the host" was wrong
  because it was tested at the wrong data rate (`RF_SNIFFING.md`).
- **When two sources disagree, measure the live system.** Static analysis and the sniffer
  disagreed; the radio registers settled it in one read (`PAIRING_PROTOCOL.md` §6.2).
- **Suspect your own tools.** The "deaf pipe 0" was really the monitor halting the CPU (§6.4).
- **Change one thing at a time**, and make every step confirm itself: the `ok:` echo in the Nano
  sketches, `make_locked_rom.py --selftest`, reading flash back after every write.
- **Write it down as you go, including what was wrong.** The journey section of
  `PAIRING_PROTOCOL.md` is the most educational part of this repo.

## 5. Reading that pays off
- *The Hardware Hacking Handbook* (van Woudenberg & O'Flynn). The best single book for this.
- *Practical Reverse Engineering* (Dang et al.) for the ARM / Thumb chapters.
- The Ghidra courses that ship with Ghidra (`docs/GhidraClass`), plus the Include Security /
  Pentest Partners nRF51 write-ups linked in `RESEARCH.md`.
- **Vendor SDK source.** Reading Nordic's `nrf_gzll` and drivers made them easy to spot in the
  binary (`FIRMWARE_FUNCTIONS.md`: a third of the ROM is near-stock SDK code). "Recognise the
  library" saves most of the work.

## 6. Exercises based on this repo
- Rewrite `arduino/nrf24_host` from scratch using only `PAIRING_PROTOCOL.md`.
- Find and test the bond-wipe fix (`bl 0x3ab0` at `0x3908`, see `FIRMWARE_FUNCTIONS.md`) and add it
  to `tools/make_locked_rom.py` with a self-test.
- Drive the rumble motors from the Nano via the step-4 ack bytes 3 and 4.
- Follow the stock LFSR channel hopping from the host, so the fixed-channel patch can be dropped.
- Confirm or refute the `_maybe` function names in the Ghidra project.

Using AI as a sparring partner works well: have it explain one function at a time, then **verify
the claim yourself** on the hardware.
