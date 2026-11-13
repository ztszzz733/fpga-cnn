from pathlib import Path
import json,csv,struct
R=Path(__file__).resolve().parents[1]
src=R/'incoming/CNN_storage_handoff_v0.2/cases'
out=R/'build/vectors';out.mkdir(parents=True,exist_ok=True)
records=[]
for c in json.loads((src/'unaligned_lane_vectors.json').read_text())['cases']:
    direction=c['direction']=='LOCAL_TO_DDR'
    a=bytes.fromhex(c['initial_source_hex']);b=bytes.fromhex(c['initial_destination_hex'])
    ddr,local=(b,a) if direction else (a,b)
    s,d=(c['local_start'],c['ddr_start']) if direction else (c['ddr_start'],c['local_start'])
    records.append((ddr,local,s,d,c['bytes'],int(direction)))
for case in ['short_row_2x2x2','tile_8x8x32']:
    p=src/case
    for row in csv.DictReader((p/'moves.csv').open()):
        s,d,n,flag=[int(row[k]) for k in ['src','dst','bytes','flags_proposed']]
        ddr=bytearray((p/'ddr_initial.bin').read_bytes());local=bytearray((p/'local_initial.bin').read_bytes())
        # Transport-only source stimulus. No claim of CNN compute in this test.
        if flag: local[s:s+n]=(p/'ddr_expected.bin').read_bytes()[d:d+n]
        records.append((ddr,local,s,d,n,flag))
with (out/'transfers.bin').open('wb') as f:
    f.write(struct.pack('<I',len(records)))
    for a,b,s,d,n,flag in records:
        f.write(struct.pack('<6I',len(a),len(b),s,d,n,flag));f.write(a);f.write(b)
print('prepared transport cases',len(records))
