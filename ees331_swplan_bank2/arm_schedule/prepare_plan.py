"""Prepare two 112x112 RGB jobs for the board's DW7-disabled CNN."""

import argparse
from planned_schema import plan_k3
import hashlib
import json
from pathlib import Path
import struct
import zlib

import numpy as np


def digest(data):
    return hashlib.sha256(data).hexdigest()


def words(path):
    return [int(value, 16) for value in path.read_text().split()]


def write_words(path, values):
    path.write_text("".join(f"{value:08x}\n" for value in values), encoding="ascii")


def tail_reference(samples, command, memory, parameters):
    weights = np.frombuffer(memory, dtype=np.int8, offset=command[2], count=512 * 128)
    pixels = np.frombuffer(samples, dtype=np.uint8).reshape(49, 512)
    # Use wide integer accumulation for the reference, independent of the RTL.
    raw = pixels.astype(np.int64) @ weights.reshape(128, 512).T.astype(np.int64)
    if raw.min() < -(1 << 31) or raw.max() >= 1 << 31:
        raise ValueError("Tail convolution exceeds INT32")
    quantized = []
    for i, value in enumerate(raw.flat):
        bias, mult, _, config, clamp = struct.unpack_from("<iiiII", memory, parameters + 20 * (i % 128))
        product = (int(value) + bias) * mult
        shift = config & 63
        rounded = (abs(product) + ((1 << (shift - 1)) if shift else 0)) >> shift
        if product < 0:
            rounded = -rounded
        q = rounded + (config >> 24)
        quantized.append(max(clamp & 255, min((clamp >> 8) & 255, q)))
    return raw.astype("<i4").tobytes(), bytes(quantized)


