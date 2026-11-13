"""Build fixed RV32I firmware and a 256-byte external-memory CNN demo image."""
from pathlib import Path
import json
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]


class Program:
    def __init__(self):
        self.code = []
        self.labels = {}
        self.fixups = []

    def emit(self, word, comment):
        self.code.append((word & 0xffffffff, comment))

    def label(self, name):
        self.labels[name] = 4 * len(self.code)

    def li(self, rd, value):
        self.emit(((value + 0x800) & 0xfffff000) | rd << 7 | 0x37, f"lui x{rd}, hi({value:#x})")
        self.i(0, rd, rd, value & 0xfff, f"addi x{rd}, x{rd}, lo({value:#x})")

    def i(self, funct3, rd, rs, imm, comment, op=0x13):
        self.emit((imm & 0xfff) << 20 | rs << 15 | funct3 << 12 | rd << 7 | op, comment)

    def lw(self, rd, rs, offset=0):
        self.i(2, rd, rs, offset, f"lw x{rd}, {offset}(x{rs})", 0x03)

    def sw(self, rs, rt, offset=0, width=2):
        imm = offset & 0xfff
        self.emit((imm >> 5) << 25 | rt << 20 | rs << 15 | width << 12 | (imm & 31) << 7 | 0x23,
                  f"{'sw' if width == 2 else 'sb' if width == 0 else 'sh'} x{rt}, {offset}(x{rs})")

    def branch(self, f, rs, rt, target):
        self.fixups.append((len(self.code), f, rs, rt, target))
        self.emit(0, f"{'beq' if f == 0 else 'bne'} x{rs}, x{rt}, {target}")

    def jump(self, target):
        self.branch(0, 0, 0, target)

    def resolve(self):
        for idx, f, rs, rt, target in self.fixups:
            off = self.labels[target] - 4 * idx
            assert -4096 <= off <= 4094 and off % 2 == 0
            word = ((off >> 12) & 1) << 31 | ((off >> 5) & 63) << 25 | rt << 20 | rs << 15
            word |= f << 12 | ((off >> 1) & 15) << 8 | ((off >> 11) & 1) << 7 | 0x63
            self.code[idx] = (word, self.code[idx][1])


