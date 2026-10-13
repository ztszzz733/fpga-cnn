OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS { .text 0 : { *(.start) *(.text*) *(.rodata*) } /DISCARD/ : { *(.eh_frame*) *(.comment*) } }
