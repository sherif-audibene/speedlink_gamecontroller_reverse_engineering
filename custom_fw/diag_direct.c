/* Diagnostic: drive ALL pins low, then set the 7 direct-button pins
 * (P0.21,23,22,28,29,14,15) to INPUT+PULLUP. If the motor buzzes ->
 * a direct-button pull-up is the trigger. */
#define OUTCLR    (*(volatile unsigned int*)0x5000050C)
#define DIRSET    (*(volatile unsigned int*)0x50000518)
#define PINCNF(n) (*(volatile unsigned int*)(0x50000700+(n)*4))
void _start(void){
    OUTCLR = 0xFFFFFFFF;
    DIRSET = 0xFFFFFFFF;
    PINCNF(21) = 0x0C;   /* input + pull-up */
    PINCNF(23) = 0x0C;
    PINCNF(22) = 0x0C;
    PINCNF(28) = 0x0C;
    PINCNF(29) = 0x0C;
    PINCNF(14) = 0x0C;
    PINCNF(15) = 0x0C;
    while (1) { }
}
typedef void(*v)(void);
__attribute__((section(".vectors"),used))
const v vectors[]={(v)0x20008000,_start};
