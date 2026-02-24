/* STM32H755ZI Linker Script - M7 core, 2MB Flash, 1MB RAM */

MEMORY
{
    FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 2048K
    DTCM (rwx)  : ORIGIN = 0x20000000, LENGTH = 128K
    RAM (rwx)   : ORIGIN = 0x24000000, LENGTH = 512K
}

ENTRY(reset_handler)

SECTIONS
{
    .text : {
        *(.isr_vector)
        *(.text*)
        *(.rodata*)
        _etext = .;
    } > FLASH

    _sidata = LOADADDR(.data);
    
    .data : {
        _sdata = .;
        *(.data*)
        _edata = .;
    } > RAM AT > FLASH

    .bss : {
        _sbss = .;
        *(.bss*)
        *(COMMON)
        _ebss = .;
    } > RAM
}
