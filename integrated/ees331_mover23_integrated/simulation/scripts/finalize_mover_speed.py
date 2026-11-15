"""Package verified MOVER speed changes without altering the previous bundle."""
from pathlib import Path
import json,csv,hashlib,shutil,difflib,zipfile
SIM=Path(__file__).resolve().parents[1];BASE=SIM.parent
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def local(s):return Path('D:/'+s[7:] if s.startswith('/mnt/d/') else s)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
b=read(SIM/'build/mover_speed_baseline.json');oldrun=Path(b['baseline_run']);old=read(oldrun/'result.json')
run=local(read(SIM/'build/mover_speed_soc_active.json')['run_dir']);r=read(run/'result.json')
synrun=local(read(SIM/'build/reduced_synth_active.json')['run_dir']);syn=read(synrun/'result.json')
assert r['status']==old['status']==syn['status']=='PASS'
for rec in (r,syn):
 for name,h in rec['sources'].items():assert sha(BASE/name)==h,'source changed: '+name
allowed={'storage_v2/rtl/data_mover.sv','simulation/tb/integration/ees331_axi_mover_model.hpp'}
osrc={n.replace('\\','/'):h for n,h in old['sources'].items()}
for name,h in r['sources'].items():
 key=name.replace('\\','/')
 if key in osrc and key not in allowed:assert h==osrc[key],key
for size in ('small','full'):
 assert r[size]['output_sha256']==old[size]['output_sha256']
 for key in ('jobs','checked_output_bytes','results','unit_starts','ddr_read_bytes','ddr_write_bytes'):
  assert r[size]['metrics'][key]==old[size]['metrics'][key],key
res=syn['resources'];assert res['Slice LUTs']<=53200 and res['Slice Registers']<=106400 and res['Block RAM Tile']<=140 and res['DSPs']<=220
def latency(p):return int(next(csv.DictReader((p/'full/output_timing.csv').open()))['latency_cycles'])
before,after=latency(oldrun),latency(run);assert after<before
profile=read(run/'full/recorded_performance_profile.json');prior=read(oldrun/'full/recorded_performance_profile.json')
assert profile['actual_conv_mac_fire_cycles']==prior['actual_conv_mac_fire_cycles']
assert sum(profile['mover_cycles'].values())==profile['window_cycles']==after
busy=lambda p:p['window_cycles']-p['mover_cycles']['IDLE']
compat=read(SIM/'build/mover_model_compat/result.json');assert compat['status']=='PASS'
assert compat['new_sha256']==sha(SIM/'tb/integration/ees331_axi_mover_model.hpp')
out=BASE/'deliverables/mover_speed_single_20261112';out.mkdir(parents=True,exist_ok=True)
for name in ('full_states','full_cpu_config','full_operator_detail'):
 assert 'PASS GTKWave 12-operator view' in (out/('validation_'+name+'.log')).read_text()
def copy(p,n):
 q=out/n;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q)
for tag,origin in [('before',Path(b['baseline_synth'])),('after',synrun)]:
 for name in ('result.json','utilization.rpt','hierarchy.rpt'):copy(origin/name,'evidence/synthesis_'+tag+'/'+name)
for tag,origin in [('before',oldrun),('after',run)]:
 copy(origin/'result.json','evidence/simulation_'+tag+'/result.json')
 for name in ('metrics.json','output_timing.csv','recorded_performance_profile.json'):copy(origin/'full'/name,'evidence/simulation_'+tag+'/'+name)
for name in ('20261112_220321_mover_speed_burst','20261112_221012_mover_speed_legacy','20261112_221011_reduced_pager'):
 for f in ('result.json','simulation.log'):copy(SIM/'build/runs'/name/f,'evidence/unit/'+name+'/'+f)
copy(SIM/'build/mover_model_compat/result.json','evidence/unit/model_compatibility.json')
for size in ('small','full'):
 for name in ('metrics.json','output_timing.csv','outputs.bin','events.csv'):copy(run/size/name,size+'_'+name)
 for p in (SIM/('build/fixtures/reduced_single_'+size)).iterdir():
  if p.is_file():copy(p,'source/simulation/build/fixtures/reduced_single_'+size+'/'+p.name)
