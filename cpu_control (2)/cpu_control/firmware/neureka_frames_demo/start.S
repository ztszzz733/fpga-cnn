.section .text.start
.global _start
_start:
    lui sp, 0x40
    addi sp, sp, -16
    jal ra, main
1:  j 1b
