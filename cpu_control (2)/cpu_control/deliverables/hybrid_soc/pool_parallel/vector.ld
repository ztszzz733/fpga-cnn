OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS { .vectors 0 : { *(.vectors) } .text 0x80 : { *(.text*) } }
