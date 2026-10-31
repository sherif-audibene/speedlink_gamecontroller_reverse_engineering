// nRF24 SPI connectivity diagnostic (no RF24 lib). CE=9 CSN=10 SCK=13 MOSI=11 MISO=12
#include <SPI.h>
#define CE 9
#define CSN 10
uint8_t rreg(uint8_t r){ digitalWrite(CSN,LOW); SPI.transfer(r&0x1F); uint8_t v=SPI.transfer(0xFF); digitalWrite(CSN,HIGH); return v; }
void wreg(uint8_t r,uint8_t v){ digitalWrite(CSN,LOW); SPI.transfer(0x20|(r&0x1F)); SPI.transfer(v); digitalWrite(CSN,HIGH); }
void setup(){
  Serial.begin(115200);
  pinMode(CE,OUTPUT); pinMode(CSN,OUTPUT);
  digitalWrite(CE,LOW); digitalWrite(CSN,HIGH);
  SPI.begin();
  SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));
  delay(100);
  Serial.println("=== nRF24 SPI diag ===");
  uint8_t cfg=rreg(0x00);
  Serial.print("CONFIG(0x00)=0x"); Serial.println(cfg,HEX);   // ~0x08 after power-up
  // write/readback test on SETUP_AW (0x03): valid values 1..3
  wreg(0x03,0x03); uint8_t a=rreg(0x03);
  wreg(0x03,0x01); uint8_t b=rreg(0x03);
  Serial.print("SETUP_AW wrote3 read=0x"); Serial.print(a,HEX);
  Serial.print("  wrote1 read=0x"); Serial.println(b,HEX);
  if((a==0x03)&&(b==0x01)) Serial.println(">> SPI OK, module responding");
  else if(cfg==0x00||cfg==0xFF) Serial.println(">> DEAD BUS: all 0x00/0xFF - check MISO/power/seating");
  else Serial.println(">> SPI unstable - check SCK/MOSI/MISO wiring & jumpers");
}
void loop(){}
