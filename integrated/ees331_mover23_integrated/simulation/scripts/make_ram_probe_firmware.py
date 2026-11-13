"""Add a test-only CPU RAM round trip before the unchanged mailbox program."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / "firmware/ees331_cpu/program.mem"
dest = ROOT / "firmware/ees331_cpu/program_ram_probe.mem"
words = [int(w, 16) for w in source.read_text().split()]
assert len(words) == 2048 and words[0] == 0x400000b7
base = 0x700
assert all(w == 0x13 for w in words[base // 4:base // 4 + 7])

def jal(pc: int, target: int) -> int:
    imm = target - pc
    assert imm % 2 == 0 and -(1 << 20) <= imm < 1 << 20
    imm &= (1 << 21) - 1
    return ((imm >> 20) & 1) << 31 | ((imm >> 1) & 0x3ff) << 21 | ((imm >> 11) & 1) << 20 | ((imm >> 12) & 0xff) << 12 | 0x6f

original_first = words[0]
words[0] = jal(0, base)
probe = [
    original_first,        # Preserve LUI x1,0x40000 for the mailbox service.
    0x10000a13,            # addi x20,x0,0x100
    0x12300a93,            # addi x21,x0,0x123
    0x015a2023,            # sw x21,0(x20)
    0x000a2b03,            # lw x22,0(x20)
    0x016a9063,            # bne x21,x22,0: fail by staying here
    jal(base + 24, 4),     # Resume the original instruction at PC=4.
]
words[base // 4:base // 4 + len(probe)] = probe
dest.write_text("".join(f"{word:08x}\n" for word in words))
print(dest)
