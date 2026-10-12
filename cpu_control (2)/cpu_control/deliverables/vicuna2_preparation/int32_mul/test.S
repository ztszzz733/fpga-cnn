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
 vmul.vv v3, v1, v2
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
.byte 220,255,255,255,224,255,255,255,228,255,255,255,232,255,255,255,236,255,255,255,240,255,255,255,244,255,255,255,248,255,255,255,252,255,255,255,0,0,0,0,4,0,0,0,8,0,0,0,12,0,0,0,16,0,0,0,20,0,0,0,24,0,0,0,28,0,0,0,32,0,0,0,36,0,0,0
.balign 16
input_b:
.byte 3,0,0,0,2,0,0,0,1,0,0,0,0,0,0,0,255,255,255,255,254,255,255,255,253,255,255,255,3,0,0,0,2,0,0,0,1,0,0,0,0,0,0,0,255,255,255,255,254,255,255,255,253,255,255,255,3,0,0,0,2,0,0,0,1,0,0,0,0,0,0,0,255,255,255,255
