.option norvc
.option norelax
.section .vectors,"ax"
.org 0x70
 j fail
.org 0x74
 j done
.org 0x80
 j _start
.section .text
.global _start
_start:
 li sp, 0x3fff0
 li t0, 0x6600
 csrs mstatus, t0
 csrw fcsr, zero
 la a0, input_a
 la a1, input_b
 li a2, 0x4000
 li a3, 19

loop:
 vsetvli t1, a3, e32, m1, ta, ma
 vle32.v v1, (a0)
 vle32.v v2, (a1)
 vfadd.vv v3, v1, v2
 vse32.v v3, (a2)
 slli t2, t1, 2
 add a0, a0, t2
 add a1, a1, t2
 add a2, a2, t2
 sub a3, a3, t1
 bnez a3, loop

 fence
 # Dependent read and delay allow the final vector store to drain.
 li t0, 0x4000
 lw t0, 0(t0)
 li t0, 20
wait_drain:
 addi t0, t0, -1
 bnez t0, wait_drain
 sw zero, 0x400(zero)
 li t0, 0x74
 jr t0
fail:
 j fail
done:
 j done

.section .data
.balign 16
input_a:
.byte 0,0,144,192,0,0,128,192,0,0,96,192,0,0,64,192,0,0,32,192,0,0,0,192,0,0,192,191,0,0,128,191,0,0,0,191,0,0,0,0,0,0,0,63,0,0,128,63,0,0,192,63,0,0,0,64,0,0,32,64,0,0,64,64,0,0,96,64,0,0,128,64,0,0,144,64
.balign 16
input_b:
.byte 0,0,0,191,0,0,128,190,0,0,0,0,0,0,128,62,0,0,0,63,0,0,0,191,0,0,128,190,0,0,0,0,0,0,128,62,0,0,0,63,0,0,0,191,0,0,128,190,0,0,0,0,0,0,128,62,0,0,0,63,0,0,0,191,0,0,128,190,0,0,0,0,0,0,128,62
