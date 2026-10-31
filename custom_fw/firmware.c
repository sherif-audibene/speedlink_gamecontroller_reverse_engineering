/* Minimal nRF51822 firmware: mirror GPIO inputs to RAM for SWD readout.
 * Milestone 1 - read the controller's buttons over ST-Link.
 * LOG_MAGIC  @0x20001000 = 0xB00B1E5 (proves our fw is running)
 * LOG_COUNT  @0x20001004 = heartbeat (increments fast)
 * LOG_GPIOIN @0x20001008 = live GPIO IN (button bits; pressed button -> bit goes 0)
 */
#define GPIO_IN     (*(volatile unsigned int*)0x50000510)
#define PIN_CNF(n)  (*(volatile unsigned int*)(0x50000700 + (n)*4))
#define LOG_MAGIC   (*(volatile unsigned int*)0x20001000)
#define LOG_COUNT   (*(volatile unsigned int*)0x20001004)
#define LOG_GPIOIN  (*(volatile unsigned int*)0x20001008)

void _start(void){
    /* configure all GPIO as input with pull-up (buttons short to GND -> read 0) */
    for (int i = 0; i < 31; i++) PIN_CNF(i) = 0x00;  /* input, NO pull (external pullups read buttons; no motor drive) */
    LOG_MAGIC = 0x0B00B1E5;
    LOG_COUNT = 0;
    while (1) {
        LOG_GPIOIN = GPIO_IN;
        LOG_COUNT++;
    }
}

typedef void (*vec_t)(void);
__attribute__((section(".vectors"), used))
const vec_t vectors[] = {
    (vec_t)0x20008000,   /* initial SP = top of 32KB RAM */
    _start,              /* reset vector (thumb bit set by compiler) */
};
