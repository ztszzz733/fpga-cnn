"""Add a third scratch destination to the existing, identical small workload."""
import argparse,hashlib,json,struct
from pathlib import Path
def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=Path('build/mobilefacenet_pipeline_data'));p.add_argument('out',type=Path);a=p.parse_args()
    src=a.source;out=a.out;out.mkdir(parents=True,exist_ok=True)
    original=(src/'memory.bin').read_bytes();mem=bytearray(original)
    report=json.loads((src/'workload.json').read_text());scratch=[0x38000,0x3a000,0x3c000]
    cursor=0x34000;words=[]
    # Each task has six 24-word images: [slot][32-output-channel group].
    for node in report['nodes']:
        old=node['config_base'];node['config_base']=cursor
        for slot in range(3):
            for group in range(2):
                cfg=list(struct.unpack_from('<24I',original,old+group*96))
                assert cfg[2]==scratch[0]+group*128
                cfg[2]=scratch[slot]+group*128
                struct.pack_into('<24I',mem,cursor,*cfg);cursor+=96
        assert node['count']*4<=8192
        words += [node[k] for k in ['deps','config_base','parameters','destination','count','channels','tag','layer','raw_golden','y']]
    assert cursor<=scratch[0] and scratch[-1]+8192<=len(mem)
    # No input, weight, parameter or feature-plane byte changes outside configs.
    assert mem[:0x34000]==original[:0x34000] and mem[cursor:]==original[cursor:]
    (out/'memory.bin').write_bytes(mem);(out/'golden.bin').write_bytes((src/'golden.bin').read_bytes())
    (out/'nodes.hex').write_text(''.join(f'{v:08x}\n' for v in words));(out/'meta.hex').write_text((src/'meta.hex').read_text())
    report.update(scratch=scratch,source_data=str(src),source_data_hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in src.iterdir() if f.is_file()},config_end=cursor)
    (out/'workload.json').write_text(json.dumps(report,indent=2));print(f"Expanded {len(report['nodes'])} tasks to 3 slots; inputs and goldens unchanged")
if __name__=='__main__':main()
