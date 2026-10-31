/* Read raw ADC AIN0..AIN7 directly (no mux). Store to RAM. Verifies ADC + finds sticks.
 * RAM: 0x20001000 magic 'AIN0', 0x20001004 count, 0x20001008..0x20001024 = AIN0..7 */
#define OUTCLR  (*(volatile unsigned*)0x5000050C)
#define DIRSET  (*(volatile unsigned*)0x50000518)
#define DIRCLR  (*(volatile unsigned*)0x5000051C)
#define PINCNF(n) (*(volatile unsigned*)(0x50000700+(n)*4))
#define ADC_EN    (*(volatile unsigned*)0x40007500)
#define ADC_CFG   (*(volatile unsigned*)0x40007504)
#define ADC_RES   (*(volatile unsigned*)0x40007508)
#define ADC_START (*(volatile unsigned*)0x40007000)
#define ADC_END   (*(volatile unsigned*)0x40007400)
#define MAGIC (*(volatile unsigned*)0x20001000)
#define COUNT (*(volatile unsigned*)0x20001004)
#define CH(i) (*(volatile unsigned*)(0x20001008+(i)*4))
/* AIN -> pin: AIN0=P26 AIN1=P27 AIN2=P1 AIN3=P2 AIN4=P3 AIN5=P4 AIN6=P5 AIN7=P6 */
static const unsigned char ainpin[8]={26,27,1,2,3,4,5,6};
static unsigned adc(unsigned psel){
    ADC_CFG=(psel<<8)|(2<<2)|2; ADC_EN=1; ADC_END=0; ADC_START=1;
    while(!ADC_END){} ADC_EN=0; return ADC_RES&0x3FF;
}
void _start(void){
    OUTCLR=0xFFFFFFFF; DIRSET=0xFFFFFFFF;       /* all output low */
    for(int i=0;i<8;i++){ DIRCLR=(1u<<ainpin[i]); PINCNF(ainpin[i])=0x02; } /* AIN pins analog */
    MAGIC=0x41494E30; COUNT=0;
    for(;;){ for(unsigned a=0;a<8;a++) CH(a)=adc(1u<<a); COUNT++; }
}
typedef void(*v)(void);
__attribute__((section(".vectors"),used)) const v vectors[]={(v)0x20008000,_start};
