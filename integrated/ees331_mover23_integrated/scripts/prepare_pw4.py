"""Verify pointwise experiment provenance and write the small-regression report."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]

def read(p):
    return json.loads(p.read_text(encoding='utf-8'))

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap = argparse.ArgumentParser()
    for name in ('baseline', 'candidate', 'unit', 'synth_old', 'synth_new'):
        ap.add_argument('--' + name.replace('_', '-'), type=Path, required=True)
    args = ap.parse_args()
    paths = {k: v.resolve() for k, v in vars(args).items()}
    r = {k: read(p/'result.json') for k, p in paths.items()}
    assert all(x['status'] == 'PASS' for x in r.values())
    old, new = r['baseline'], r['candidate']
    assert not old['pw4'] and new['pw4'] and not old['full_network'] and not new['full_network']
    assert old['manifest_sha256'] == new['manifest_sha256']
    assert old['pool'] == new['pool'] == dict(K3=2, K1=4, Post=1, Add=1, DW7=1, Pad=1)
    expected_difference = {'rtl/cnn_self/self_pw4_engine.sv'}
    before, after = old['source_signature']['sources'], new['source_signature']['sources']
    assert before.keys() == after.keys()
    assert {k for k in before if before[k] != after[k]} <= expected_difference
    assert [x for x in old['source_signature']['flags'] if not x.startswith('-GPW4=')] == [x for x in new['source_signature']['flags'] if not x.startswith('-GPW4=')]
    for name, digest in after.items():
        assert sha(ROOT/name) == digest, name
    for name, digest in r['unit']['sources'].items():
        assert sha(ROOT/name) == digest, name
    for key, source in (('synth_old', 'rtl/cnn_self/self_conv_engine.sv'), ('synth_new', 'rtl/cnn_self/self_pw4_engine.sv')):
        assert r[key]['sources_sha256'][source] == sha(ROOT/source)
        assert r[key]['part'] == 'xc7z020clg484-1' and r[key]['period_ns'] == 10
    manifest = read(ROOT/'build/self_six_small/manifest.json')
    assert sha(ROOT/'build/self_six_small/manifest.json') == new['manifest_sha256']
    for name, digest in manifest['files_sha256'].items():
        assert sha(ROOT/'build/self_six_small'/name) == digest, name
    modes = ['overlap', 'serial', 'preloaded', 'stress']
    assert set(old['scenarios']) == set(new['scenarios']) == set(modes)
    rows = []
    for mode in modes:
        a, b = old['scenarios'][mode], new['scenarios'][mode]
        for key, scenario in (('baseline', a), ('candidate', b)):
            assert sha(paths[key]/mode/'outputs.bin') == scenario['outputs_sha256'] == manifest['final_expected_sha256']
            assert scenario['metrics'] == read(paths[key]/mode/'metrics.json')
            assert scenario['metrics']['commands'] == 48
        ac, bc = a['metrics']['cycles'], b['metrics']['cycles']
        rows.append(dict(mode=mode, old_cycles=ac, new_cycles=bc, ratio=ac/bc, reduction_percent=100*(1-bc/ac)))
    unit = read(paths['unit']/'metrics.json')
    case = next(c for c in unit['cases'] if c['id'] == 64)
    out = ROOT/'deliverables/self_pw4'
    out.mkdir(parents=True, exist_ok=True)
    for key, path in paths.items():
        dest = out/'evidence'/key
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path/'result.json', dest/'result.json')
        if key == 'unit':
            shutil.copyfile(path/'metrics.json', dest/'metrics.json')
        if key.startswith('synth'):
            for name in ('utilization.rpt', 'timing_summary.rpt'):
                shutil.copyfile(path/name, dest/name)
    report = dict(status='PASS', runs={k: str(p.relative_to(ROOT)) for k, p in paths.items()},
                  cases=len(unit['cases']), comparison=rows, representative_unit=case,
                  final_expected_sha256=manifest['final_expected_sha256'], current_sources=after)
    (out/'comparison.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    text = ['# 1×1四位置并行：小回归已通过', '',
            '2026-10-23。保持3×3两套、1×1四套；每套1×1改为四位置并行、同步读/乘法/累加流水、对齐32位加载。所有结果均来自真实RTL，本轮未运行完整MobileFaceNet。', '',
            '## 六图对照', '',
            '同一六图8×8 RGB ROI、首三层及相关处理、48任务，每场景107,784字节检查，最终6,144字节输出全部逐字节匹配。串行场景按原runner逐帧串行提交；正常并行为六帧交错。', '',
            '| 场景 | 旧版周期 | 优化版周期 | 周期减少 | 同频比值 |', '|---|---:|---:|---:|---:|']
    labels = dict(overlap='正常并行', serial='串行对照', preloaded='预加载', stress='压力/反压')
    for x in rows:
        text.append(f"| {labels[x['mode']]} | {x['old_cycles']:,} | {x['new_cycles']:,} | {x['reduction_percent']:.2f}% | {x['ratio']:.3f}× |")
    text += ['', f"最终小回归电脑执行 {new['wall_seconds']:.3f} 秒，编译 {new['compile_seconds']:.3f} 秒；不包括此前调试、单测及综合耗时。周期表与电脑运行耗时是两回事。", '',
             '## 单层及协议', '',
             f"{len(unit['cases'])}组数值对照、3次clear重启、描述符锁存、13种非法配置、2组同拍响应通过；覆盖奇数通道、未对齐、尾块、stride=1/2、1～512输入通道和访存反压。", '',
             f"示例4×4、64输入/64输出通道、65,536 MAC：{case['old_cycles']:,} → {case['new_cycles']:,}拍，约{case['old_cycles']/case['new_cycles']:.2f}倍；请求{case['old_requests']:,} → {case['new_requests']:,}次，读入字节量均{case['new_bytes']:,}。计算阶段观察到64拍连续有效累加。该样例收益不能当成完整网络收益。", '',
             '## 资源和时序', '', '| 单个K1引擎 | 旧版 | 优化版 |', '|---|---:|---:|']
    for name in ('Slice LUTs', 'Slice Registers', 'Block RAM Tile', 'DSPs'):
        text.append(f"| {name} | {r['synth_old']['utilization'][name]['used']} | {r['synth_new']['utilization'][name]['used']} |")
    text += [f"| 10ns综合WNS | {r['synth_old']['worst_setup_slack_ns']} ns | {r['synth_new']['worst_setup_slack_ns']} ns |", '',
             f"优化版综合时序达标：{'是' if r['synth_new']['synthesis_setup_met'] else '否'}。Vivado 2025.2，XC7Z020-CLG484-1，单引擎OOC综合；没有整机布局布线或板级频率验证。DSP=0表示本次工具将乘法实现于逻辑资源，不是没有乘法。", '',
             '四个K1的缓存合计10个BRAM Tile（20个RAMB18），只是K1部分。没有解决整机512KiB容量问题。', '',
             '## 使用与边界', '',
             '`self_fixed_network_top`设`PW4=1`启用优化版，`PW4=0`保留旧版对照（默认0）；六图runner用`--pw4`选择。该选项是编译参数。', '',
             '加载和计算尚未在同一引擎内重叠，缓存输入跨输出通道复用、权重跨四个位置复用；四套K1可跨图同时工作。边界块会降低通路利用率。', '',
             '小数据不等于完整六图全网PASS，也不能据此将以前8.98秒直接按比例换算。32MiB实验SRAM、合成测试图、诊断量化；不代表上板容量、识别准确率、CPU/UART或层内条带输入。', '',
             '[设计及复现](../../docs/self_pw4_design.md) · [机器可读对照](comparison.json)', '',
             '## 原始证据', '']
    for key, path in paths.items():
        text.append(f"- {key}: `{path.relative_to(ROOT).as_posix()}`；[结果副本](evidence/{key}/result.json)")
    text += ['', f"小回归输出SHA256：`{manifest['final_expected_sha256']}`。已核对当前源码、数据、结果文件和报告哈希。", '']
    (out/'README.md').write_text('\n'.join(text), encoding='utf-8')
    print('PASS', out)

if __name__ == '__main__':
    main()
