/* HC4051 mux button reader v2. selects P0.09/10/11, mux out -> ADC AIN0 (P0.26).
 * Set ALL analog pins (AIN0..7) to analog-input (don't load the analog bus).
 * selects = output; every other pin driven LOW (motor safe). Longer settle. */
#define OUT     (*(volatile unsigned*)0x50000504)
#define OUTSET  (*(volatile unsigned*)0x50000508)
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
static const unsigned char ainpin[8]={26,27,1,2,3,4,5,6};
static unsigned adc0(void){
    ADC_CFG=(1u<<8)|2u;  /* PSEL=AIN0, INPSEL=0 (no prescale, high-Z ok), RES=10 */
    ADC_EN=1; ADC_END=0; ADC_START=1; while(!ADC_END){} ADC_EN=0;
    return ADC_RES&0x3FF;
}
void _start(void){
    OUTCLR=0xFFFFFFFF; DIRSET=0xFFFFFFFF;            /* all output low */
    for(int i=0;i<8;i++){ DIRCLR=(1u<<ainpin[i]); PINCNF(ainpin[i])=0x02; } /* AIN pins analog */
    PINCNF(9)=0x01; PINCNF(10)=0x01; PINCNF(11)=0x01; /* selects output */
    MAGIC=0x4D555832; COUNT=0;
    for(;;){
        for(unsigned ch=0; ch<8; ch++){
            OUTCLR=(7u<<9);
            OUTSET=((ch&1)<<9)|(((ch>>1)&1)<<10)|(((ch>>2)&1)<<11);
            for(volatile int d=0; d<2000; d++){}       /* longer settle */
            CH(ch)=adc0();
        }
        COUNT++;
    }
}
typedef void(*v)(void);
__attribute__((section(".vectors"),used)) const v vectors[]={(v)0x20008000,_start};
