"""Ten distinct deterministic numerical images, retaining the previous six inputs."""
from pathlib import Path
import hashlib
import json
import sys
from gen_self_full import ROOT, generate


def main():
    from PIL import Image
    out = ROOT / 'build/self_ten_images'
    out.mkdir(exist_ok=True)
    images = [ROOT / 'build/self_full_model/images' / f'test_{i}.png' for i in range(6)]
    for frame in range(6, 10):
        raw = bytes((x * (3 + 2 * frame) + y * (5 + 4 * frame)
                     + c * (47 + frame * 6) + ((x // (7 + frame)) ^ (y // (5 + frame))) * 29
                     + frame * 61) % 256
                    for y in range(112) for x in range(112) for c in range(3))
        image = out / f'test_{frame}.png'
        if image.exists():
            assert Image.open(image).convert('RGB').tobytes() == raw
        else:
            Image.frombytes('RGB', (112, 112), raw).save(image)
        images.append(image)
    for small in (True, False):
        target = ROOT / ('build/self_ten_small' if small else 'build/self_ten_full')
        generate(ROOT/'build/self_full_model/mobilefacenet.onnx', target,
                 frames=10, small=small, images=images, contexts=10, max_tasks=2048)


if __name__ == '__main__':
    main()
