OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS {
 .vectors 0 : { *(.vectors) }
 .text 0x1000 : { *(.text*) }
 .data 0x2000 : { *(.data*) }
 .output 0x4000 : { *(.output) }
}
