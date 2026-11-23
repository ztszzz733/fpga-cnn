.section .text.start,"ax",@progbits
.globl _start
_start:
    la sp, __stack_top
    call ees331_run
1:  j 1b
