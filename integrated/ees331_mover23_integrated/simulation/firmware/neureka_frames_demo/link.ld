ENTRY(_start)
SECTIONS {
    . = 0;
    .text : { *(.text.start) *(.text .text.*) }
    .rodata : { *(.rodata .rodata.* .srodata .srodata.*) }
    .data : { *(.data .data.* .sdata .sdata.*) }
    .bss : { *(.bss .bss.* .sbss .sbss.* COMMON) }
    ASSERT(SIZEOF(.text) <= 0x10000, "main IMEM overflow")
    ASSERT(SIZEOF(.rodata) == 0 && SIZEOF(.data) == 0 && SIZEOF(.bss) == 0,
           "demo must keep runtime data in SRAM, not instruction ROM")
}
