.option norvc
.option norelax
.section .vectors,"ax"
j fail
.section .text
.global _start
_start:
 li t0,0x6600
 csrs mstatus,t0
 csrw fcsr,zero
 li t0,0xffff0010
 lw a0,0(t0)
 lw a2,4(t0)
 lw a3,8(t0)
 lw a4,12(t0)
 beqz a3,finish
 bnez a4,float_setup
int_loop:
 vsetvli t1,a3,e8,m1,ta,ma
 vle8.v v1,(a0)
 vmslt.vi v0,v1,0
 vsra.vi v4,v1,2
 vmerge.vvm v3,v1,v4,v0
 vse8.v v3,(a2)
 add a0,a0,t1
 add a2,a2,t1
 sub a3,a3,t1
 bnez a3,int_loop
 j finish
float_setup:
 li t0,0x3e800000
 fmv.w.x ft1,t0
float_loop:
 vsetvli t1,a3,e32,m1,ta,ma
 vle32.v v1,(a0)
 # This pinned core needs multiply before comparison in the integrated setup;
 # the reverse order fails a preserved diagnostic, see integration notes.
 vfmul.vf v4,v1,ft1
 vmslt.vi v0,v1,0
 vmerge.vvm v3,v1,v4,v0
 vse32.v v3,(a2)
 slli t2,t1,2
 add a0,a0,t2
 add a2,a2,t2
 sub a3,a3,t1
 bnez a3,float_loop
finish:
 fence
 li t0,0xffff0000
 sw zero,0(t0)
stop:
 j stop
fail:
 li t0,0xffff0000
 li t1,1
 sw t1,0(t0)
 j stop