sources=set(syn['sources'])|set(r['sources'])
for name in sources:copy(BASE/name,'source/'+name.replace('\\','/'))
for name in ('rtl/filelists/system_ees331_reduced.f','scripts/synth_reduced_bram.tcl','firmware/ees331_cpu/program.mem'):copy(BASE/name,'source/'+name)
for name in ('run_mover_speed_soc.py','run_reduced_synth.py','export_reduced_states.py','export_soc_states.cpp','profile_reduced_fst.py','profile_reduced_fst.cpp','prepare_reduced_views.py','run_mover_speed_checks.py','run_reduced_pager.py','check_mover_model_compat.py'):
 copy(SIM/'scripts'/name,'source/simulation/scripts/'+name)
for name in ('mover_speed_unit.cpp','mover_model_compat.cpp','reduced_pager_main.cpp'):
 copy(SIM/'tb/integration'/name,'source/simulation/tb/integration/'+name)
copy(BASE/'storage_v2/tb/data_mover.cpp','source/storage_v2/tb/data_mover.cpp')
copy(BASE/'storage_v2/scripts/prepare_vectors.py','source/storage_v2/scripts/prepare_vectors.py')
copy(BASE/'storage_v2/build/vectors/transfers.bin','source/storage_v2/build/vectors/transfers.bin')
patch=[]
for name in allowed:
 a=(Path(b['backup'])/name).read_text(encoding='utf-8-sig').splitlines(True);c=(BASE/name).read_text(encoding='utf-8-sig').splitlines(True)
 patch.extend(difflib.unified_diff(a,c,fromfile='a/'+name,tofile='b/'+name))
