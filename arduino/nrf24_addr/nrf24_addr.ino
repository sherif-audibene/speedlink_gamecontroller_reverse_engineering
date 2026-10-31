// Try common ESB/Gazell addresses with CRC16 ON. Valid CRC = real packet = address found.
// CE=9 CSN=10 SCK=13 MOSI=11 MISO=12, SPI 4MHz.
#include <SPI.h>
#include <RF24.h>
RF24 radio(9, 10, 4000000);

// Candidate 5-byte addresses (LSB-first as RF24 wants). Add more freely.
const uint64_t ADDRS[] = {
  0xE7E7E7E7E7ULL, 0xA8A8A8A8A8ULL, 0x0C0C0C0C0CULL,
  0x7E7E7E7E7EULL, 0x1A1A1A1A1AULL, 0xC2C2C2C2C2ULL,
  0xE7E7E7E7E7ULL
};
const uint8_t NA = sizeof(ADDRS)/sizeof(ADDRS[0]);
const rf24_datarate_e RATES[] = {RF24_2MBPS, RF24_1MBPS};
const char* RN[] = {"2M","1M"};

void setup(){
  Serial.begin(115200);
  if(!radio.begin()){ Serial.println("radio not found"); while(1);}
  radio.setAutoAck(false);
  radio.enableDynamicPayloads();
  radio.setCRCLength(RF24_CRC_16);
  radio.setAddressWidth(5);
  radio.setPALevel(RF24_PA_MIN);
  Serial.println("addr-scan ready");
}

void loop(){
  for(uint8_t a=0;a<NA;a++){
    for(uint8_t r=0;r<2;r++){
      radio.setDataRate(RATES[r]);
      radio.openReadingPipe(1, ADDRS[a]);
      for(uint8_t ch=0; ch<=83; ch++){
        radio.setChannel(ch);
        radio.startListening();
        uint32_t t=millis();
        while(millis()-t<15){
          if(radio.available()){
            uint8_t len=radio.getDynamicPayloadSize();
            uint8_t buf[32];
            if(len>32) len=32;
            radio.read(buf,len);
            Serial.print("HIT addr="); Serial.print((uint32_t)(ADDRS[a]>>8),HEX);
            Serial.print((uint32_t)(ADDRS[a]&0xFF),HEX);
            Serial.print(' '); Serial.print(RN[r]); Serial.print(" ch"); Serial.print(ch);
            Serial.print(" len"); Serial.print(len); Serial.print(':');
            for(uint8_t i=0;i<len;i++){ if(buf[i]<16)Serial.print('0'); Serial.print(buf[i],HEX);}
            Serial.println();
          }
        }
        radio.stopListening();
      }
    }
  }
}
