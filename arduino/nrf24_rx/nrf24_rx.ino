// HISTORICAL (day 1/2): 010276 @ 2M is NOT the controller's pairing link (that is 250k,
// 5-byte addr - see PAIRING_PROTOCOL.md / nrf24_host). Kept for the record.
// Act as ESB receiver/host for the controller: RX on addr 010276, ch32, 2M, auto-ack ON.
// Goal: ack the controller so it leaves beacon mode and streams button data.
// CE=9 CSN=10 SCK=13 MOSI=11 MISO=12, SPI 4MHz.
#include <SPI.h>
#include <RF24.h>
RF24 radio(9, 10, 4000000);

// On-air address bytes 01 02 76. Try this byte order; swap to 0x760201 if no RX.
const uint64_t ADDR = 0x010276ULL;
const uint8_t CHANS[] = {32,31,33,29,47,48,59,61,63,65};  // ch32 first, then rest of table
const uint8_t NC = sizeof(CHANS);

void cfg(){
  radio.setAddressWidth(3);
  radio.setDataRate(RF24_2MBPS);
  radio.setCRCLength(RF24_CRC_16);
  radio.setAutoAck(true);                 // <-- ack received packets
  radio.enableDynamicPayloads();
  radio.openReadingPipe(1, ADDR);
  radio.setPALevel(RF24_PA_HIGH);         // PA module: push ack back to controller
  radio.setChannel(32);
  radio.startListening();
}
void setup(){
  Serial.begin(115200);
  if(!radio.begin()){ Serial.println("radio not found"); while(1);}
  cfg();
  Serial.println("rx-ack ready on ch32 addr010276 2M");
}

uint32_t lastRx=0; uint8_t ci=0;
void loop(){
  if(radio.available()){
    uint8_t len=radio.getDynamicPayloadSize(); if(len>32)len=32;
    uint8_t buf[32]; radio.read(buf,len);
    lastRx=millis();
    Serial.print("RX ch"); Serial.print(CHANS[ci]); Serial.print(" len"); Serial.print(len); Serial.print(':');
    for(uint8_t i=0;i<len;i++){ if(buf[i]<16)Serial.print('0'); Serial.print(buf[i],HEX);}
    Serial.println();
  }
  // if quiet for 300ms, hop to next table channel to find the controller
  if(millis()-lastRx>300){
    ci=(ci+1)%NC;
    radio.setChannel(CHANS[ci]);
    lastRx=millis();
  }
}
