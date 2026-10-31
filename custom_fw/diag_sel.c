/* Diagnostic: drive ALL pins low, then drive the 3 mux-select pins
 * (P0.09,10,11) HIGH. If the motor buzzes -> a select pin is the trigger. */
#define OUTCLR    (*(volatile unsigned int*)0x5000050C)
#define OUTSET    (*(volatile unsigned int*)0x50000508)
#define DIRSET    (*(volatile unsigned int*)0x50000518)
void _start(void){
    OUTCLR = 0xFFFFFFFF;
    DIRSET = 0xFFFFFFFF;
    OUTSET = (1u<<9)|(1u<<10)|(1u<<11);   /* drive selects high */
    while (1) { }
}
typedef void(*v)(void);
__attribute__((section(".vectors"),used))
const v vectors[]={(v)0x20008000,_start};
