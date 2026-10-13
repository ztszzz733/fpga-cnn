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
 vsetvli t1, a3, e16, m1, ta, ma
 vle16.v v1, (a0)
 vle16.v v2, (a1)
 vfmul.vv v3, v1, v2
 vse16.v v3, (a2)
 slli t2, t1, 1
 add a0, a0, t2
 add a1, a1, t2
 add a2, a2, t2
 sub a3, a3, t1
 bnez a3, loop

 # The upstream wrapper ties fencei_flush_ack low, and this controller maps
 # FENCE to FENCE.I. Use the wrapper's scalar-read/vector-store interlock in
 # this uncached testbench; full SoC integration must implement flush ack.
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
.byte 128,196,0,196,0,195,0,194,0,193,0,192,0,190,0,188,0,184,0,0,0,56,0,60,0,62,0,64,0,65,0,66,0,67,0,68,128,68
.balign 16
input_b:
.byte 0,184,0,180,0,0,0,52,0,56,0,184,0,180,0,0,0,52,0,56,0,184,0,180,0,0,0,52,0,56,0,184,0,180,0,0,0,52
