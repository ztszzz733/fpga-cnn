OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY {
    IMEM (rx) : ORIGIN = 0x0000, LENGTH = 8K
    DMEM (rw) : ORIGIN = 0x2000, LENGTH = 8K
}
SECTIONS {
    .text : {
        KEEP(*(.text.start))
        *(.text .text.* .gnu.linkonce.t.*)
        . = ALIGN(4);
    } > IMEM
    .data : {
        *(.rodata .rodata.*)
        *(.srodata .srodata.*)
        *(.data .data.* .sdata .sdata.*)
        . = ALIGN(4);
    } > DMEM
    .bss (NOLOAD) : {
        *(.bss .bss.* .sbss .sbss.* COMMON)
        . = ALIGN(4);
    } > DMEM
    __stack_top = ORIGIN(DMEM) + LENGTH(DMEM);
    ASSERT(. <= __stack_top - 1024, "DMEM globals leave less than 1 KiB stack")
    /DISCARD/ : { *(.comment .note* .eh_frame*) }
}
