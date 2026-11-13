"""Verify and package the second convolution optimization's small RTL evidence."""
from pathlib import Path
import argparse,hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser()
    keys=['baseline','candidate','unit_k1','unit_k3','synth_old_k1','synth_new_k1','synth_old_k3','synth_new_k3']
    for k in keys:ap.add_argument('--'+k.replace('_','-'),type=Path,required=True)
    p={k:v.resolve() for k,v in vars(ap.parse_args()).items()};r={k:read(v/'result.json') for k,v in p.items()}
    assert all(v['status']=='PASS' for v in r.values())
    assert r['synth_new_k1']['synthesis_setup_met'] and r['synth_new_k3']['synthesis_setup_met']
    a,b=r['baseline'],r['candidate'];assert a['pw4'] and b['pw4'] and not a['conv_overlap'] and b['conv_overlap']
    assert not a['full_network'] and not b['full_network'] and a['frames']==b['frames']==6
    assert a['manifest_sha256']==b['manifest_sha256'] and a['pool']==b['pool']==dict(K3=2,K1=4,Post=1,Add=1,DW7=1,Pad=1)
    for name,h in b['source_signature']['sources'].items():assert sha(ROOT/name)==h,name
    old,new=a['source_signature']['sources'],b['source_signature']['sources']
    assert old.keys()==new.keys() and {k for k in old if old[k]!=new[k]} <= {'rtl/cnn_self/self_pw4_overlap_engine.sv'}
    assert [f for f in a['source_signature']['flags'] if not f.startswith('-GCONV_OVERLAP=')]==[f for f in b['source_signature']['flags'] if not f.startswith('-GCONV_OVERLAP=')]
    assert b['runner_sha256']==sha(ROOT/'scripts/run_self_six_wsl.py')
    consumed=dict(unit_k1=['self_pw4_engine','self_pw4_overlap_engine'],unit_k3=['self_conv_engine','self_conv_pipe_engine'],synth_old_k1=['self_pw4_engine'],synth_new_k1=['self_pw4_overlap_engine'],synth_old_k3=['self_conv_engine'],synth_new_k3=['self_conv_pipe_engine'])
    for key,mods in consumed.items():
        hashes=r[key].get('sources',r[key].get('sources_sha256'))
        for mod in mods:
            rel='rtl/cnn_self/'+mod+'.sv';assert hashes[rel]==sha(ROOT/rel),(key,rel)
        if key.startswith('unit'):
            for rel in ['tb/self_optimized_unit_top.sv','tb/integration/self_optimized_unit_main.cpp']:
                assert hashes[rel]==sha(ROOT/rel)
        else:assert r[key]['part']=='xc7z020clg484-1' and r[key]['period_ns']==10
    manifest=ROOT/'build/self_six_small/manifest.json';assert sha(manifest)==b['manifest_sha256'];m=read(manifest)
    for name,h in m['files_sha256'].items():assert sha(manifest.parent/name)==h,name
    modes=['overlap','serial','preloaded','stress'];assert set(a['scenarios'])==set(b['scenarios'])==set(modes)
    rows=[]
    for mode in modes:
        for key in ['baseline','candidate']:
            s=r[key]['scenarios'][mode];v=s['metrics'];assert v==read(p[key]/mode/'metrics.json')
            assert v['status']=='PASS' and v['commands']==48 and v['macs']==614400 and v['checked_bytes']==107784
            assert sha(p[key]/mode/'outputs.bin')==s['outputs_sha256']==m['final_expected_sha256']
            assert (p[key]/mode/'outputs.bin').stat().st_size==6144
        ac=a['scenarios'][mode]['metrics']['cycles'];bc=b['scenarios'][mode]['metrics']['cycles']
        rows.append(dict(mode=mode,old_cycles=ac,new_cycles=bc,ratio=ac/bc,reduction_percent=100*(1-bc/ac)))
    u1=read(p['unit_k1']/'metrics.json');u3=read(p['unit_k3']/'metrics.json');assert len(u1['cases'])==68 and len(u3['cases'])==50
    c=u1['cases'][64];assert c['read_mac_overlap']>0 and c['write_mac_overlap']>0
    assert any(x['queue_full_cycles']>0 for x in u1['cases'])
    out=ROOT/'deliverables/conv_overlap';out.mkdir(parents=True,exist_ok=True)
    for key,path in p.items():
        dest=out/'evidence'/key;dest.mkdir(parents=True,exist_ok=True)
        for name in (['result.json','metrics.json'] if key.startswith('unit') else ['result.json','utilization.rpt','timing_summary.rpt'] if key.startswith('synth') else ['result.json']):shutil.copyfile(path/name,dest/name)
    summary=dict(status='PASS',runs={k:v.relative_to(ROOT).as_posix() for k,v in p.items()},comparison=rows,unit_k1=c,unit_k3=u3['cases'][32],unit_dw3=u3['cases'][34],source_signature=b['source_signature'],output_sha256=m['final_expected_sha256'])
    (out/'comparison.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    t=['# 卷积预取与流水优化：验证结果','',
       '保持3×3两套、1×1四套。本轮完成1×1双权重缓存预取、八字写回队列，以及3×3/DW3连续乘加流水。对照是上一版“四位置1×1＋原始3×3”，不是最早串行版。','',
       '## 六图小回归','',
       '同一六张8×8 RGB ROI、前三层及相关后处理/补边，48任务、614400 MAC、107784检查字节；四场景最终6144字节输出全部与整数参考和基线一致。','',
       '| 场景 | 上一版周期 | 本轮周期 | 周期减少 | 同频吞吐比值 |','|---|---:|---:|---:|---:|']
    labels=dict(overlap='正常并行',serial='逐帧串行',preloaded='预加载',stress='CPU访存竞争/慢结果读取')
    for x in rows:t.append(f"| {labels[x['mode']]} | {x['old_cycles']:,} | {x['new_cycles']:,} | {x['reduction_percent']:.2f}% | {x['ratio']:.3f}× |")
    cycles=rows[0]['new_cycles']
    t+=['',f"正常并行在假设100MHz下为{cycles/100000:.5f}ms。最终这轮电脑执行四场景{b['wall_seconds']:.3f}秒，编译{b['compile_seconds']:.3f}秒；不含开发、前面试验和综合时间。电脑时间与硬件周期不同。",'',
        '最早未优化的小回归为570511拍；本轮263887拍。这仅是同一小数据的历史对照，不能按比例推算原完整六图的8.98秒。','',
        '## 单层和真实重叠','',
        '1×1通过68组数值对照，K3通过50组普通/DW3数值对照；两套测试分别包含3次clear重启、描述符锁存、13种非法配置及2组同拍响应。覆盖步长、奇数通道/尾块、未对齐、512通道和长延迟。','',
        f"1×1样例4×4、64输入/64输出通道：{c['old_cycles']:,}→{c['new_cycles']:,}拍，约{c['old_cycles']/c['new_cycles']:.3f}倍。读写请求仍为{c['new_requests']:,}次、读取{c['new_bytes']:,}字节，收益来自重叠和减少控制空拍。观察到{c['read_mac_overlap']}拍MAC与读响应同拍、{c['write_mac_overlap']}拍MAC与写响应同拍；不是用busy推测重叠。另一个压力样例确实经历队列满，仍完整写出且正确。",'']
    for title,idx in [('普通3×3：5×5×64输入、3输出通道',32),('DW3：5×5×64输入、64输出通道',34)]:
        x=u3['cases'][idx];t.append(f"- {title}：{x['old_cycles']:,}→{x['new_cycles']:,}拍；连续有效MAC最长{x['consecutive_mac_cycles']}拍。")
    t+=['','3×3仍逐字节加载，仍在计算结束后写回；计算流水不能消除全部访存时间。单层测试数值由独立标量参考生成，参考中间结果没有代替RTL计算。','',
        '## 单引擎资源与时序','', '| 引擎 | LUT | FF | BRAM Tile | DSP | 10ns综合WNS |','|---|---:|---:|---:|---:|---:|']
    for key,label in [('synth_old_k1','上一版K1'),('synth_new_k1','双缓冲K1'),('synth_old_k3','上一版K3'),('synth_new_k3','流水K3')]:
        s=r[key];u=s['utilization'];v=[u[n]['used'] for n in ['Slice LUTs','Slice Registers','Block RAM Tile','DSPs']]
        t.append(f"| {label} | {v[0]} | {v[1]} | {v[2]} | {v[3]} | {s['worst_setup_slack_ns']:+.3f}ns |")
    t+=['','Vivado2025.2，XC7Z020-CLG484-1，OOC综合。WNS非负表示通过此阶段的时钟约束；没有整机布局布线或板级频率结论。DSP为0表示乘法映射到逻辑。K1每套多一个RAMB18，四套共增加两个36Kb BRAM Tile；八字队列也有逻辑资源成本。','',
        '## 启用及范围','',
        '`CONV_OVERLAP=1`启用本轮两项优化。六图runner使用`--conv-overlap`；不带它、只带`--pw4`可回到上一版。默认硬件生成参数保留0，本轮新配置由仿真runner显式选择。','',
        '本轮没有重跑完整MobileFaceNet，也没有做卷积与后处理融合。32MiB实验SRAM、合成ROI、诊断量化不代表512KiB适配或识别准确率；不包含CPU固件/UART、层内条带输入。未启动长仿真或定时检查。','',
        '[结构及复现说明](../../docs/conv_overlap_design.md) · [机器可读数据](comparison.json)','', '## 证据目录','']
    for key,path in p.items():t.append(f"- {key}：`{path.relative_to(ROOT).as_posix()}`，[结果副本](evidence/{key}/result.json)")
    t+=['',f"输出SHA256：`{m['final_expected_sha256']}`。已按各配置实际使用的模块核对源码、数据和输出哈希；未使用模块的旧编译快照不冒充当前源码证明。",'']
    (out/'README.md').write_text('\n'.join(t),encoding='utf-8');print('PASS',out)
if __name__=='__main__':main()
