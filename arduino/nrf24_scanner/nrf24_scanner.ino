// Promiscuous sniffer PARKED on Gazell default channel table {4,25,42,63,77}.
// Long dwell so a hopping device is caught every time it lands here.
// CE=9 CSN=10 SCK=13 MOSI=11 MISO=12, SPI 4MHz.
#include <SPI.h>
#include <RF24.h>

RF24 radio(9, 10, 4000000);
const uint8_t CHANS[] = {32};  // locked on controller channel
const uint8_t NC = sizeof(CHANS);
const uint16_t DWELL_MS = 900;
// Data rate: 0=2M (Gazell default). Change by reflashing if needed.
#define RATE RF24_2MBPS
#define RATE_NAME "2M"

void setup() {
  Serial.begin(115200);
  if (!radio.begin()) { Serial.println("radio not found"); while (1); }
  radio.setAutoAck(false);
  radio.disableCRC();
  radio.setPayloadSize(32);
  radio.setAddressWidth(2);
  radio.openReadingPipe(0, 0x00AAULL);
  radio.openReadingPipe(1, 0x0055ULL);
  radio.setDataRate(RATE);
  radio.setPALevel(RF24_PA_MIN);
  Serial.println("park-sniff ready");
}

void loop() {
  for (uint8_t i = 0; i < NC; i++) {
    uint8_t ch = CHANS[i];
    radio.setChannel(ch);
    radio.startListening();
    uint32_t t = millis();
    while (millis() - t < DWELL_MS) {
      if (radio.available()) {
        uint8_t buf[32];
        radio.read(buf, 32);
        Serial.print(RATE_NAME); Serial.print(" ch"); Serial.print(ch); Serial.print(':');
        for (uint8_t k = 0; k < 32; k++) { if (buf[k] < 16) Serial.print('0'); Serial.print(buf[k], HEX); }
        Serial.println();
      }
    }
    radio.stopListening();
  }
}
