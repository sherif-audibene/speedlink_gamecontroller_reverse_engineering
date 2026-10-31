/* Safe-hold firmware: drive ALL pins as output LOW forever. Motors/LEDs OFF.
 * No button reading - just makes the controller safe on any power-up. */
#define OUTCLR  (*(volatile unsigned int*)0x5000050C)
#define DIRSET  (*(volatile unsigned int*)0x50000518)
#define LOG_MAGIC (*(volatile unsigned int*)0x20001000)
void _start(void){
    OUTCLR = 0xFFFFFFFF;   /* all outputs low */
    DIRSET = 0xFFFFFFFF;   /* all pins output */
    LOG_MAGIC = 0x5AFE0000;
    while (1) { OUTCLR = 0xFFFFFFFF; }  /* keep them low */
}
typedef void(*v)(void);
__attribute__((section(".vectors"),used))
const v vectors[]={(v)0x20008000,_start};
