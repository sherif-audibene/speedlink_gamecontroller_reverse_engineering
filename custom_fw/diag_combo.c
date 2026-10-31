/* Diagnostic: drive ALL pins low, then put EVERY pin the scan touches into its
 * "active" state at once: selects high, analog floating, direct buttons pull-up.
 * If the motor buzzes -> it's the combination of simultaneous non-low pins. */
#define OUTCLR    (*(volatile unsigned int*)0x5000050C)
#define OUTSET    (*(volatile unsigned int*)0x50000508)
#define DIRSET    (*(volatile unsigned int*)0x50000518)
#define PINCNF(n) (*(volatile unsigned int*)(0x50000700+(n)*4))
void _start(void){
    OUTCLR = 0xFFFFFFFF;
    DIRSET = 0xFFFFFFFF;
    /* analog float */
    PINCNF(3)=0x02; PINCNF(4)=0x02; PINCNF(5)=0x02; PINCNF(6)=0x02; PINCNF(26)=0x02;
    /* direct pull-ups */
    PINCNF(21)=0x0C; PINCNF(23)=0x0C; PINCNF(22)=0x0C; PINCNF(28)=0x0C; PINCNF(29)=0x0C;
    PINCNF(14)=0x0C; PINCNF(15)=0x0C;
    /* selects high */
    OUTSET = (1u<<9)|(1u<<10)|(1u<<11);
    while (1) { }
}
typedef void(*v)(void);
__attribute__((section(".vectors"),used))
const v vectors[]={(v)0x20008000,_start};
