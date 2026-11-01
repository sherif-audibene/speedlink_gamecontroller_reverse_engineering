// Speedlink controller HOST (replaces the lost dongle) - nRF24L01+ on Arduino Nano.
// Implements the app-level handshake from PAIRING_PROTOCOL.md:
//   1) pairing addr: ctrl sends A1 <ownID> <hop LFSR>  -> ack 01 <HOST_ID> 000000
//   2) host-ID addr: ctrl sends 82 <ownID> <hostID>    -> ack 02 <HOST_ID> <ownID>
//   3) own-ID addr:  ctrl sends 84 <flags> <19B report> -> ack 04 00000000
// Radio: 250 kbps, CRC16, 5-byte addr, dynamic payload + ack payload, channel 32.
// REQUIRES the patched controller image (tools/make_locked_rom.py ABCDEF): stock firmware
// hops channel every packet and resets on step-2/4 failures. All replies are static, so
// they sit pre-loaded in the ack FIFO - the ATmega never has to react in real time.
// Only pipe1 is used (pipe0 once looked deaf, but that test was invalidated by a halted
// controller - see PAIRING_PROTOCOL.md 6.4); its address walks a RING pairing -> host-ID -> own-ID -> ...
// Advance on SILENCE, not on reception: keep acking the current step until the
// controller stops sending it (= it got our reply and moved on). A lost ack then
// just means another retry on the same address. Wherever the controller is, the
// ring reaches it within one lap. (Controller retries steps 1+2 forever when patched.)
// Serial 115200: prints state changes + input reports (only when they change).
// Wiring: CE=9 CSN=10 SCK=13 MOSI=11 MISO=12 (see RF_SNIFFING.md).
#include <SPI.h>
#include <RF24.h>
#include <EEPROM.h>  // ownId survives Nano resets (controller may already be streaming)

const uint32_t HOST_ID = 0xABCDEF;  // must match the bond record on the controller
const uint32_t PAIR_ID = 0xC1C2C6;  // fixed pairing "ID" (firmware literal @0x4764)
const uint8_t CHANNEL = 32;         // must match the controller patch @0x48c2 (movs r4,#32)

RF24 radio(9, 10, 4000000);
uint32_t ownId = 0;
enum Role : uint8_t { PAIR, CONFIRM, STREAM } role = PAIR;
#define TICK_LOG 0  // 1 = print "tick 81:n 82:n 84:n" (packets/s per step) every second
uint32_t lastRx = 0, lastTick = 0;  // lastRx: last packet of the current role
uint16_t cnt[3];          // packets seen per step this second
uint8_t lastRep[20];

// Gazell ID -> nRF24 address (verified live: C1C2C6 -> 0xC6C2C1E7E7)
uint64_t addrOf(uint32_t id) {
  uint32_t base = ((uint32_t)(id & 0xFF) << 24) | ((uint32_t)((id >> 8) & 0xFF) << 16) |
                  ((uint32_t)((id >> 16) & 0xFF) << 8) | 0xE7;
  return ((uint64_t)base << 8) | 0xE7;
}

void put3(uint8_t* p, uint32_t v) { p[0] = v; p[1] = v >> 8; p[2] = v >> 16; }

// The ack (with our queued payload) goes out ~0.65 ms AFTER RX_DR at 250 kbps.
// Flushing / changing the address before that kills the reply -> controller sees an
// empty ack. So: wait for the TX FIFO to drain (ack sent) before touching anything.
void waitAckSent() {
  uint32_t t = micros();
  while (!radio.isFifo(true, true) && micros() - t < 3000) {}
}

void loadAck() {  // exactly one queued ack, matching the current role
  uint8_t a[7] = {0};
  radio.flush_tx();
  if (role == PAIR) { a[0] = 0x01; put3(a + 1, HOST_ID); radio.writeAckPayload(1, a, 7); }
  else if (role == CONFIRM) { a[0] = 0x02; put3(a + 1, HOST_ID); put3(a + 4, ownId); radio.writeAckPayload(1, a, 7); }
  else { a[0] = 0x04; radio.writeAckPayload(1, a, 5); }
}

void setRole(Role r) {
  role = r; lastRx = millis();
  radio.openReadingPipe(1, r == PAIR ? addrOf(PAIR_ID) : r == CONFIRM ? addrOf(HOST_ID) : addrOf(ownId));
  loadAck();
  Serial.println(r == PAIR ? F("STATE pairing") : r == CONFIRM ? F("STATE confirm (host-ID addr)")
                                                               : F("STATE streaming (own-ID addr)"));
}

void printHex(const uint8_t* b, uint8_t n) {
  for (uint8_t i = 0; i < n; i++) { if (b[i] < 16) Serial.print('0'); Serial.print(b[i], HEX); }
}

void setup() {
  Serial.begin(115200);
  if (!radio.begin()) { Serial.println(F("radio not found")); while (1); }
  radio.setAddressWidth(5);
  radio.setChannel(CHANNEL);
  radio.setDataRate(RF24_250KBPS);
  radio.setCRCLength(RF24_CRC_16);
  radio.setAutoAck(true);
  radio.enableDynamicPayloads();
  radio.enableAckPayload();
  radio.setPALevel(RF24_PA_HIGH);
  EEPROM.get(0, ownId);
  if (ownId > 0xFFFFFF) ownId = 0;  // blank EEPROM
  radio.startListening();
  setRole(PAIR);
  Serial.print(F("host ready id=")); Serial.print(HOST_ID, HEX);
  Serial.print(F(" known ownID=")); Serial.println(ownId, HEX);
}

void loop() {
  uint8_t pipe;
  while (radio.available(&pipe)) {
    uint8_t len = radio.getDynamicPayloadSize();
    uint8_t b[32];
    if (len > 32) { radio.flush_rx(); break; }
    radio.read(b, len);
    waitAckSent();
    uint8_t type = b[0] & 0x8F;
    if (type == 0x81 && len >= 4) {
      cnt[0]++;
      uint32_t id = b[1] | ((uint32_t)b[2] << 8) | ((uint32_t)b[3] << 16);
      if (id != ownId) { ownId = id; EEPROM.put(0, ownId); Serial.print(F("controller ownID=")); Serial.println(ownId, HEX); }
      if (role == PAIR) lastRx = millis();
    } else if (type == 0x82) {
      cnt[1]++;
      if (role == CONFIRM) lastRx = millis();
    } else if (type == 0x84 && len >= 2) {
      cnt[2]++; lastRx = millis();
      uint8_t n = len - 1 > 20 ? 20 : len - 1;
      if (memcmp(lastRep, b + 1, n)) {
        memcpy(lastRep, b + 1, n);
        Serial.print(F("REP ")); printHex(b + 1, n); Serial.println();
      }
    } else {
      Serial.print(F("? p")); Serial.print(pipe); Serial.print(':'); printHex(b, len); Serial.println();
    }
    loadAck();
  }
  // ponytail: fixed 1.5 s silence per step; tune if step retries are slower
  if (millis() - lastRx > 1500) {
    if (role == PAIR) setRole(CONFIRM);
    else if (role == CONFIRM && ownId) setRole(STREAM);
    else setRole(PAIR);
  }
  if (TICK_LOG && millis() - lastTick > 1000) {
    lastTick = millis();
    Serial.print(F("tick 81:")); Serial.print(cnt[0]); Serial.print(F(" 82:")); Serial.print(cnt[1]);
    Serial.print(F(" 84:")); Serial.println(cnt[2]);
    cnt[0] = cnt[1] = cnt[2] = 0;
  }
}
