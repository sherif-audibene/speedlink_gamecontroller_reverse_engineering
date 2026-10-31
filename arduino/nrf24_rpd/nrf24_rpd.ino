// nRF24L01+ FAST channel activity scanner (raw SPI, RPD-based). No RF24 lib.
// CE=9 CSN=10 SCK=13 MOSI=11 MISO=12.
#include <SPI.h>
#define CE 9
#define CSN 10
#define R_RF_CH 0x05
#define R_RPD   0x09
uint8_t counts[126];
const uint8_t SAMPLES = 60;

uint8_t rreg(uint8_t r){ digitalWrite(CSN,LOW); SPI.transfer(r&0x1F); uint8_t v=SPI.transfer(0xFF); digitalWrite(CSN,HIGH); return v; }
void wreg(uint8_t r,uint8_t v){ digitalWrite(CSN,LOW); SPI.transfer(0x20|(r&0x1F)); SPI.transfer(v); digitalWrite(CSN,HIGH); }

void setup(){
  Serial.begin(115200);
  pinMode(CE,OUTPUT); pinMode(CSN,OUTPUT);
  digitalWrite(CE,LOW); digitalWrite(CSN,HIGH);
  SPI.begin();
  SPI.beginTransaction(SPISettings(4000000, MSBFIRST, SPI_MODE0));
  delay(5);
  wreg(0x01,0x00);      // EN_AA off
  wreg(0x00,0x03);      // CONFIG: PWR_UP + PRIM_RX, CRC off
  delay(5);             // power-up settle
  if(rreg(0x00)!=0x03){ Serial.println("radio not found - check wiring"); while(1); }
  Serial.println("rpd-scan ready");
}

void loop(){
  memset(counts,0,sizeof(counts));
  for(uint8_t s=0;s<SAMPLES;s++){
    for(uint8_t ch=0;ch<=125;ch++){
      digitalWrite(CE,LOW);
      wreg(R_RF_CH,ch);
      digitalWrite(CE,HIGH);
      delayMicroseconds(200);        // RX settle + RPD integration
      if(rreg(R_RPD)&1) counts[ch]++;
      digitalWrite(CE,LOW);
    }
  }
  Serial.print("SCAN");
  for(uint8_t ch=0;ch<=125;ch++)
    if(counts[ch]){ Serial.print(' '); Serial.print(ch); Serial.print('='); Serial.print(counts[ch]); }
  Serial.println();
}
