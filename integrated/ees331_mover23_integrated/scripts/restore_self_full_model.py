"""Verify the pinned MobileFaceNet checkpoint, export ONNX, and test four images.

Dependencies are resolved from .tools/mobilefacenet-python before global Python.
The checkpoint must already be cloned into .tools/mobilefacenet-upstream at the
exact pinned commit. The known SHA256 is checked BEFORE torch.jit.load; arbitrary
pickle/checkpoint files and upstream Python model code are never executed.
"""
from __future__ import annotations

import collections
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/self_full_model"
UPSTREAM = ROOT / ".tools/mobilefacenet-upstream"
COMMIT = "a6cc9032a659b615f477833e1a70b5e7931bcccc"
CHECKPOINT_SHA = "780e31e7c2639a0d5fdebe843f5df3ff81fda79a090164df0ff40514d172853a"
HISTORICAL_ONNX_SHA = "28ee4f5fb6c4f0bc0a2a66c1ec7a0b6fed0593013c0a8f442d5dd4af08b0f8fe"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    started = time.perf_counter()
    checkpoint = UPSTREAM / "pretrained_model/mobilefacenet_scripted.pt"
    commit = subprocess.check_output(
        ["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True
    ).strip()
    if commit != COMMIT:
        raise RuntimeError(f"Upstream commit mismatch: {commit}")
    checkpoint_sha = sha(checkpoint)
    if checkpoint_sha != CHECKPOINT_SHA:
        raise RuntimeError(f"Checkpoint SHA256 mismatch: {checkpoint_sha}")
    print(f"CHECKPOINT_VERIFIED {checkpoint_sha}", flush=True)

    sys.path.insert(0, str(ROOT / ".tools/mobilefacenet-python"))
    import numpy as np
    import onnx
    from onnx import numpy_helper
    import onnxruntime as ort
    import PIL
    from PIL import Image
    import torch

    OUT.mkdir(parents=True, exist_ok=True)
    image_dir = OUT / "images"
    image_dir.mkdir(exist_ok=True)
    torch.set_num_threads(2)
    model = torch.jit.load(str(checkpoint), map_location="cpu").eval()
    (OUT / "torchscript_graph.txt").write_text(str(model.inlined_graph), encoding="utf-8")
    onnx_path = OUT / "mobilefacenet.onnx"
    with torch.inference_mode():
        torch.onnx.export(
            model, torch.zeros(1, 3, 112, 112), str(onnx_path),
            opset_version=17, input_names=["image"], output_names=["embedding"],
            do_constant_folding=True, dynamo=False,
        )
    graph = onnx.shape_inference.infer_shapes(onnx.load(onnx_path))
    onnx.checker.check_model(graph)
    onnx.save(graph, onnx_path)
    shapes = {v.name: [d.dim_value for d in v.type.tensor_type.shape.dim]
              for v in [*graph.graph.input, *graph.graph.value_info, *graph.graph.output]}
    tensors = {t.name: numpy_helper.to_array(t) for t in graph.graph.initializer}
    inventory = []
    for index, node in enumerate(graph.graph.node):
        row = dict(index=index, name=node.name, op=node.op_type,
                   inputs=list(node.input), output=node.output[0],
                   output_shape=shapes.get(node.output[0], []))
        if node.op_type == "Conv":
            attrs = {a.name: onnx.helper.get_attribute_value(a) for a in node.attribute}
            weight = tensors[node.input[1]]
            row.update(kernel=list(weight.shape[2:]), group=int(attrs.get("group", 1)),
                       strides=attrs.get("strides", [1, 1]),
                       pads=attrs.get("pads", [0, 0, 0, 0]),
                       weight_shape=list(weight.shape),
                       macs=math.prod(row["output_shape"]) * math.prod(weight.shape[1:]))
        inventory.append(row)
    op_counts = dict(collections.Counter(row["op"] for row in inventory))
    macs = sum(row.get("macs", 0) for row in inventory)
    if op_counts.get("Conv") != 51 or op_counts.get("Add") != 12 or macs != 233810432:
        raise RuntimeError(f"Unexpected full network: {op_counts}, MACs={macs}")
    (OUT / "operators.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")

    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(onnx_path), options, providers=["CPUExecutionProvider"])
    yy, xx = np.indices((112, 112), dtype=np.int32)
    cc = np.arange(3, dtype=np.int32)[None, None, :]
    # Integer-only patterns avoid RNG/version dependence and exercise all RGB
    # values, local edges, distinct spatial frequencies, and distinct frame IDs.
    images, inputs, torch_outputs, onnx_outputs = [], [], [], []
    for frame in range(4):
        rgb = (((xx[..., None] * (3 + 2 * frame)
                 + yy[..., None] * (5 + 4 * frame) + cc * (47 + frame * 6)
                 + ((xx[..., None] // (7 + frame)) ^ (yy[..., None] // (5 + frame))) * 29
                 + frame * 61) % 256).astype(np.uint8))
        image_path = image_dir / f"test_{frame}.png"
        Image.fromarray(rgb).save(image_path)
        normalized = rgb.astype(np.float32) / np.float32(255)
        normalized = ((normalized - np.array([.485, .456, .406], dtype=np.float32))
                      / np.array([.229, .224, .225], dtype=np.float32))
        x = normalized.transpose(2, 0, 1)[None].copy()
        with torch.inference_mode():
            ty = model(torch.from_numpy(x)).numpy()
        oy = session.run(None, {"image": x})[0]
        if ty.shape != (1, 128) or oy.shape != (1, 128):
            raise RuntimeError(f"Invalid embedding shape for frame {frame}")
        if not np.isfinite(ty).all() or not np.isfinite(oy).all():
            raise RuntimeError(f"Non-finite embedding for frame {frame}")
        np.testing.assert_allclose(oy, ty, rtol=2e-4, atol=2e-5)
        images.append(dict(frame=frame, path=str(image_path), sha256=sha(image_path),
                           raw_rgb_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(),
                           shape=list(rgb.shape), synthetic=True,
                           torch_onnx_max_abs_error=float(np.max(np.abs(ty - oy)))))
        inputs.append(x[0]); torch_outputs.append(ty[0]); onnx_outputs.append(oy[0])
        print(f"IMAGE_PASS frame={frame} max_error={images[-1]['torch_onnx_max_abs_error']:.9g}", flush=True)
    if len({row["raw_rgb_sha256"] for row in images}) != 4:
        raise RuntimeError("Synthetic inputs must all differ")
    np.save(OUT / "inputs_nchw.npy", np.stack(inputs))
    np.save(OUT / "torch_embeddings.npy", np.stack(torch_outputs))
    np.save(OUT / "onnx_embeddings.npy", np.stack(onnx_outputs))
    record = dict(
        status="PASS", source="https://github.com/foamliu/MobileFaceNet",
        upstream_commit=commit, checkpoint=str(checkpoint), checkpoint_sha256=checkpoint_sha,
        checkpoint_hash_verified_before_loading=True,
        model=str(onnx_path), onnx_sha256=sha(onnx_path),
        historical_onnx_sha256=HISTORICAL_ONNX_SHA,
        historical_onnx_hash_equal=sha(onnx_path) == HISTORICAL_ONNX_SHA,
        historical_onnx_note="Exporter-version-dependent bytes; checkpoint and graph shape/MAC inventory are pinned.",
        script_sha256=sha(Path(__file__)),
        versions=dict(python=sys.version, torch=torch.__version__, onnx=onnx.__version__,
                      onnxruntime=ort.__version__, numpy=np.__version__, pillow=PIL.__version__),
        export=dict(opset=17, dynamo=False, constant_folding=True, input="image", output="embedding"),
        input_shape=[1, 3, 112, 112], output_shape=[1, 128],
        parameters=sum(p.numel() for p in model.parameters()), op_counts=op_counts,
        convolution_macs=macs, images=images,
        preprocessing=dict(layout="NCHW", color="RGB", mean=[.485, .456, .406],
                           std=[.229, .224, .225], range_before_normalization=[0, 1],
                           source="pinned upstream data_gen.py val transform", horizontal_flip=False),
        purpose="Full-shape synthetic numerical and RTL throughput verification; not face accuracy evaluation.",
        accuracy_evaluated=False, full_network_rtl=False, quantized_network=False,
        total_seconds=time.perf_counter() - started,
    )
    (OUT / "manifest.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"MODEL_READY {onnx_path}", flush=True)
    print(json.dumps(record, indent=2), flush=True)


if __name__ == "__main__":
    main()
