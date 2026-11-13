"""Verify an unpacked handoff without depending on the original workspace."""
import argparse
import hashlib
import json
from pathlib import Path
from cnn_tile_handoff_case import verify

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(data):return hashlib.sha256(data).hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('root',type=Path,nargs='?',default=Path(__file__).resolve().parents[1]);a=ap.parse_args();root=a.root.resolve()
    inventory=read(root/'MANIFEST.sha256.json')['files']
    for name,entry in inventory.items():
        path=(root/name).resolve();assert path.is_relative_to(root),name
        blob=path.read_bytes();assert len(blob)==entry['bytes'] and sha(blob)==entry['sha256'],name
    signature=read(root/'source_snapshot/build_signature.json')['signature']['sources']
    for name,h in signature.items():assert sha((root/'source_snapshot'/name).read_bytes())==h,name
    for case in sorted((root/'cases').iterdir()):
        if case.is_dir() and (case/'manifest.json').exists():verify(case)
    lanes=read(root/'cases/unaligned_lane_vectors.json')['cases'];assert len(lanes)==96
    coverage=set()
    for case in lanes:
        target=bytearray.fromhex(case['initial_destination_hex']);source=bytes.fromhex(case['initial_source_hex'])
        direction=case['direction'];n=case['bytes'];local=case['local_start'];ddr=case['ddr_start']
        src,dst=(ddr,local) if direction=='DDR_TO_LOCAL' else (local,ddr)
        assert ddr%8==0 and local%8==case['local_lane']
        before=bytes(target);target[dst:dst+n]=source[src:src+n]
        assert bytes(target).hex()==case['expected_destination_hex']
        assert target[:dst]==before[:dst] and target[dst+n:]==before[dst+n:]
        coverage.add((direction,case['local_lane'],n))
    assert len(coverage)==96
    rtl=read(root/'evidence/tile_core_rtl/result.json');assert rtl['status']=='PASS' and len(rtl['scenarios'])==6
    for name,entry in rtl['scenarios'].items():
        dest=root/'evidence/tile_core_rtl'/name
        assert read(dest/'metrics.json')['status']=='PASS'
        assert sha((dest/'outputs.bin').read_bytes())==entry['output_sha256']
    prior=root/'evidence/ten_image_16_units';p=read(prior/'result.json');m=read(prior/'data_manifest.json')
    assert p['status']=='PASS' and p['frames']==10
    assert sha((prior/'outputs.bin').read_bytes())==m['final_expected_sha256']==p['scenarios']['overlap']['outputs_sha256']
    print('PASS portable package: '+str(len(inventory))+' file hashes, source hashes, 2 integer tile cases, 96 lane vectors, 6 recorded CNN/SRAM RTL checks, ten-image result')
    print('MOVER RTL, new adapter RTL, PS DDR and same-top resources: NOT VALIDATED BY THIS PACKAGE')

if __name__=='__main__':main()
