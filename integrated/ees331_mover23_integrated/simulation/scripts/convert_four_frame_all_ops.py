"""Convert the archived four-image diagnostic graph to EES331 compact format.

The source has 11 graph steps per image and all six operator types. It uses
synthetic weights and small 7x7 inputs, so it is not a full MobileFaceNet run.
"""
from pathlib import Path
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
source = ROOT.parent / "deliverables/self_cnn_four_frames/data"
dest = ROOT / "build/fixtures/four_frame_all_ops"
dest.mkdir(parents=True, exist_ok=True)
manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
assert manifest["task_count"] == 44 and manifest["template_steps"] == 11

def hex_words(name):
    return [int(w, 16) for w in (source / name).read_text().split()]

def write_words(name, values):
    (dest / name).write_text("".join(f"{v:08x}\n" for v in values))

for name in ("memory", "images", "expected"):
    (dest / f"{name}.bin").write_bytes(bytes(hex_words(f"{name}.hex")))
for name in ("commands.hex", "template_commands.hex"):
    shutil.copyfile(source / name, dest / name)

old_meta = hex_words("template_meta.hex")
assert len(old_meta) == 11 * 11
new_meta = []
for step in range(11):
    row = old_meta[step * 11:step * 11 + 11]
    assert row[5] < (1 << 11)
    # The archived stream packs three owner steps in 4-bit nibbles. The
    # compact DDR scheduler expects three separate 8-bit owner fields.
    row[8] = sum(((row[8] >> (4 * u)) & 0xf) << (8 * u) for u in range(3))
    new_meta.extend(row[:6] + [0] * 7 + row[6:])
write_words("template_meta.hex", new_meta)

image_info = hex_words("image_info.hex")
assert len(image_info) == 12
images = []
for frame in range(4):
    address, length, offset = image_info[frame * 3:frame * 3 + 3]
    images.extend([address, length, offset,
                   manifest["slot_base"] + frame * 4 * manifest["slot_pitch"],
                   100 + frame])
write_words("image_info.hex", images)

nodes = []
for job in manifest["jobs"]:
    nodes.extend([job["address"], job["bytes"], job["expected_offset"], job["slot"]])
write_words("node_info.hex", nodes)

info = [4, 11, 44, manifest["memory_bytes"], manifest["memory_bytes"],
        manifest["expected_bytes"], manifest["slot_base"], len(hex_words("images.hex"))]
for slot in range(16):
    info.extend([manifest["slot_base"] + slot * manifest["slot_pitch"],
                 manifest["slot_pitch"]])
info.extend([0] * (88 - len(info)))
assert len(info) == 88
write_words("info.hex", info)
print(dest)
