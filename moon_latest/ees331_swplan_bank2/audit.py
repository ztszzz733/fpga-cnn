"""Audit the delivered source, plan transformations and completed regressions."""
from pathlib import Path
import hashlib,json,struct,sys,difflib
root=Path(__file__).resolve().parent
baseline=root.parent/'ees331_bank4_100/build_k1x4_post'
sw=root/'arm_schedule'
sys.path.insert(0,str(sw))
from planned_schema import convert_binary
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
old=json.loads((root/'baseline_source_sha256.json').read_text())
manifest=json.loads((root/'source_sha256.json').read_text())
for name,expected in manifest.items():assert sha(root/'source'/name)==expected,name
top='rtl/soc/ees331/face_soc_ees331_mover_top.sv'
assert manifest[top]==old[top]
legacy=(root.parent/'ees331_bank4_100/arm_schedule_k1x4/fixture/PLAN.BIN').read_bytes()
converted,count=convert_binary(legacy)
assert converted==(sw/'fixture/PLAN.BIN').read_bytes()
assert struct.unpack_from('<I',converted,12)[0]==0x3ff
for name in ('expected_intermediate.bin','expected_results.bin','nodes.hex','guards.hex'):
 assert sha(sw/'fixture'/name)==sha(root.parent/'ees331_bank4_100/arm_schedule_k1x4/fixture'/name),name
info=json.loads((sw/'fixture/fixture_manifest.json').read_text())
info.update(bank_count=2,cache_bytes=401408,k3_plan_version=1,k3_planned_templates=count,
            plan_sha256=sha(sw/'fixture/PLAN.BIN'))
(sw/'fixture/fixture_manifest.json').write_text(json.dumps(info,indent=2)+'\n')
changed=[name for name in manifest if name not in old or manifest[name]!=old[name]]
patch=[]
for name in changed:
 before=(baseline/'source'/name).read_text().splitlines(True) if (baseline/'source'/name).exists() else []
 patch.extend(difflib.unified_diff(before,(root/'source'/name).read_text().splitlines(True),
                                 fromfile='baseline/'+name,tofile='bank2_swplan/'+name))
(root/'RTL_changes.patch').write_text(''.join(patch),encoding='utf-8')
checks={}
for folder,files in (
 ('pager_regression',('rtl/cnn_ddr/cnn_paged_mover.sv','storage_v2/rtl/data_mover.sv','storage_v2/rtl/tile_local_ram.sv','storage_v2/rtl/tile_local_ram_bank2.sv')),
 ('planned_reads_test',('rtl/cnn_self/planned_read_adapter.sv',)),
 ('k3_planned_test',('rtl/cnn_self/self_conv_spatial4_engine.sv','rtl/cnn_self/compact_word_ram.sv','rtl/cnn_self/planned_read_adapter.sv'))):
 p=sw/folder/'result.json'
 if not p.exists():checks[folder]='pending';continue
 data=json.loads(p.read_text());assert data['status']=='PASS',folder
 test_file={'pager_regression':'pager_regression.cpp','planned_reads_test':'planned_reads_test.cpp',
            'k3_planned_test':'k3_planned_test.cpp'}[folder]
 assert data['test_sha256']==sha(sw/test_file),test_file
 if 'sources_sha256' in data:
  hashes={name.replace('\\','/'):value for name,value in data['sources_sha256'].items()}
  for name in files:assert hashes[name]==manifest[name],name
 else:assert data['source_sha256']==manifest[files[0]]
 checks[folder]='PASS'
p=sw/'simulation_bank2/result.json'
if p.exists():
 data=json.loads(p.read_text());assert data['status']=='PASS'
 assert json.loads((p.parent/'rtl_sources.json').read_text())==manifest
 assert data['outputs_sha256']==sha(p.parent/'outputs.bin')==sha(sw/'fixture/expected_results.bin')
 assert data['scheduler_sha256']==sha(sw/'schedule.c')
 assert data['harness_sha256']==sha(sw/'simulate.cpp')
 assert data['plan_sha256']==sha(sw/'fixture/PLAN.BIN')
 checks['two_image_regression']=data
else:checks['two_image_regression']='pending'
evidence=dict(top_unchanged=True,top_sha256=manifest[top],cache_bytes=401408,bank_count=2,
 k3_units=2,k1_units=4,k3_planned_templates=count,changed_inputs=changed,
 plan_sha256=sha(sw/'fixture/PLAN.BIN'),checks=checks,
 software_sources_sha256={name:sha(sw/name) for name in ('main.c','schedule.c','schedule.h','k3_plan.h','planned_schema.py')},
 synthesis_run=False,board_tested=False,timing_verified=False)
(root/'verification.json').write_text(json.dumps(evidence,indent=2)+'\n')
print(json.dumps({k:v for k,v in evidence.items() if k not in ('checks','changed_inputs')},indent=2))
print('CHECKS', {k:(v if isinstance(v,str) else v['status']) for k,v in checks.items()})
