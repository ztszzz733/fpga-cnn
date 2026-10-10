0000: lui x1, hi(0x40000000)
0004: addi x1, x1, lo(0x40000000)
0008: lui x2, hi(0x100)
000c: addi x2, x2, lo(0x100)
0010: sw x2, 8(x1)
0014: lui x2, hi(0xa)
0018: addi x2, x2, lo(0xa)
001c: sw x2, 24(x1)
0020: lui x2, hi(0x3d)
0024: addi x2, x2, lo(0x3d)
0028: sw x2, 0(x1)
002c: lw x3, 4(x1)
0030: error
0034: bne x4, x0, error
0038: done
003c: beq x4, x0, poll
0040: lui x3, hi(0x600d)
0044: addi x3, x3, lo(0x600d)
0048: beq x0, x0, finish
004c: lui x3, hi(0xdead)
0050: addi x3, x3, lo(0xdead)
0054: lui x2, hi(0x80)
0058: addi x2, x2, lo(0x80)
005c: sw x3, 0(x2)
0060: beq x0, x0, halt
