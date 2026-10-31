// Gazell/ESB pairing harness v2 - reliable ack-payload delivery.
// PRX on addr 010276, ch32, 2M, CRC16, auto-ack WITH configurable ack payload.
// Keeps ack FIFO topped; does NOT print every packet (that starved the FIFO).
// Reports only NEW distinct payloads + periodic counts. Also listens pipe2 for
// post-pairing data address.
// Serial cmds: K<hex>=ack payload (differentiated: see KA/KF), C<dec>=channel,
//   KF<hex>=ack payload used in response to 1-byte "fetch" packets,
//   KA<hex>=ack payload used in response to other packets,
//   D<hex>=pipe2 data addr, P=print cfg, Z=reset counters.
// CE=9 CSN=10 SCK=13 MOSI=11 MISO=12.
#include <SPI.h>
#include <RF24.h>
RF24 radio(9, 10, 4000000);
const uint64_t PAIR_ADDR = 0x010276ULL;

uint8_t ackA[32], ackAl=0;     // ack for multi-byte request packets
uint8_t ackF[32], ackFl=0;     // ack for 1-byte fetch packets
uint64_t dataAddr=0; uint8_t dataAW=0;
uint8_t chan=32;
char line[90]; uint8_t li=0;

// distinct-payload tracker
uint8_t seen[8][20]; uint8_t seenLen[8]; uint16_t seenCnt[8]; uint8_t nSeen=0;
uint8_t hx(char c){ if(c>='0'&&c<='9')return c-'0'; c|=0x20; if(c>='a'&&c<='f')return c-'a'+10; return 0; }
uint8_t parseHex(char*s,uint8_t*out){ uint8_t n=0; while(*s&&*(s+1)&&n<32){ out[n++]=(hx(*s)<<4)|hx(*(s+1)); s+=2;} return n; }

void applyCfg(){
  radio.stopListening();
  radio.setAddressWidth(3);
  radio.setChannel(chan);
  radio.setDataRate(RF24_2MBPS);
  radio.setCRCLength(RF24_CRC_16);
  radio.setAutoAck(true);
  radio.enableDynamicPayloads();
  radio.enableAckPayload();
  radio.openReadingPipe(1, PAIR_ADDR);
  if(dataAW){ radio.setAddressWidth(dataAW); radio.openReadingPipe(2, dataAddr); radio.setAddressWidth(3);}
  radio.setPALevel(RF24_PA_HIGH);
  radio.startListening();
}
void setup(){
  Serial.begin(115200);
  if(!radio.begin()){ Serial.println("radio not found"); while(1);}
  applyCfg();
  Serial.println("pair v2 ready");
}
int findSeen(uint8_t*b,uint8_t l){
  for(uint8_t i=0;i<nSeen;i++){ if(seenLen[i]==l){ uint8_t eq=1; for(uint8_t k=0;k<l;k++) if(seen[i][k]!=b[k]){eq=0;break;} if(eq)return i; } }
  return -1;
}
void printPkt(const char*tag,uint8_t pipe,uint8_t*b,uint8_t l){
  Serial.print(tag); Serial.print(" R"); Serial.print(pipe); Serial.print(':');
  for(uint8_t i=0;i<l;i++){ if(b[i]<16)Serial.print('0'); Serial.print(b[i],HEX);} Serial.println();
}
uint32_t lastTick=0;
void loop(){
  uint8_t pipe;
  if(radio.available(&pipe)){
    uint8_t len=radio.getDynamicPayloadSize(); if(len>32)len=32;
    uint8_t buf[32]; radio.read(buf,len);
    // immediately top up ack FIFO for the NEXT packet
    if(len==1){ if(ackFl) radio.writeAckPayload(pipe,ackF,ackFl);}
    else { if(ackAl) radio.writeAckPayload(pipe,ackA,ackAl);}
    int idx=findSeen(buf,len);
    if(idx<0 && nSeen<8){ idx=nSeen++; seenLen[idx]=len; for(uint8_t k=0;k<len;k++)seen[idx][k]=buf[k]; seenCnt[idx]=0; printPkt("NEW",pipe,buf,len); }
    if(idx>=0) seenCnt[idx]++;
  }
  // top up ack FIFO opportunistically
  if(ackAl) radio.writeAckPayload(1,ackA,ackAl);
  if(ackFl) radio.writeAckPayload(1,ackF,ackFl);
  if(millis()-lastTick>1500){ lastTick=millis(); Serial.print("tick"); for(uint8_t i=0;i<nSeen;i++){ Serial.print(' '); Serial.print(seenLen[i]); Serial.print('/'); Serial.print(seenCnt[i]); } Serial.println(); }
  while(Serial.available()){
    char c=Serial.read();
    if(c=='\n'||c=='\r'){ if(li){ line[li]=0;
        if(line[0]=='K'&&line[1]=='F') ackFl=parseHex(line+2,ackF);
        else if(line[0]=='K'&&line[1]=='A') ackAl=parseHex(line+2,ackA);
        else if(line[0]=='K'){ ackAl=parseHex(line+1,ackA); ackFl=ackAl; for(uint8_t k=0;k<ackAl;k++)ackF[k]=ackA[k]; }
        else if(line[0]=='C'){ chan=atoi(line+1); applyCfg(); }
        else if(line[0]=='D'){ uint8_t tmp[5]; uint8_t n=parseHex(line+1,tmp); dataAW=n; dataAddr=0; for(int i=n-1;i>=0;i--)dataAddr=(dataAddr<<8)|tmp[i]; applyCfg(); }
        else if(line[0]=='Z'){ nSeen=0; }
        else if(line[0]=='P'){ Serial.print("chan="); Serial.print(chan); Serial.print(" ackA="); Serial.print(ackAl); Serial.print(" ackF="); Serial.print(ackFl); Serial.print(" dataAW="); Serial.println(dataAW); }
        Serial.print("ok:"); Serial.println(line);
        li=0; }
    } else if(li<sizeof(line)-1) line[li++]=c;
  }
}
