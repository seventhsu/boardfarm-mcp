/******************************************************************************
 * Bare-metal blink test for STM32H755ZI-Q Nucleo
 * Target: User LED LD1 (Green) on PG12
 * Core: Cortex-M7 (main core at 0x08000000)
 ******************************************************************************/

/* Memory regions */
#define RAM_BASE     0x24000000
#define FLASH_BASE   0x08000000

/* RCC registers - Reset and Clock Control */
#define RCC_BASE     0x58024400
#define RCC_AHB4ENR  (*(volatile unsigned int *)(RCC_BASE + 0xE0))

#define RCC_AHB4ENR_GPIOGEN  (1 << 6)  /* GPIOG clock enable */

/* GPIO registers */
#define GPIOG_BASE   0x58021800
#define GPIOG_MODER  (*(volatile unsigned int *)(GPIOG_BASE + 0x00))
#define GPIOG_ODR    (*(volatile unsigned int *)(GPIOG_BASE + 0x14))
#define GPIOG_BSRR   (*(volatile unsigned int *)(GPIOG_BASE + 0x18))

#define LED_PIN      12  /* PG12 - LD1 Green */

/* Simple delay */
static void delay(volatile unsigned int count)
{
    while (count--);
}

/* Entry point - resets to this address */
void reset_handler(void)
{
    /* Enable GPIOG clock */
    RCC_AHB4ENR |= RCC_AHB4ENR_GPIOGEN;
    
    /* Set PG12 as output (MODER12 = 01) */
    GPIOG_MODER &= ~(3 << (LED_PIN * 2));  /* Clear mode bits */
    GPIOG_MODER |=  (1 << (LED_PIN * 2));  /* Set as output */
    
    /* Blink forever */
    while (1) {
        GPIOG_BSRR = (1 << LED_PIN);        /* Set PG12 (LED on) */
        delay(5000000);
        GPIOG_BSRR = (1 << (LED_PIN + 16)); /* Reset PG12 (LED off) */
        delay(5000000);
    }
}

/* Vector table - minimal for M7 core */
__attribute__((section(".isr_vector")))
void (*const vector_table[])(void) = {
    (void (*)(void))(RAM_BASE + 0x10000),  /* Initial SP (top of DTCM) */
    reset_handler,                         /* Reset handler */
};