(out/'mover_speed_changes.patch').write_text(''.join(patch),encoding='utf-8')
summary={'status':'PASS','latency_before_cycles':before,'latency_after_cycles':after,'speedup':before/after,'latency_reduction_percent':100*(1-after/before),'reference_clock_hz':100000000,'mover_busy_before_cycles':busy(prior),'mover_busy_after_cycles':busy(profile),'mover_busy_speedup':busy(prior)/busy(profile),'resources':res,'full':r['full'],'run':str(run),'synthesis_run':str(synrun),'model_single_beat_exact_equivalence':True,'rtl_scope':'Only production data_mover.sv changed; CNN/CPU/order/sizes/392KiB unchanged'}
(out/'result.json').write_text(json.dumps(summary,indent=2)+'\n')
text=f'''# 搬运速度优化：一图完整网络验证通过

| 项目 | 优化前 | 优化后 |
|---|---:|---:|
| 图片提交到 DDR 结果可见 | {before} 周期 | {after} 周期 |
| 按 100 MHz 仿真参考换算 | {before/1e8:.6f} 秒 | {after/1e8:.6f} 秒 |
| 搬运器忙碌周期 | {busy(prior):.0f} | {busy(profile):.0f} |
| LUT | 49053 | {res['Slice LUTs']:.0f} |
| 寄存器 | 34978 | {res['Slice Registers']:.0f} |
| BRAM36 等效 | 137 | {res['Block RAM Tile']:g} |
| DSP | 33 | {res['DSPs']:.0f} |

单图延迟减少 **{summary['latency_reduction_percent']:.2f}%**，整机加速 **{summary['speedup']:.3f} 倍**。搬运器忙碌时间减少到原来的约 1/{summary['mover_busy_speedup']:.2f}；其余时间主要仍是 CNN 内部计算、共享 RAM 普通访问及算子间数据交换。以上为同一图像与模型下的仿真周期，不是上板实测频率或电脑运行时间。

## 修改范围

生产 RTL 仅修改 `storage_v2/rtl/data_mover.sv`：

1. 对齐数据按 32 位整字访问片上 RAM，非对齐首尾使用精确的 1／2 字节访问。
2. 收到上一字应答时，同一拍可提交下一字请求，利用 RAM 原有的一拍同步端口。
3. DDR 使用最多 16 拍的 AXI3 连续传输，128 字节缓存使用分布式存储，不增加 BRAM。跨 4 KiB 处拆分，尾部不越界读写。
4. 保留单命令、独立 AW/W、应答反压、原错误码、超时锁定、事务排空和恢复。DDR 命令起点仍按原接口要求 8 字节对齐；本地起点可非对齐。

16 拍上限及 4 KiB 边界依据 [Zynq-7000 AXI 事务约束](https://docs.amd.com/r/en-US/ug585-zynq-7000-SoC-TRM/AXI-Transaction-Considerations) 与 [AMD AXI 协议检查说明](https://docs.amd.com/r/en-US/pg101-axi-protocol-checker/AXI-Protocol-Checks-and-Descriptions)。

CNN 仍为 K3×2、K1×6、Post×2、Add×1、Pad×1，无 DW7，共享 RAM 392 KiB。任务模板、顺序配置方式、CPU 和 CNN 算法均保留；未进行算子融合。

## 正确性和公平比较

完整一图 **129 个任务、19365452 字节中间输出全部匹配**；最终 **7×7×128，共 6272 字节**，与优化前逐字节一致，SHA256 为 `8971dac0e8b2df60698e060a5e066b416213e8a71553161f66b037e613718485`。只读模型、缓冲区护栏、结果 fence 与批次复位检查通过。

独立检查覆盖 136 组原始搬运用例、416 组对齐／尾部／跨页组合、8 类非法命令、10 类错误条件与 3 类超时。页缓存的换页、写回、清理、取消排空和 burst 出错后的恢复通过。

外部 DDR 仿真模型扩展了 burst 支持。512 组单拍请求下，新旧模型的每周期 ready/valid/data/last/ID/response、随机状态、累计字节和最终内存完全一致。burst 首拍沿用原请求延迟，后续数据拍有随机间隙；性能比较基于此模型，不等于实际 DDR 控制器上的测量。

两版相同的 DDR 总读取 28649472 字节、写入 16259072 字节；卷积乘加活跃周期均为 33904896，说明加速来自数据通路，计算内容未减少。搬运前后完整状态占比见 evidence/ 下的 recorded_performance_profile.json。

## 波形

- `open_full.cmd`：优化后完整一图，CPU、CNN、缓存、MOVER 与全部 12 个算子状态。
- `open_full_cpu_config.cmd`：CPU 配置阶段独立小波形。
- `open_full_operator_detail.cmd`：首个 K1 任务开始后的 128 拍独立小波形。

完整文件加载较慢，局部文件打开更快。缩放过远会把密集状态变化挤成纯色；应放大读状态名称。结果取回后测试执行批次复位，任务计数会从 129 回到零。

## 代码与复现

`source/` 是验证过的生产源文件、固件、整机测试平台及输入/参考数据；`mover_speed_changes.patch` 对照本轮修改前备份。全套资源报告和检查结果见 evidence/。

本机在集成工程目录，用 WSL 运行 `simulation/scripts/run_mover_speed_soc.py`；用 Windows Python 运行 `simulation/scripts/run_reduced_synth.py 401408`。工具链路径沿用本机配置，移机需调整 Verilator、zlib 和 Vivado 路径。

资源数量在 Z7020 容量内，未做布局布线、时序收敛或上板测试。之前的压缩包和波形保留，当前工作树默认使用新搬运器。
'''
(out/'README.md').write_text(text,encoding='utf-8')
(BASE/'docs/mover_speed_20261112.md').write_text(text,encoding='utf-8')
files={str(p.relative_to(out)).replace('\\','/'):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='sha256.json'}
(out/'sha256.json').write_text(json.dumps(files,indent=2)+'\n')
target=out.with_suffix('.zip')
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as z:
 for p in out.rglob('*'):
  if p.is_file():z.write(p,str(p.relative_to(out.parent)))
print(json.dumps(summary,indent=2));print(target)
