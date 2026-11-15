"""Small mode probes using the hash-checked stripe simulator; run in WSL.

Synthetic unsigned activations, signed weights, valid convolution. This tests
mode plumbing, not pretrained-network accuracy. No recompilation or RTL edits.
"""
import argparse
import datetime
import json
import random
import struct
import time

from run_neureka_stripes import ROOT, build, generate
from run_tests import execute


def prepare(folder, mode, prefetch=None):
    h, w, ci = 10, 7, (4 if mode == 'stride2_depthwise3x3' else 3)
    strided = mode.startswith('stride2_')
    dw = mode.endswith('depthwise3x3')
    # Verified integration workaround: native DW+stride2 only with prefetch
    # disabled. Keep --force-prefetch for reproducing the saved failure.
    if prefetch is None:
        prefetch = not (dw and strided)
    co = ci if dw else (8 if strided else 5)
    spec = generate(folder, h, w, ci, co, frames=2)
    mem = bytearray((folder/'memory.bin').read_bytes())
    src = (folder/'source.bin').read_bytes()
    k = 1 if mode == 'pointwise1x1' else 3
    rng = random.Random(73)
    weights = [rng.randrange(-4, 5) for _ in range(co*(1 if dw else ci)*k*k)]
    # Same bit-plane order as the Apache-2.0 upstream NeurekaMemoryLayout.py:
    # oc -> bit -> tap -> 32 input-channel bits; DW swaps oc and ic.
    packed = bytearray()
    for oc in range(1 if dw else co):
        for bit in range(8):
            for tap in range(k*k):
                bits = 0
                for ic in range(ci):
                    idx = ic*k*k+tap if dw else (oc*ci+ic)*k*k+tap
                    bits |= (((weights[idx]+128) >> bit) & 1) << ic
                packed.extend(struct.pack('<I', bits))
    mem[0x1000:0x2000] = bytes([0xa5])*0x1000
    mem[0x1000:0x1000+len(packed)] = packed
    oh, ow = ((h-1)//2, (w-1)//2) if strided else (h-2, w-2)
    gold, relu = bytearray([0xa5]*65536), bytearray([0xa5]*65536)
    for frame in range(2):
        for y in range(oh):
            for x in range(ow):
                for oc in range(co):
                    acc = 0
                    for ic in ([oc] if dw else range(ci)):
                        for ky in range(k):
                            for kx in range(k):
                                wi = oc*k*k+ky*k+kx if dw else (oc*ci+ic)*k*k+ky*k+kx
                                step = 2 if strided else 1
                                acc += src[0x4000+frame*0x1000+((y*step+ky)*w+x*step+kx)*ci+ic]*weights[wi]
                    v = max(-128, min(127, acc >> 5))
                    a = 0x8000+frame*0x2000+(y*ow+x)*co+oc
                    gold[a], relu[a] = v & 255, max(0, v)
    for job in spec['jobs']:
        cfg = list(struct.unpack_from('<24I', mem, job[0]))
        if k == 1:
            cfg[12], cfg[13] = 32, 32
            cfg[17] = cfg[16]
            cfg[23] |= 2 << 5
        elif dw:
            cfg[13] = 0
            cfg[23] |= 1 << 5
        if strided:
            # Mask alternate PEs; each enabled PE advances two address slots.
            # Fractional-pixel strides require even byte counts in this probe.
            cfg[10], cfg[11] = co//2, ow*co//2
            cfg[23] |= 1 << 8
            rows = (job[13] >> 16)//2
            job[5] = rows*ow*co
            job[6] = 0x8000+job[3]*0x2000+(job[7]//2)*ow*co
            job[10] = job[6]
            job[13] = rows << 16 | ow
        if not prefetch:
            cfg[23] &= ~(1 << 10)
        struct.pack_into('<24I', mem, job[0], *cfg)
    (folder/'memory.bin').write_bytes(mem)
    if strided:
        (folder/'jobs.hex').write_text(''.join(f'{v:08x}\n' for job in spec['jobs'] for v in job))
        meta = [int(line,16) for line in (folder/'meta.hex').read_text().splitlines()]
        meta[10] = oh*ow*co
        (folder/'meta.hex').write_text(''.join(f'{v:08x}\n' for v in meta))
    for name, data in [('conv.hex', gold), ('relu.hex', relu)]:
        (folder/name).write_text(''.join(f'{v:02x}\n' for v in data))
    spec.update(mode=mode, prefetch=prefetch, weights=weights, output_roi=[oh,ow],
                note='1x1 tests top-left ROI, not full image; extra rows still loaded for existing streaming checks' if k == 1 else ('native stride2 bit8, even output channel count, valid convolution' if strided else 'valid DW3x3, channel multiplier 1'))
    (folder/'workload.json').write_text(json.dumps(spec, indent=2))
    return spec


def main():
    modes = ['pointwise1x1', 'depthwise3x3', 'stride2_3x3', 'stride2_depthwise3x3']
    parser = argparse.ArgumentParser()
    parser.add_argument('--modes', nargs='+', choices=modes, default=modes)
    flags=parser.add_mutually_exclusive_group()
    flags.add_argument('--no-prefetch', action='store_true')
    flags.add_argument('--force-prefetch', action='store_true')
    args = parser.parse_args()
    out = ROOT/'build/runs'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_neureka_model_modes')
    out.mkdir(parents=True)
    print('RUN_DIR='+str(out), flush=True)
    start = time.perf_counter()
    exe, env, compile_time, key = build(out, reuse=True)
    result = dict(status='RUNNING', build_inputs=key, compile_seconds=compile_time, cases={})
    for mode in args.modes:
        case = out/mode
        case.mkdir()
        spec=prepare(case, mode, prefetch=False if args.no_prefetch else (True if args.force_prefetch else None))
        stamp = time.perf_counter()
        try:
            execute([exe, '+serial'], case, env, case/'sim.log', timeout=120)
            assert 'PASS tb_neureka_stripes' in (case/'sim.log').read_text()
            record = dict(status='PASS', metrics=json.loads((case/'metrics.json').read_text()))
        except Exception as exc:
            record = dict(status='FAIL', error=str(exc))
        record['simulation_seconds'] = time.perf_counter()-stamp
        record['prefetch'] = spec['prefetch']
        result['cases'][mode] = record
        (out/'result.json').write_text(json.dumps(result, indent=2))
        print(mode+': '+json.dumps(record), flush=True)
    result['status'] = 'PASS' if all(c['status']=='PASS' for c in result['cases'].values()) else 'FAIL'
    result['total_seconds'] = time.perf_counter()-start
    (out/'result.json').write_text(json.dumps(result, indent=2))
    return result['status'] != 'PASS'


if __name__ == '__main__':
    raise SystemExit(main())
