.option norvc
.option norelax
.section .start,"ax"
.global _start
_start:
 li sp,0x3fff0
 call main
1: j 1b
