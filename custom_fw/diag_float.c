/* Diagnostic: drive ALL pins low, then FLOAT only the 5 analog pins
 * (P0.03,04,05,06,26). If the motor buzzes -> the analog pins are the trigger. */
#define OUTCLR    (*(volatile unsigned int*)0x5000050C)
#define DIRSET    (*(volatile unsigned int*)0x50000518)
#define PINCNF(n) (*(volatile unsigned int*)(0x50000700+(n)*4))
void _start(void){
    OUTCLR = 0xFFFFFFFF;   /* all low */
    DIRSET = 0xFFFFFFFF;
    PINCNF(3)  = 0x02;     /* float the 5 analog pins (input, buffer disconnected) */
    PINCNF(4)  = 0x02;
    PINCNF(5)  = 0x02;
    PINCNF(6)  = 0x02;
    PINCNF(26) = 0x02;
    while (1) { }
}
typedef void(*v)(void);
__attribute__((section(".vectors"),used))
const v vectors[]={(v)0x20008000,_start};
