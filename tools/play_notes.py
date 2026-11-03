
import serial
import time
import sys
import math
import struct
import pygame

# -----------------------------
# Configuration
# -----------------------------

PORT = "/dev/cu.wchusbserial1110"
BAUD = 115200
SAMPLE_RATE = 44100

# Map HID bits to musical notes
NOTES = {
    0x10: 261.63,  # C4
    0x20: 293.66,  # D4
    0x80: 329.63,  # E4
    0x40: 392.00,  # G4
}

# -----------------------------
# Generate sound
# -----------------------------

pygame.mixer.pre_init(
    frequency=SAMPLE_RATE,
    size=-16,
    channels=1,
    buffer=128
)
pygame.init()

def create_note(freq, duration=0.3):
    samples = int(SAMPLE_RATE * duration)
    audio = bytearray()

    for i in range(samples):
        t = i / SAMPLE_RATE

        # Smooth decay envelope
        envelope = max(0, 1 - t / duration)

        # Sine wave
        value = (
            math.sin(2 * math.pi * freq * t)
            * envelope
            * 12000
        )

        audio.extend(struct.pack("<h", int(value)))

    return pygame.mixer.Sound(buffer=bytes(audio))


sounds = {
    key: create_note(freq)
    for key, freq in NOTES.items()
}

# -----------------------------
# Serial connection
# -----------------------------

s = serial.Serial(PORT, BAUD, timeout=0.001)

s.setDTR(False)
s.setRTS(False)
time.sleep(0.05)

s.setDTR(True)
s.setRTS(True)
time.sleep(0.3)

s.reset_input_buffer()

# -----------------------------
# Main loop
# -----------------------------

dur = int(sys.argv[1]) if len(sys.argv) > 1 else 3600

end = time.time() + dur
previous_mask = 0

print("Listening for keys...")

try:
    while time.time() < end:

        ln = s.readline().decode(errors="replace").strip()

        if not ln.startswith("REP "):
            continue

        try:
            data = bytes.fromhex(ln[4:])
        except ValueError:
            continue

        if len(data) < 5:
            continue

        # Key bits are in byte 4
        current_mask = data[4]

        # Detect newly pressed keys
        pressed = current_mask & ~previous_mask

        for bit, sound in sounds.items():
            if pressed & bit:
                sound.play()
                print(f"Note: {bit:02X}")

        previous_mask = current_mask

except KeyboardInterrupt:
    print("Stopped.")

finally:
    s.close()
    pygame.quit()

