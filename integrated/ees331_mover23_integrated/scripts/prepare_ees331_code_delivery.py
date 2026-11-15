"""Archive bounded final code-verification evidence without generated binaries."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[1]
RUNS={
 'soc':'20261024_215712_328991_ees331_soc',
 'four_modes':'20261024_215719_084012_ees331_full',
 'compact':'20261024_215557_216919_compact_cnn',
 'cache':'20261024_184132_914735_cnn_ddr_cache',
 'control':'20261024_184020_033055_ees331_control',
 'server':'20261024_220057_896748_ees331_server',
 'operators':'20261024_183642_006922_ees331_bram_operators',
 'cache_ooc':'20261024_184639_782498_cnn_ddr_cache_synth',
}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    out=ROOT/'deliverables/ees331_code';out.mkdir(parents=True,exist_ok=True)
    records={}
    for label,dirname in RUNS.items():
        src=ROOT/'build/runs'/dirname;report=json.loads((src/'result.json').read_text())
        assert report['status']=='PASS',dirname+' not PASS'
        hashes=report.get('source_sha256',report.get('sources_sha256',report.get('signature',{}).get('sources',{})))
        for n,h in hashes.items():
            path=ROOT/n
            if path.exists():assert sha(path)==h,'Source no longer matches evidence: '+n
        dest=out/'evidence'/label;dest.mkdir(parents=True,exist_ok=True)
        picked=[]
        for p in src.rglob('*'):
            rel=p.relative_to(src)
            if len(rel.parts)>2 or not p.is_file():continue
            if p.name not in ['result.json','metrics.json','sim.log','simulation.log','outputs.bin','events.csv','utilization.rpt','primitive_counts.tsv']:continue
            if 'compile' in rel.parts:continue
            target=dest/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target);picked.append(rel.as_posix())
        records[label]=dict(run=dirname,status='PASS',files=picked)
    for name in ['ees331_wiring_check.json','ees331_ps_port_audit.json']:
        shutil.copy2(ROOT/'build'/name,out/name)
    (out/'implementation.md').write_text('# 代码实施说明\n\n请阅读仓库中的[代码入口、接口、验证结果与边界](../../docs/ees331_code_integration.md)。\n',encoding='utf-8')
    (out/'README.md').write_text('# EES331 DDR/cache 代码交付\n\n'
        '代码已按七页接线图接入新 CNN，并通过四图小网络的真实六模块仿真。\n\n'
        '主入口：[face_soc_ees331_top.sv](../../rtl/soc/ees331/face_soc_ees331_top.sv)；'
        '[文件清单](../../rtl/filelists/system_ees331.f)；[完整改动与验证说明](../../docs/ees331_code_integration.md)。\n\n'
        'evidence 保存本次最终 PASS 原始结果、数值输出和有限日志；verification_index.json 记录来源。'
        '不是 DDR 版完整 MobileFaceNet、整机资源/时序或上板验收。\n',encoding='utf-8')
    (out/'verification_index.json').write_text(json.dumps(dict(status='PASS',scope='code and offline reduced-network validation; no board',runs=records),indent=2)+'\n')
    hashes={p.relative_to(out).as_posix():sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='sha256.json'}
    (out/'sha256.json').write_text(json.dumps(hashes,indent=2)+'\n')
    print(f'PASS: {len(records)} verification records, {len(hashes)} evidence files -> {out}')
if __name__=='__main__':main()
