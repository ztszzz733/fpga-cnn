"""Compile MobileFaceNet into the address-driven, NEureka-free CNN interface.

The floating model supplies diagnostic scales from image zero only. All frames
then use the same quantized weights/scales; independent NumPy INT64 operations
produce checker data. Execution SRAM contains weights, parameters, and poison:
neither intermediate golden values nor input pixels are preloaded into it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".tools/mobilefacenet-python"))
MAX_TASKS, IW, STEPS, LW = 1024, 10, 256, 8
POISON, ALIGN, GUARD = 0xA5, 64, 64


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def align(n: int, boundary: int = ALIGN) -> int:
    return (n + boundary - 1) // boundary * boundary


def hex_words(path: Path, values) -> None:
    path.write_text("".join(f"{int(v) & 0xffffffff:08x}\n" for v in values), encoding="ascii")


def rounded(v, shift=24):
    import numpy as np
    return np.sign(v) * ((np.abs(v) + (0 if shift == 0 else 1 << (shift - 1))) >> shift)


def generate(model_path: Path, out: Path, frames: int = 4, small: bool = False, images=None):
    import numpy as np
    import onnx
    import onnxruntime as ort
    from onnx import numpy_helper
    from PIL import Image

    began = time.perf_counter()
    model_path, out = Path(model_path).resolve(), Path(out).resolve()
    assert 1 <= frames <= 4, "one to four finite frame contexts are supported"
    assert model_path.is_file(), f"missing ONNX: {model_path}"
    assert not out.exists() or not any(out.iterdir()), "preserve existing generated data; select an empty output directory"
    out.mkdir(parents=True, exist_ok=True)
    model = onnx.load(model_path)
    onnx.checker.check_model(model)
    weights = {t.name: numpy_helper.to_array(t) for t in model.graph.initializer}
    constants = dict(weights)
    for node in model.graph.node:
        if node.op_type == "Constant":
            attrs = {a.name: onnx.helper.get_attribute_value(a) for a in node.attribute}
            if "value" in attrs:
                constants[node.output[0]] = numpy_helper.to_array(attrs["value"])
    nodes = list(model.graph.node)
    users = {}
    for n in nodes:
        for name in n.input:
            users.setdefault(name, []).append(n)
    selected = [n for n in nodes if n.op_type in ("Conv", "Add")]
    assert len(selected) == 63, f"expected 63 Conv/Add layers, found {len(selected)}"
    if small:
        selected = selected[:3]
        assert all(n.op_type == "Conv" for n in selected)
    fused = {}
    for n in selected:
        cs = users.get(n.output[0], [])
        fused[n.name] = cs[0] if len(cs) == 1 and cs[0].op_type in ("Relu", "Clip") else None
    output_names = [(fused[n.name] or n).output[0] for n in selected]
    assert len(set(output_names)) == len(output_names)
    input_name = model.graph.input[0].name

    # The small gate retains pretrained channels/weights and the first three
    # operators, but substitutes an 8x8 spatial ROI, with actual zero padding.
    side = 8 if small else 112
    rgb_images = []
    input_sources = []
    image_paths = [Path(p).resolve() for p in images] if images else [model_path.parent / "images" / f"test_{f}.png" for f in range(frames)]
    assert len(image_paths) == frames
    model_provenance_path = model_path.parent / "manifest.json"
    model_provenance = json.loads(model_provenance_path.read_text(encoding="utf-8")) if model_provenance_path.exists() else None
    for f in range(frames):
        source = image_paths[f]
        assert source.is_file(), f"missing input image: {source}; provide --images or restore model images"
        rgb = np.asarray(Image.open(source).convert("RGB"), dtype=np.uint8)
        assert rgb.shape == (112, 112, 3), (source, rgb.shape)
        ppm = b"P6\n112 112\n255\n" + rgb.tobytes()
        (out / f"image{f}.ppm").write_bytes(ppm)
        input_sources.append(dict(frame=100 + f, kind="provided_RGB_numerical_test_input",
            path=str(source), source_sha256=sha(source.read_bytes()),
            shape=[112, 112, 3], ppm_sha256=sha(ppm), rgb_sha256=sha(rgb.tobytes()),
            execution_roi=[0, 0, side, side], face_accuracy_claim=False))
        rgb_images.append(rgb[:side, :side])
    assert len({s["rgb_sha256"] for s in input_sources}) == frames
    norm = [((x.astype(np.float32) / 255 - np.array([.485, .456, .406])) /
             np.array([.229, .224, .225])).astype(np.float32) for x in rgb_images]

    float_model = onnx.ModelProto()
    float_model.CopyFrom(model)
    if small:
        last_name = (fused[selected[-1].name] or selected[-1]).output[0]
        end = next(i for i, n in enumerate(nodes) if last_name in n.output)
        del float_model.graph.node[end + 1:]
        dims = float_model.graph.input[0].type.tensor_type.shape.dim
        dims[2].dim_value = side
        dims[3].dim_value = side
    del float_model.graph.output[:]
    del float_model.graph.value_info[:]
    for name in output_names:
        float_model.graph.output.append(onnx.helper.make_tensor_value_info(name, onnx.TensorProto.FLOAT, None))
    float_model = onnx.shape_inference.infer_shapes(float_model)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.log_severity_level = 3
    reference = ort.InferenceSession(float_model.SerializeToString(), options, providers=["CPUExecutionProvider"])
    float_values = dict(zip(output_names, reference.run(None, {input_name: norm[0].transpose(2, 0, 1)[None]})))

    ro = []
    ro_cursor = 4096
    def readonly(data: bytes, name: str) -> int:
        nonlocal ro_cursor
        base = align(ro_cursor)
        ro_cursor = base + len(data) + GUARD
        ro.append(dict(name=name, address=base, bytes=len(data), sha256=sha(data), data=data))
        return base

    def parameter_blob(bias, ma, mb, za, zb, zo):
        assert all(-(1 << 31) <= int(x) < (1 << 31) for x in bias)
        assert all(0 <= int(x) < (1 << 31) for x in list(ma) + list(mb))
        return b"".join(struct.pack("<5I", int(b) & 0xffffffff, int(a), int(c),
            24 | (int(za) << 8) | (int(zb) << 16) | (int(zo) << 24), 255 << 8)
            for b, a, c in zip(bias, ma, mb))

    input_scale, input_zero = 3 / 127, 128
    inputs = [np.clip(np.rint(x / input_scale) + input_zero, 0, 255).astype(np.uint8) for x in norm]
    tensors = {input_name: dict(arrays=inputs, shape=list(inputs[0].shape), producer=None,
                                scale=input_scale, zero=input_zero)}
    jobs, layer_reports = [], []
    def step(name, opcode, sources, arrays, layer, **extra):
        assert name not in tensors, name
        shape = list(arrays[0].shape)
        assert all(list(a.shape) == shape for a in arrays)
        raw = opcode in (0, 3, 5)
        payloads = [a.astype("<i4" if raw else "u1").tobytes() for a in arrays]
        tensors[name] = dict(arrays=arrays, payloads=payloads, shape=shape, producer=len(jobs), **extra)
        jobs.append(dict(index=len(jobs), name=name, opcode=opcode, sources=sources,
                         output=name, layer=layer, **extra))
        return tensors[name]

    total_macs = 0
    for li, node in enumerate(selected):
        act = fused[node.name]
        out_name = (act or node).output[0]
        target = float_values[out_name][0].transpose(1, 2, 0).astype(np.float64)
        relu = act is not None
        if act is not None and act.op_type == "Clip":
            aa = {a.name: onnx.helper.get_attribute_value(a) for a in act.attribute}
            lo = aa.get("min", float(np.asarray(constants[act.input[1]])) if len(act.input) > 1 and act.input[1] else 0.)
            hi = aa.get("max", float(np.asarray(constants[act.input[2]])) if len(act.input) > 2 and act.input[2] else 6.)
            assert float(lo) == 0. and np.isfinite(hi) and hi > 0, "unsupported Clip limits"
            sy = float(hi) / 255
        else:
            sy = max(float(target.max() if relu else np.abs(target).max()) / (240 if relu else 110), 1e-7)
        zy = 0 if relu else 128
        src_name = node.input[0]
        src = tensors[src_name]
        sx, zx = src["scale"], src["zero"]
        first = len(jobs)
        layer_macs = 0
        extra = {}
        if node.op_type == "Add":
            other = tensors[node.input[1]]
            assert other["shape"] == src["shape"]
            co = src["shape"][2]
            ma = np.full(co, round(sx / sy * (1 << 24)), np.int64)
            mb = np.full(co, round(other["scale"] / sy * (1 << 24)), np.int64)
            pp = readonly(parameter_blob(np.zeros(co, np.int64), ma, mb, zx, other["zero"], zy), f"layer{li}_parameters")
            q = [np.clip(rounded((a.astype(np.int64) - zx) * ma +
                    (b.astype(np.int64) - other["zero"]) * mb) + zy, 0, 255).astype(np.uint8)
                 for a, b in zip(src["arrays"], other["arrays"])]
            result = step(out_name, 2, list(node.input[:2]), q, li, parameter_address=pp, scale=sy, zero=zy)
        else:
            attrs = {a.name: onnx.helper.get_attribute_value(a) for a in node.attribute}
            w = weights[node.input[1]].astype(np.float64)
            bias = weights[node.input[2]].astype(np.float64) if len(node.input) > 2 else np.zeros(w.shape[0])
            co, wi, ky, kx = w.shape
            ci = src["shape"][2]
            group = attrs.get("group", 1)
            dw = group == ci and ci > 1
            stride = attrs.get("strides", [1, 1])[0]
            assert 0 < ci <= 512 and 0 < co <= 512 and ky == kx and ky in (1, 3, 7)
            assert attrs.get("dilations", [1, 1]) == [1, 1] and attrs.get("strides", [1, 1]) == [stride, stride]
            assert stride in (1, 2) and ((dw and wi == 1 and ci == co) or (not dw and group == 1 and wi == ci))
            pads = attrs.get("pads", [0, 0, 0, 0])
            assert pads in ([0, 0, 0, 0], [1, 1, 1, 1])
            if pads[0]:
                padded = [np.pad(x, ((1, 1), (1, 1), (0, 0)), constant_values=zx) for x in src["arrays"]]
                pad_name = f"__layer{li}_padding"
                src = step(pad_name, 4, [src_name], padded, li, scale=sx, zero=zx, fill=zx)
                src_name = pad_name
            sw = np.maximum(np.abs(w).max((1, 2, 3)) / 127, 1e-15)
            qw = np.clip(np.rint(w / sw[:, None, None, None]), -127, 127).astype(np.int64)
            if ky == 7:
                assert dw and stride == 1 and src["shape"] == [7, 7, 512]
                packed = qw[:, 0].transpose(1, 2, 0).astype("i1")
                layout = "KY_KX_C"
            elif dw:
                packed, layout = qw[:, 0].astype("i1"), "C_KY_KX"
            else:
                packed, layout = qw.transpose(0, 2, 3, 1).astype("i1"), "O_KY_KX_I"
            wa = readonly(packed.tobytes(), f"layer{li}_weights_{layout}")
            raw = []
            for x in src["arrays"]:
                patches = np.lib.stride_tricks.sliding_window_view(x, (ky, ky), axis=(0, 1))[::stride, ::stride].astype(np.int64)
                oh, ow = patches.shape[:2]
                acc = (patches * qw[:, 0]).sum((3, 4)) if dw else (patches.reshape(oh * ow, -1) @ qw.reshape(co, -1).T).reshape(oh, ow, co)
                assert -(1 << 31) <= int(acc.min()) and int(acc.max()) < (1 << 31)
                # Check exported byte order with a separate scalar dot product.
                # The main oracle above consumes original OIHW weights instead.
                packed_bytes = packed.tobytes()
                for y, xx, oc in ((0, 0, 0), (oh // 2, ow // 2, co // 2), (oh - 1, ow - 1, co - 1)):
                    scalar = 0
                    for dy in range(ky):
                        for dx in range(ky):
                            for channel in ([oc] if dw else range(ci)):
                                index = ((dy * ky + dx) * co + oc) if ky == 7 else ((oc * ky + dy) * ky + dx)
                                if not dw:
                                    index = index * ci + channel
                                wb = packed_bytes[index]
                                scalar += int(x[y * stride + dy, xx * stride + dx, channel]) * (wb if wb < 128 else wb - 256)
                    assert scalar == int(acc[y, xx, oc]), ("weight layout oracle mismatch", li, y, xx, oc)
                raw.append(acc)
            qb = np.rint(bias / (sx * sw)).astype(np.int64) - zx * qw.sum((1, 2, 3))
            ma = np.rint(sx * sw / sy * (1 << 24)).astype(np.int64)
            pp = readonly(parameter_blob(qb, ma, np.zeros(co, np.int64), 0, 0, zy), f"layer{li}_parameters")
            # Prove the oracle's INT64 multiply cannot wrap (RTL uses INT96).
            bound = max(max(abs(int(a.min())), abs(int(a.max()))) for a in raw) + max(abs(int(b)) for b in qb)
            assert bound * max(int(m) for m in ma) + (1 << 23) < (1 << 63)
            q = [np.clip(rounded((a + qb) * ma) + zy, 0, 255).astype(np.uint8) for a in raw]
            layer_macs = int(raw[0].size * (ky * ky if dw else ci * ky * ky))
            total_macs += layer_macs
            raw_name = f"__layer{li}_raw"
            step(raw_name, 3 if ky == 7 else (5 if ky == 1 else 0), [src_name], raw, li,
                 weight_address=wa, kernel=ky, stride=stride, depthwise=dw, macs=layer_macs)
            result = step(out_name, 1, [raw_name], q, li, parameter_address=pp, scale=sy, zero=zy)
            extra = dict(kernel=ky, stride=stride, depthwise=dw, weight_layout=layout,
                         weight_address=wa, weight_bytes=packed.nbytes, raw_min=min(int(a.min()) for a in raw),
                         raw_max=max(int(a.max()) for a in raw))
        assert result["shape"] == list(target.shape), (node.name, result["shape"], target.shape)
        layer_reports.append(dict(index=li, name=node.name, operation=node.op_type,
            activation=act.op_type if act else None, shape=result["shape"], first_step=first,
            end_step=len(jobs), scale=sy, zero=zy, macs=layer_macs,
            first_image_diagnostic_rmse=float(np.sqrt(np.mean(((q[0].astype(np.float64) - zy) * sy - target) ** 2))), **extra))
        print(f"layer {li:02d} {node.op_type} {result['shape']} steps={len(jobs)} MAC={layer_macs}", flush=True)
    steps = len(jobs)
    assert steps <= STEPS and steps * frames <= MAX_TASKS
    if not small:
        assert steps == 131 and total_macs == 233810432 and len(jobs) == 131
        assert tensors[jobs[-1]["output"]]["shape"] == [1, 1, 128]

    # Lifetimes include all residual readers. Within each image the template
    # retains sequential dependencies, so a last-use schedule has exact meaning.
    consumers = {name: [] for name in tensors}
    for j in jobs:
        for name in j["sources"]:
            consumers[name].append(j["index"])
    slots = [dict(last=-1, payload_bytes=0) for _ in range(4)]
    for j in jobs:
        t = tensors[j["output"]]
        first = j["index"]
        last = max([first] + consumers[j["output"]])
        n = len(t["payloads"][0])
        choices = [s for s in range(4) if slots[s]["last"] < first]
        assert choices, ("more than four simultaneous buffers", first)
        s = min(choices, key=lambda a: (max(slots[a]["payload_bytes"], n) - slots[a]["payload_bytes"], -slots[a]["payload_bytes"], a))
        slots[s]["last"], slots[s]["payload_bytes"] = last, max(slots[s]["payload_bytes"], n)
        t.update(slot=s, first=first, last=last, bytes=n)
    slot_cursor = 0
    for slot in slots:
        slot["offset"] = slot_cursor
        slot["size"] = align(slot["payload_bytes"]) + GUARD
        slot_cursor += slot["size"]
    for j in jobs:
        t = tensors[j["output"]]
        t["offset"] = slots[t["slot"]]["offset"]
        for p in jobs[:j["index"]]:
            a = tensors[p["output"]]
            assert a["slot"] != t["slot"] or a["last"] < t["first"]
    for j in jobs:
        out_t = tensors[j["output"]]
        for name in j["sources"]:
            t = tensors[name]
            if t["producer"] is not None:
                assert t["slot"] != out_t["slot"], ("in-place slot alias", j["index"])

    image_addresses = []
    for f in range(frames):
        base = align(ro_cursor)
        image_addresses.append(base)
        ro_cursor = base + inputs[f].nbytes + GUARD
    readonly_end = align(ro_cursor, 4096)
    # Reserve all four physical workspaces even in a one-image diagnostic run.
    workspace_bases = [readonly_end + f * slot_cursor for f in range(4)]
    init_bytes = workspace_bases[-1] + slot_cursor
    sram_size = 262144 if small else 16 * 1024 * 1024
    assert init_bytes <= sram_size, ("SRAM parameter too small", init_bytes, sram_size)
    memory = bytearray([POISON]) * init_bytes
    for r in ro:
        memory[r["address"]:r["address"] + r["bytes"]] = r["data"]
    image_payload = b"".join(a.tobytes() for a in inputs)
    image_info = []
    image_offset = 0
    for f, data in enumerate(inputs):
        image_info.extend([image_addresses[f], data.nbytes, image_offset, workspace_bases[f], 100 + f])
        input_sources[f]["quantized_sha256"] = sha(data.tobytes())
        input_sources[f]["quantized_shape"] = list(data.shape)
        image_offset += data.nbytes

    templates, metas, commands, node_info = [], [], [], []
    expected = bytearray()
    job_reports = []
    for j in jobs:
        local = j["index"]
        t = tensors[j["output"]]
        src = tensors[j["sources"][0]]
        source_mode = 1 if src["producer"] is None else 2
        cmd = [0] * 16
        cmd[0], cmd[1], cmd[3] = j["opcode"], (0 if src["producer"] is None else src["offset"]), t["offset"]
        cmd[6], cmd[7], cmd[8], cmd[12] = src["shape"][2], src["shape"][1], src["shape"][0], j["layer"]
        if j["opcode"] in (0, 3, 5):
            cmd[2], cmd[9], cmd[10], cmd[11] = j["weight_address"], t["shape"][2], j["stride"], int(j["depthwise"])
        elif j["opcode"] == 4:
            cmd[9] = j["fill"]
        else:
            cmd[4], cmd[5], cmd[6] = j["parameter_address"], t["bytes"], t["shape"][2]
            if j["opcode"] == 2:
                other = tensors[j["sources"][1]]
                assert other["producer"] is not None
                cmd[2] = other["offset"]
                source_mode |= 2 << 2
        deps = sorted(set(([local - 1] if local else []) +
                         [tensors[s]["producer"] for s in j["sources"] if tensors[s]["producer"] is not None]))
        assert len(deps) <= 2 and all(d < local for d in deps)
        hold = sum(1 << d for d in set([local] + consumers[j["output"]]))
        uses = [(tensors[s]["slot"], tensors[s]["producer"]) for s in j["sources"] if tensors[s]["producer"] is not None]
        assert len(uses) <= 3 and len({s for s, _ in uses}) == len(uses)
        use_slots = sum(s << (2 * u) for u, (s, _) in enumerate(uses))
        use_owners = sum(owner << (LW * u) for u, (_, owner) in enumerate(uses))
        final = local == steps - 1
        meta = [source_mode, (1 << len(deps)) - 1, *(deps + [0, 0])[:2], t["slot"],
                *[(hold >> (32 * word)) & 0xffffffff for word in range(8)],
                (1 << len(uses)) - 1, use_slots, use_owners, int(final), t["bytes"] if final else 0]
        assert len(meta) == 18
        templates.extend(cmd)
        metas.extend(meta)
        for f in range(frames):
            row = cmd.copy()
            for w, mode in ((1, source_mode & 3), (2, source_mode >> 2)):
                row[w] += image_addresses[f] if mode == 1 else (workspace_bases[f] if mode == 2 else 0)
            row[3] += workspace_bases[f]
            row[13], row[14] = 100 + f, f
            assert row[3] % 4 == 0
            node = local * frames + f
            blob = t["payloads"][f]
            node_info.extend([row[3], len(blob), len(expected), j["layer"]])
            job_reports.append(dict(node=node, local_step=local, frame=100 + f, layer=j["layer"],
                name=j["name"], opcode=j["opcode"], address=row[3], bytes=len(blob),
                expected_offset=len(expected), dependencies=[d * frames + f for d in deps],
                slot=f * 4 + t["slot"], macs=j.get("macs", 0), result=final))
            commands.extend(row)
            expected.extend(blob)
    slot_pairs = [(workspace_bases[f] + s["offset"], s["size"]) for f in range(4) for s in slots]
    info = [frames, steps, steps * frames, sram_size, init_bytes, len(expected), readonly_end, len(image_payload)]
    info += [x for pair in slot_pairs for x in pair]
    assert len(info) == 40 and len(commands) == steps * frames * 16
    assert memory[readonly_end:] == bytes([POISON]) * (init_bytes - readonly_end)
    for base, data in zip(image_addresses, inputs):
        assert memory[base:base + data.nbytes] == bytes([POISON]) * data.nbytes
    (out / "memory.bin").write_bytes(memory)
    (out / "images.bin").write_bytes(image_payload)
    (out / "expected.bin").write_bytes(expected)
    for filename, values in [("image_info.hex", image_info), ("template_commands.hex", templates),
                             ("template_meta.hex", metas), ("commands.hex", commands),
                             ("node_info.hex", node_info), ("info.hex", info)]:
        hex_words(out / filename, values)
    finals = tensors[jobs[-1]["output"]]["payloads"]
    manifest = dict(status="GENERATED_NOT_RTL_PASS", format="self-fixed-full-v1", full_network=not small,
        frames=frames, template_steps=steps, total_tasks=steps * frames, max_tasks=MAX_TASKS, iw=IW,
        template_capacity=STEPS, lw=LW, input_shape=list(inputs[0].shape), input_sources=input_sources,
        model=str(model_path), model_sha256=sha(model_path.read_bytes()), generator_sha256=sha(Path(__file__).read_bytes()),
        model_provenance_manifest=str(model_provenance_path) if model_provenance else None,
        model_provenance_sha256=sha(model_provenance_path.read_bytes()) if model_provenance else None,
        checkpoint_sha256=model_provenance.get("checkpoint_sha256") if model_provenance else None,
        layers=layer_reports, jobs=job_reports, macs_per_frame=total_macs, total_macs=total_macs * frames,
        macs_by_opcode={str(op): sum(j.get("macs", 0) for j in jobs if j["opcode"] == op) for op in (0, 3, 5)},
        memory_bytes=sram_size, init_bytes=init_bytes, readonly_end=readonly_end, expected_bytes=len(expected),
        workspace_bases=workspace_bases, workspace_bytes=slot_cursor, slots=slots,
        slot_bases=[b for b, _ in slot_pairs], slot_sizes=[n for _, n in slot_pairs],
        slotplan=[dict(name=j["output"], first=tensors[j["output"]]["first"], last=tensors[j["output"]]["last"],
                      slot=tensors[j["output"]]["slot"], offset=tensors[j["output"]]["offset"], bytes=tensors[j["output"]]["bytes"],
                      consumers=consumers[j["output"]]) for j in jobs],
        immutable=[{k: v for k, v in r.items() if k != "data"} for r in ro],
        final_bytes_per_frame=len(finals[0]), final_addresses=[workspace_bases[f] + tensors[jobs[-1]["output"]]["offset"] for f in range(frames)],
        final_expected_sha256=sha(b"".join(finals)), final_frame_sha256=[sha(b) for b in finals],
        quantization=dict(scale_policy="first_image_diagnostic_fixed_across_all_frames", calibrated_accuracy=False,
            input_scale=input_scale, input_zero=input_zero, weight_type="per_output_channel_INT8_symmetric",
            activation_type="UINT8_affine", intermediate_type="INT32_raw", shift=24, rounding="nearest_ties_away_from_zero"),
        scope="Full pretrained MobileFaceNet arithmetic on synthetic test inputs; no face recognition accuracy claim" if not small else
              "Pretrained first three Conv layers on 8x8 synthetic ROI; not full-network evidence",
        simulation_memory_only=True, cpu=False, uart=False, software_intermediate_injection=False,
        generation_seconds=time.perf_counter() - began)
    manifest["files_sha256"] = {p.name: sha(p.read_bytes()) for p in sorted(out.iterdir()) if p.is_file()}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("status", "frames", "template_steps", "total_tasks", "macs_per_frame", "init_bytes", "expected_bytes", "final_bytes_per_frame", "final_expected_sha256", "generation_seconds")}, indent=2), flush=True)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=ROOT / "build/self_full_model/mobilefacenet.onnx")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=4)
    parser.add_argument("--images", type=Path, nargs="+", help="112x112 RGB files; defaults to model-directory images/test_N.png")
    parser.add_argument("--small", action="store_true", help="pretrained first three Conv layers on 8x8 ROI")
    args = parser.parse_args()
    generate(args.model, args.out, args.frames, args.small, args.images)
