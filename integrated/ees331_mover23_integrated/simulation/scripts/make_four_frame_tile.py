"""Replicate the provided 8x8x32 tile across four independent DDR workspaces.

All four images use the same diagnostic fixture input; their workspaces and
expected-output spans are separate. This is a concurrency test, not four
different recognition images or a full network fixture.
"""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / "build/fixtures/tile_8x8x32"
dest = ROOT / "build/fixtures/tile_8x8x32_four_frames"
dest.mkdir(parents=True, exist_ok=True)

def read_words(name):
    return [int(w, 16) for w in (source / name).read_text().split()]

def write_words(name, words):
    (dest / name).write_text("".join(f"{w:08x}\n" for w in words))

frame_bytes = 32768
frames = 4
initial = (source / "memory.bin").read_bytes()
images = (source / "images.bin").read_bytes()
gold = (source / "expected.bin").read_bytes()
info = read_words("info.hex")
image = read_words("image_info.hex")
nodes = read_words("node_info.hex")
assert len(initial) == frame_bytes and len(images) == image[1] == 3200
assert info[:8] == [1, 3, 3, frame_bytes, frame_bytes, len(gold), 15744, len(images)]
assert len(info) == 88 and len(nodes) == 12
assert all(initial[info[8 + s * 2] + info[9 + s * 2] - 64:info[8 + s * 2] + info[9 + s * 2]] == b"\xa5" * 64 for s in range(16))

# The initial DDR image contains immutable weights and guard bytes. CNN input
# pixels are uploaded only after the run starts, as in the one-frame fixture.
(dest / "memory.bin").write_bytes(initial * frames)
(dest / "images.bin").write_bytes(images * frames)
expected = bytearray()
node_table = []
for step in range(3):
    address, size, offset, slot = nodes[step * 4:step * 4 + 4]
    for frame in range(frames):
        node_table.extend([address + frame * frame_bytes, size, len(expected), slot + frame * 4])
        expected.extend(gold[offset:offset + size])
(dest / "expected.bin").write_bytes(expected)
write_words("node_info.hex", node_table)

image_table = []
for frame in range(frames):
    image_table.extend([frame * frame_bytes, len(images), frame * len(images),
                        frame * frame_bytes, image[4] + frame])
write_words("image_info.hex", image_table)

info[0], info[2], info[3], info[4] = frames, frames * 3, frame_bytes * frames, frame_bytes * frames
info[5], info[7] = len(expected), len(images) * frames
for frame in range(frames):
    for slot in range(4):
        original_slot = slot if frame == 0 else slot
        info[8 + (frame * 4 + slot) * 2] = info[8 + original_slot * 2] + frame * frame_bytes
        info[9 + (frame * 4 + slot) * 2] = info[9 + original_slot * 2]
write_words("info.hex", info)
for name in ("commands.hex", "template_commands.hex", "template_meta.hex"):
    shutil.copyfile(source / name, dest / name)
print(dest)