def generate():
    data = bytearray([0xa5] * 256)
    data[:4] = bytes([1, 254, 3, 4])
    struct.pack_into('<i', data, 0x10, 2)
    struct.pack_into('<i', data, 0x20, 3)
    # Version 1, conv opcode 0; 2x2 spatial, one input and output channel.
    struct.pack_into('<8I', data, 0xe0, 0x100, 0x100, 0x141, 0x110, 0x120, 0x20002, 0x10001, 0x11)
    assert zlib.crc32(data) == 0xfe679cc9
    p = Program()
    p.li(1, 0x40000000)  # CNN MMIO
    p.li(2, 0x40)        # CPU-local request + status
    p.li(3, 0x80)        # result / finish mailbox
    p.sw(3, 0); p.sw(3, 0, 4); p.sw(3, 0, 8)
    p.li(4, 1); p.sw(2, 4)
    p.sw(2, 0)          # premature clear is ignored while load is outstanding
    p.sw(2, 4)          # repeated request must not start another batch
    p.li(6, 200000)
    p.label('wait_load')
    p.lw(4, 2, 4)
    p.i(7, 5, 4, 1, 'andi x5, x4, 1')
    p.branch(1, 5, 0, 'load_finished')
    p.i(0, 6, 6, -1, 'addi x6, x6, -1')
    p.branch(1, 6, 0, 'wait_load')
    p.jump('timeout')
    p.label('load_finished')
    p.i(7, 7, 4, 2, 'andi x7, x4, 2 # save load error before acknowledgement')
    p.sw(2, 0, width=0); p.sw(2, 0, width=1)  # partial local writes ignored
    p.lw(8, 2); p.li(9, 1)
    p.branch(1, 8, 9, 'result_error')
    for _ in range(8): p.i(0, 0, 0, 0, 'nop # exercise held completion')
    p.sw(2, 0)          # full-word ack
    p.li(6, 20000)
    p.label('wait_ack')
    p.lw(4, 2, 4)
    p.branch(0, 4, 0, 'acknowledged')
    p.i(0, 6, 6, -1, 'addi x6, x6, -1')
    p.branch(1, 6, 0, 'wait_ack')
    p.jump('timeout')
    p.label('acknowledged')
    p.branch(1, 7, 0, 'load_error')
    p.li(4, 0x1e0); p.sw(1, 4, 8)
    p.li(4, 1); p.sw(1, 4, 24)
    p.li(4, 0x3d); p.sw(1, 4)
    p.li(6, 20000)
    p.label('wait_cnn')
    p.lw(4, 1, 4)
    p.i(7, 5, 4, 4, 'andi x5, x4, 4 # CNN ERROR')
    p.branch(1, 5, 0, 'cnn_error')
    p.i(7, 5, 4, 2, 'andi x5, x4, 2 # CNN DONE')
    p.branch(1, 5, 0, 'cnn_finished')
    p.i(0, 6, 6, -1, 'addi x6, x6, -1')
    p.branch(1, 6, 0, 'wait_cnn')
    p.jump('timeout')
    p.label('cnn_finished')
    p.li(2, 0x140); p.lw(4, 2); p.lw(5, 2, 4)
    p.sw(3, 4); p.sw(3, 5, 4)
    p.li(8, 0x09ff05a5); p.branch(1, 4, 8, 'result_error')
    p.li(8, 0xa5a5a50b); p.branch(1, 5, 8, 'result_error')
    p.li(4, 0x600d); p.sw(3, 4, 8); p.jump('halt')
    for name, code in [('load_error', 1), ('cnn_error', 2), ('timeout', 3), ('result_error', 4)]:
        p.label(name); p.li(4, 0xdead0000 | code); p.sw(3, 4, 8); p.jump('halt')
    p.label('halt'); p.emit(0x0000006f, 'jal x0, 0')
    p.resolve()
    out = ROOT / 'firmware/autoload_demo'
    out.mkdir(parents=True, exist_ok=True)
    words = [word for word, _ in p.code]
    assert len(words) <= 1024
    (out/'program.mem').write_text(''.join(f'{w:08x}\n' for w in words + [0x13]*(1024-len(words))), encoding='ascii')
    labels = {addr: name for name, addr in p.labels.items()}
    listing = ['# Generated RV32I listing: byte address, machine word, instruction; not C runtime.']
    for i, (w, text) in enumerate(p.code):
        if i*4 in labels: listing.append(labels[i*4]+':')
        listing.append(f'{i*4:04x}  {w:08x}  {text}')
    (out/'program.lst').write_text('\n'.join(listing)+'\n', encoding='utf-8')
    (out/'external.bin').write_bytes(data)
    (out/'external_bytes.mem').write_text(''.join(f'{b:02x}\n' for b in data), encoding='ascii')
    metadata = {'input_signed_int8': [1, -2, 3, 4], 'weight': 2, 'bias': 3,
                'expected_signed_int8': [5, -1, 9, 11], 'batch_crc32': 'fe679cc9',
                'sram_load_base': '0x100', 'load_bytes': 256, 'descriptor': '0x1e0',
                'output_bytes': '0x141..0x144', 'cpu_local_control': '0x40', 'cpu_local_status': '0x44',
                'result_words': ['0x09ff05a5', '0xa5a5a50b'], 'finish_mailbox': '0x88',
                'instruction_count': len(p.code), 'rom_words': 1024}
    (out/'manifest.json').write_text(json.dumps(metadata, indent=2)+'\n', encoding='utf-8')
    print(f'Generated {out}; instructions={len(p.code)}, CRC32=fe679cc9')
    return out


if __name__ == '__main__':
    generate()
