/* Startup code for STM32H755ZI - Cortex-M7 */
.syntax unified
.cpu cortex-m7
.fpu fpv5-d16
.thumb

.global g_pfnVectors
.global Reset_Handler
.global Default_Handler

/* Start of code section */
.section .isr_vector,"a",%progbits

g_pfnVectors:
    .word _estack               /* Top of stack */
    .word Reset_Handler         /* Reset Handler */
    .word Default_Handler       /* NMI Handler */
    .word Default_Handler       /* Hard Fault Handler */
    .word Default_Handler       /* MPU Fault Handler */
    .word Default_Handler       /* Bus Fault Handler */
    .word Default_Handler       /* Usage Fault Handler */
    .word 0                     /* Reserved */
    .word 0                     /* Reserved */
    .word 0                     /* Reserved */
    .word 0                     /* Reserved */
    .word Default_Handler       /* SVCall Handler */
    .word Default_Handler       /* Debug Monitor Handler */
    .word 0                     /* Reserved */
    .word Default_Handler       /* PendSV Handler */
    .word Default_Handler       /* SysTick Handler */

/* Reset handler */
.section .text.Reset_Handler,"ax",%progbits
.weak Reset_Handler

Reset_Handler:
    /* Set stack pointer */
    ldr sp, =_estack
    
    /* Copy data section from flash to RAM */
    ldr r0, =_sdata
    ldr r1, =_edata
    ldr r2, =_sidata
    movs r3, #0
    b LoopCopyDataInit

CopyDataInit:
    ldr r4, [r2, r3]
    str r4, [r0, r3]
    adds r3, r3, #4

LoopCopyDataInit:
    adds r4, r0, r3
    cmp r4, r1
    bcc CopyDataInit
    
    /* Zero fill bss section */
    ldr r2, =_sbss
    ldr r4, =_ebss
    movs r3, #0
    b LoopFillZerobss

FillZerobss:
    str r3, [r2]
    adds r2, r2, #4

LoopFillZerobss:
    cmp r2, r4
    bcc FillZerobss
    
    /* Call main */
    bl main
    
    /* Infinite loop if main returns */
    b .

/* Default handler */
.section .text.Default_Handler,"ax",%progbits
.weak Default_Handler

Default_Handler:
    b Default_Handler
