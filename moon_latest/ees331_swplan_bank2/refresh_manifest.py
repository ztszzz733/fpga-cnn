from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parent
old=json.loads((root/'baseline_source_sha256.json').read_text())
names=[name.replace('tile_local_ram_bank4.sv','tile_local_ram_bank2.sv') for name in old]
names.append('rtl/cnn_self/planned_read_adapter.sv')
manifest={name:hashlib.sha256((root/'source'/name).read_bytes()).hexdigest() for name in names}
(root/'source_sha256.json').write_text(json.dumps(manifest,indent=2)+'\n')
top='rtl/soc/ees331/face_soc_ees331_mover_top.sv'
assert manifest[top]==old[top]
(root/'profile.json').write_text(json.dumps(dict(bank_count=2,cache_bytes=401408,k3_units=2,k1_units=4,
 planned_reads=True,target_fclk_mhz=100,timing_verified=False,top_source_unchanged=True,
 source_sha256=manifest),indent=2)+'\n')
print('Recorded',len(manifest),'inputs; board top unchanged')
