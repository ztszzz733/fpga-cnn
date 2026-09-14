"""Independent integer CNN reference. HWC activations; OHWI weights.

Produces sparse little-endian RAM images, byte golden files and a bench manifest.
No NumPy/framework dependency and no RTL-derived intermediates.
"""
from pathlib import Path
import json
import random

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build" / "vectors"
INPUT, WEIGHT, BIAS, OUTPUT = 0x101, 0x30003, 0x31000, 0x32001


def int32(n):
    return ((n + (1 << 31)) % (1 << 32)) - (1 << 31)


def reference(w, h, ci, co, stride, pad, shift, relu, pool, inputs, weights, biases):
    cw, ch = (w + 2 * pad - 3) // stride + 1, (h + 2 * pad - 3) // stride + 1
    conv = []
    for y in range(ch):
        for x in range(cw):
            for oc in range(co):
                total = biases[oc]
                for ky in range(3):
                    iy = y * stride + ky - pad
                    for kx in range(3):
                        ix = x * stride + kx - pad
                        if 0 <= ix < w and 0 <= iy < h:
                            for ic in range(ci):
                                total += inputs[(iy * w + ix) * ci + ic] * weights[((oc * 3 + ky) * 3 + kx) * ci + ic]
                total = int32(total)
                conv.append(max(total, 0) if relu else total)
    ow, oh = (cw // 2, ch // 2) if pool else (cw, ch)
    result = []
    for y in range(oh):
        for x in range(ow):
            for oc in range(co):
                if pool:
                    value = max(conv[((2 * y + dy) * cw + 2 * x + dx) * co + oc]
                                for dy in range(2) for dx in range(2))
                else:
                    value = conv[(y * cw + x) * co + oc]
                result.append(max(0 if relu else -128, min(127, value >> shift)))
    return ow, oh, result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # name,width,height,IC,OC,stride,pad,shift,ReLU,pool
    cases = [
        ("sanity", 3, 3, 1, 1, 1, 0, 0, 0, 0),
        ("rgb_signed", 5, 4, 3, 3, 1, 1, 2, 0, 0),
        ("relu_saturation", 4, 4, 1, 2, 1, 1, 0, 1, 0),
        ("negative_pool", 5, 5, 2, 2, 1, 1, 3, 0, 1),
        ("stride_pool", 7, 6, 3, 2, 2, 1, 3, 1, 1),
        ("padding_two", 2, 3, 2, 1, 1, 2, 0, 0, 0),
        ("shift_255", 3, 3, 1, 2, 1, 0, 255, 0, 0),
        ("int32_wrap", 3, 3, 1, 2, 1, 0, 0, 0, 0),
        ("pool_odd_drop", 5, 5, 1, 1, 1, 0, 1, 0, 1),
    ]
    rng = random.Random(20260911)
    for i in range(6):
        while True:
            w, h, s, p, pool = rng.randint(3, 8), rng.randint(3, 8), rng.randint(1, 3), rng.randint(0, 2), rng.randint(0, 1)
            if min((w+2*p-3)//s+1, (h+2*p-3)//s+1) >= (2 if pool else 1):
                break
        cases.append((f"random_{i}", w, h, rng.randint(1, 4), rng.randint(1, 3), s, p, rng.randint(0, 5), rng.randint(0, 1), pool))
    cases.append(("rgb_224", 224, 224, 3, 1, 1, 1, 8, 1, 0))
    manifest, calls = [], []
    for name, w, h, ci, co, s, p, q, relu, pool in cases:
        inputs = [rng.randint(-16, 16) for _ in range(w*h*ci)]
        weights = [rng.randint(-8, 8) for _ in range(9*ci*co)]
        biases = [rng.randint(-200, 200) for _ in range(co)]
        inputs[0], inputs[-1] = -128, 127
        weights[0], weights[-1] = -128, 127
        if name == "sanity":
            inputs, weights, biases = list(range(1, 10)), [1]*9, [0]
        if name == "negative_pool":
            inputs = [rng.randint(-9, 9) for _ in inputs]
            weights = [rng.randint(-3, 3) for _ in weights]
            biases = [-400, -500]
        if name == "shift_255":
            weights, biases = [0]*len(weights), [100, -100]
        if name == "int32_wrap":
            inputs, weights, biases = [127]*9, [1]*9+[-1]*9, [2147483647, -2147483648]
        ow, oh, expected = reference(w,h,ci,co,s,p,q,relu,pool,inputs,weights,biases)
        sections = [(INPUT, inputs), (WEIGHT, weights),
                    (BIAS, [byte for bias in biases for byte in (bias & 0xffffffff).to_bytes(4, "little")])]
        text = "".join(f"@{addr:08x}\n" + "\n".join(f"{v & 255:02x}" for v in values) + "\n" for addr, values in sections)
        (OUT / f"{name}.memh").write_text(text, encoding="ascii")
        (OUT / f"{name}.golden.hex").write_text("\n".join(f"{v & 255:02x}" for v in expected)+"\n", encoding="ascii")
        manifest.append(dict(name=name,width=w,height=h,input_channels=ci,output_channels=co,
                             stride=s,padding=p,quant_shift=q,relu=bool(relu),pool=bool(pool),
                             output_width=ow,output_height=oh,output_bytes=len(expected),first_outputs=expected[:16]))
        calls.append(f'run_case("{name}",{w},{h},{ci},{co},{s},{p},{q},{relu},{pool},{len(expected)});')
    (OUT / "cases.svh").write_text("\n".join(calls)+"\n", encoding="ascii")
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    assert manifest[0]["first_outputs"] == [45]
    assert next(c for c in manifest if c["name"] == "shift_255")["first_outputs"] == [0,-1]
    assert next(c for c in manifest if c["name"] == "int32_wrap")["first_outputs"] == [-128,127]
    print(f"Generated {len(cases)} deterministic CNN cases ({sum(c['output_bytes'] for c in manifest)} golden bytes)")


if __name__ == "__main__":
    main()