def prepare(source, out):
    manifest_bytes = (source / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest["input_shape"] != [112, 112, 3] or manifest["template_steps"] != 131:
        raise ValueError("Expected the archived 131-step 112x112 MobileFaceNet fixture")
    for name, expected_hash in manifest["files_sha256"].items():
        if digest((source / name).read_bytes()) != expected_hash:
            raise ValueError(f"Source fixture hash mismatch: {name}")
    old_commands = words(source / "template_commands.hex")
    old_meta = words(source / "template_meta.hex")
    image_info = words(source / "image_info.hex")
    memory = (source / "memory.bin").read_bytes()
    old_gold = (source / "expected.bin").read_bytes()
    old_images = (source / "images.bin").read_bytes()
    page_bytes = 1024
    def align_page(size):
        return (size + page_bytes - 1) & ~(page_bytes - 1)

    model = memory[:image_info[0]].ljust(align_page(image_info[0]), b"\0")
    next_base = len(model)
    images, frames, tails = [], [], []
    old_jobs = {(job["local_step"], job["frame"]): job for job in manifest["jobs"]}

    def golden(step, frame_id):
        job = old_jobs[step, frame_id]
        start = job["expected_offset"]
        return old_gold[start:start + job["bytes"]]

    for f in range(2):
        _, length, offset, _, frame_id = image_info[f * 5:f * 5 + 5]
        image = old_images[offset:offset + length]
        if len(image) != 112 * 112 * 3 or digest(image) != manifest["input_sources"][f]["quantized_sha256"]:
            raise ValueError(f"Invalid image payload {f}")
        images.append(image)
        input_addr = next_base
        work = input_addr + align_page(length)
        work_bytes = align_page(manifest["workspace_bytes"])
        next_base = work + work_bytes
        frames.append([frame_id, input_addr, length, work, work_bytes, zlib.crc32(image)])
        tails.append(tail_reference(golden(126, frame_id), old_commands[129 * 16:130 * 16],
                                    memory, old_commands[130 * 16 + 4]))
    if next_base > 0x01000000:
        raise ValueError("DDR plan exceeds the shared window")
    if images[0] == images[1]:
        raise ValueError("Expected two distinct images")

    kept = [i for i in range(131) if i not in (127, 128)]
    remap = {old: new for new, old in enumerate(kept)}
    remap[128] = remap[126]
    uses = []
    consumers = [set() for _ in kept]
    for new, old in enumerate(kept):
        meta = old_meta[old * 18:old * 18 + 18]
        owners = [remap[(meta[15] >> (8 * k)) & 255] for k in range(3) if (meta[13] >> k) & 1]
        for owner in owners:
            consumers[owner].add(new)
        owner_bits = sum(remap[(meta[15] >> (8 * k)) & 255] << (8 * k)
                         for k in range(3) if (meta[13] >> k) & 1)
        uses.append((owners, owner_bits))

    rows, node_info = [], []
    expected = bytearray()
    for new, old in enumerate(kept):
        command = old_commands[old * 16:old * 16 + 16].copy()
        meta = old_meta[old * 18:old * 18 + 18]
        owners, owner_bits = uses[new]
        deps = sorted(set((([new - 1] if new else []) + owners)))
        ends = sorted(consumers[new])
        if len(deps) > 2 or len(ends) > 2 or command[0] == 3:
            raise ValueError(f"Unsupported template step {old}")
        d0, d1 = (deps + [0, 0])[:2]
        e0, e1 = (ends + [0, 0])[:2]
        if old in (129, 130):
            command[7] = command[8] = 7
        final = old == 130
        if final:
            command[5] = 6272
        command = plan_k3(command)
        rows.extend(command + [
            meta[0] | meta[4] << 4 | meta[13] << 6 | meta[14] << 9 |
            int(final) << 15 | ((1 << len(deps)) - 1) << 16 | d0 << 18,
            d1 | owner_bits << 8,
            e0 | e1 << 8 | len(ends) << 16,
            6272 if final else 0,
        ])
        for f, (frame_id, _, _, work, work_bytes, _) in enumerate(frames):
            blob = tails[f][old - 129] if old >= 129 else golden(old, frame_id)
            if not blob or command[3] + len(blob) > work_bytes:
                raise ValueError(f"Output outside workspace at step {old}")
            node_info.extend([work + command[3], len(blob), len(expected)])
            expected.extend(blob)

    # All K3, K1, Post, Add and Pad instances in the current board configuration.
    header = [0x31435345, len(frames), len(kept), 0x3FF, len(model), zlib.crc32(model),
              rows[-17], 6272]
    descriptor = header + [word for frame in frames for word in frame] + rows
    out.mkdir(parents=True, exist_ok=True)
    (out / "PLAN.BIN").write_bytes(struct.pack(f"<{len(descriptor)}I", *descriptor) + model + b"".join(images))
    (out / "expected_intermediate.bin").write_bytes(expected)
    (out / "expected_results.bin").write_bytes(b"".join(tail[1] for tail in tails))
    write_words(out / "nodes.hex", node_info)
    guards = [word for frame in frames for slot in manifest["slots"]
              for word in (frame[3] + slot["offset"] + slot["size"] - 64,)]
    write_words(out / "guards.hex", guards)
    details = {
        "fixture_manifest_sha256": digest(manifest_bytes), "input_shape": [112, 112, 3],
        "input_sha256": [digest(image) for image in images], "frames": [frame[0] for frame in frames],
        "steps": len(kept), "jobs": 2 * len(kept), "result_shape": [7, 7, 128],
        "ddr": {"model_bytes": len(model), "frame_partitions": [
            {"frame": f[0], "input": f[1], "input_bytes": f[2], "workspace": f[3], "workspace_bytes": f[4]}
            for f in frames]},
        "oracle_bytes": len(expected), "expected_results_sha256": digest(b"".join(tail[1] for tail in tails)),
        "model_variant": "DW7 and its following Post bypassed; final K1 and Post run over 7x7",
        "bank_count": 2, "cache_bytes": 401408, "k1_units": 4, "unit_mask": "0x3ff",
        "k3_plan_version": 1, "plan_sha256": digest((out / "PLAN.BIN").read_bytes()),
    }
    (out / "fixture_manifest.json").write_text(json.dumps(details, indent=2) + "\n")
    print(json.dumps(details, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    prepare(args.source, args.output)
