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
li s0, 0
loop:
 vsetvli t1, a3, e32, m1, ta, ma
 vle32.v v1, (a0)
 vle32.v v2, (a1)
 vmul.vv v3, v1, v2
 vmv.s.x v4, zero
 vredsum.vs v5, v3, v4
 vmv.x.s t3, v5
 add s0, s0, t3
 slli t2, t1, 2
 add a0, a0, t2
 add a1, a1, t2
 sub a3, a3, t1
 bnez a3, loop
 sw s0, 0(a2)
 addi a2, a2, 4

 # The upstream wrapper ties fencei_flush_ack low, and this controller maps
 # FENCE to FENCE.I. Use the wrapper's scalar-read/vector-store interlock in
 # this uncached testbench; full SoC integration must implement flush ack.
 lw t0, -4(a2)
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
.word -36,-32,-28,-24,-20,-16,-12,-8,-4,0,4,8,12,16,20,24,28,32,36
.balign 16
input_b:
.word 3,2,1,0,-1,-2,-3,3,2,1,0,-1,-2,-3,3,2,1,0,-1
