"""Collect measured evidence only after full numerical and synthesis PASS."""
from pathlib import Path
import json,hashlib,shutil,zipfile,csv,difflib
SIM=Path(__file__).resolve().parents[1];BASE=SIM.parent
def local(s):return Path('D:/'+s[len('/mnt/d/'):] if s.startswith('/mnt/d/') else s)
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
run=local(read(SIM/'build/reduced_soc_active.json')['run_dir']);sim=read(run/'result.json')
synrun=local(read(SIM/'build/reduced_synth_active.json')['run_dir']);syn=read(synrun/'result.json')
baseline=SIM/'build/runs/20261112_200153_reduced_synth_32768'
assert sim['status']==syn['status']=='PASS'
assert syn['capacity']==401408
assert sim['full']['metrics']['jobs']==129 and sim['full']['metrics']['checked_output_bytes']==19365452
assert sim['full']['output_sha256']=='8971dac0e8b2df60698e060a5e066b416213e8a71553161f66b037e613718485'
prebank=SIM/'build/runs/20261112_201305_reduced_single_soc'
old=read(prebank/'result.json')
for size in ('small','full'):
 assert sim[size]==old[size],'RAM bank split changed complete numerical metrics or cycle counts'
 for name in ('events.csv','output_timing.csv'):
  assert (run/size/name).read_bytes()==(prebank/size/name).read_bytes(),'RAM bank split changed '+name
for r in (sim,syn):
 for name,digest in r['sources'].items():assert sha(BASE/name)==digest,'source changed since verification: '+name
resource=syn['resources'];assert resource['Slice LUTs']<=53200 and resource['Block RAM Tile']<=140
out=BASE/'deliverables/reduced_cnn_single_20261112';out.mkdir(parents=True,exist_ok=True)
def copy(p,target):
 q=out/target;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q)
for folder,origin in [('original23',BASE/'evidence/synth'),('reduced32k',baseline),('reduced392k',synrun)]:
 for f in ('utilization.rpt','hierarchy.rpt','result.json'):
  if (origin/f).exists():copy(origin/f,'evidence/'+folder+'/'+f)
for f in ('result.json',):copy(run/f,'evidence/simulation/'+f)
for name in ('20261112_195327_compact_k1','20261112_195424_compact_k3','20261112_195424_compact_post','20261112_203031_reduced_pager','20261112_203407_reduced_tile_ram'):
 for f in ('result.json','metrics.json','simulation.log'):
  p=SIM/'build/runs'/name/f
  if p.exists():copy(p,'evidence/unit/'+name+'/'+f)
for name in syn['sources']:copy(BASE/name,'source/'+name.replace('\\','/'))
for name in ('rtl/filelists/system_ees331_reduced.f','scripts/synth_reduced_bram.tcl','firmware/ees331_cpu/program.mem'):
 copy(BASE/name,'source/'+name)
for name in ('run_reduced_soc.py','export_reduced_states.py','export_reduced_states.cpp','prepare_reduced_views.py','run_reduced_synth.py','prepare_reduced_single.py','run_reduced_tile_ram.py','run_reduced_pager.py'):
 copy(SIM/'scripts'/name,'source/simulation/scripts/'+name)
for name in ('tb/ees331_soc_reduced_sim_top.sv','tb/integration/ees331_soc_reduced_main.cpp','tb/integration/ees331_axi_mover_model.hpp','tb/integration/reduced_tile_ram_main.cpp','tb/integration/reduced_pager_main.cpp','firmware/ees331_cpu/program_ram_probe.mem'):
 copy(SIM/name,'source/simulation/'+name)
for size in ('small','full'):
 for p in (SIM/('build/fixtures/reduced_single_'+size)).iterdir():
  if p.is_file():copy(p,'source/simulation/build/fixtures/reduced_single_'+size+'/'+p.name)
 copy(run/size/'soc_states.fst',size+'_states.fst')
 for f in ('metrics.json','events.csv','output_timing.csv','outputs.bin'):copy(run/size/f,size+'_'+f)
for script in ('export_soc_states.cpp',):copy(SIM/'scripts'/script,'source/simulation/scripts/'+script)
# Include the exact patch against the original backed-up production files.
before=read(SIM/'build/reduced_bram_source_backup.json');backup=Path(before['backup']);patch=[]
for name in before['changes']:
 a=(backup/name).read_text(encoding='utf-8-sig').splitlines(True);b=(BASE/name).read_text(encoding='utf-8-sig').splitlines(True)
 patch.extend(difflib.unified_diff(a,b,fromfile='a/'+name,tofile='b/'+name))
for name in ('rtl/cnn_self/compact_word_ram.sv','rtl/filelists/system_ees331_reduced.f'):
 patch.extend(difflib.unified_diff([], (BASE/name).read_text(encoding='utf-8-sig').splitlines(True),fromfile='/dev/null',tofile='b/'+name))
(out/'production_changes.patch').write_text(''.join(patch),encoding='utf-8')
timing=list(csv.DictReader((run/'full/output_timing.csv').open()))[0];cycles=int(timing['latency_cycles'])
table='| 版本 | LUT | 寄存器 | BRAM36 等效 | DSP | 共享 RAM |\n|---|---:|---:|---:|---:|---:|\n| 原 23 算子 | 71101 | 46017 | 137.5 | 61 | 32 KiB |\n| 缩减算子、未回填共享 RAM | 35326 | 25830 | 47 | 33 | 32 KiB |\n| 本次实际配置 | %d | %d | %s | %d | 392 KiB |\n'%(resource['Slice LUTs'],resource['Slice Registers'],resource['Block RAM Tile'],resource['DSPs'])
text='''# 本次结果：Post×2，缩减算子并扩容共享 BRAM

K3×2、K1×6、Post×2、Add×1、Pad×1，共 12 个；DW7 不实例化。生产默认共享 tile RAM 为 **392 KiB**，即原 32 KiB 加上回收的 360 KiB。

## 实际资源统计

'''+table+'''
统计为同型号 Z7020、Vivado 2025.2 综合后的整套 SoC。原版引用随集成包提供的真实综合报告；两份缩减版报告为本次运行。完整证据在 evidence/。回填共享缓存会增加页表逻辑，所以最终 LUT 以最后一行为准。资源数量检查通过，未进行布局布线或上板时序验证。

## 一图完整网络验证通过

129 个任务全部开始并完成；19365452 字节中间输出逐字节匹配独立整数参考。CPU 配置、图片提交、算子计算、tile RAM 换页、MOVER/DDR 读写、CPU fence、结果取回、缓冲区护栏与批次复位均经过实际 RTL。

按约定跳过原 DW7 及其关联 Post，末尾 PW 和 Post 保留原参数，在 7×7 上运算。最终为 UINT8/HWC、7×7×128，**6272 字节**，见 full_outputs.bin。此网络变体不等价于原 128 字节嵌入，不包含识别精度验证。

输出 SHA256：`8971dac0e8b2df60698e060a5e066b416213e8a71553161f66b037e613718485`。

图片提交到 DDR 结果可见的周期数：'''+str(cycles)+'''；按 100 MHz 绘图参考换算为 '''+('%.3f'%(cycles/100000))+''' ms。这是模拟周期换算，不是电脑仿真用时或板上实测频率。

PS GP0 和 DDR 是外部环境模型，软 CPU、CNN、片上 RAM、MOVER 为生产 RTL；执行内存只预装模型和填充值，中间参考结果不注入执行内存。

## 打开波形

- `open_full.cmd`：完整一图，CPU、CNN、内存和 MOVER，以及全部 12 个算子状态。
- `open_full_cpu_config.cmd`：复位到 CPU 配置及输入提交。
- `open_full_operator_detail.cmd`：首个 K1 任务开始后的 128 拍细节，可横移查看请求、等待、MAC 和输出。
- `open_small.cmd`：已完成的小规模 8 任务回归。

CPU 配置和算子细节是从完整记录按真实时间戳裁出的独立小文件，打开更快；完整状态 FST 约 96 MB，首次加载可能需要几十秒。

各行有 K3_0、K1_0、POST_0 等实例名称。`IDLE_NO_TASK` 表示没有持有任务；其他名称是该实例实际 FSM。拿到任务后可能在等数据，不能把整段有色区都当成乘加。缩放过远时密集变化会显示成纯色，请先打开细节视图或放大。

末尾任务计数回到零，是测试在取回结果后执行了批次复位；此前会达到 129。最终 RAM 分块前后的整机数值、周期、任务事件和结果时刻完全一致。

## 代码和复现

`source/` 包含本次生产 RTL 清单中的源码、CPU 固件、测试平台和一图数据；`production_changes.patch` 对照修改前备份。当前工作目录仍在 `D:/code/FPGA1/integrated/ees331_mover23_integrated`。入口 `rtl/soc/ees331/face_soc_ees331_mover_top.sv`，清单 `rtl/filelists/system_ees331_reduced.f`。

本机完整仿真脚本 `simulation/scripts/run_reduced_soc.py` 通过 WSL 运行，依赖已安装的 Verilator、C++ 编译器和 zlib。综合脚本 `simulation/scripts/run_reduced_synth.py 401408` 通过 Windows Python 调用 Vivado。移到其他机器时需要调整工具路径；Vivado 本身及工具链不包含在交付包中。
'''
(out/'README.md').write_text(text,encoding='utf-8')
copy(BASE/'docs/reduced_cnn_bram_20261112.md','修改说明.md')
summary={'status':'PASS','pool':sim['pool'],'shared_bytes':401408,'shared_increase_bytes':368640,'resources':resource,'full':sim['full'],'source_run':str(run),'synth_run':str(synrun),'latency_cycles':cycles,'ram_split_exact_cycles_metrics_events_equivalence':True}
(out/'result.json').write_text(json.dumps(summary,indent=2)+'\n')
files={str(p.relative_to(out)).replace('\\','/'):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='sha256.json'}
(out/'sha256.json').write_text(json.dumps(files,indent=2)+'\n')
target=out.with_suffix('.zip')
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as z:
 for p in out.rglob('*'):
  if p.is_file():z.write(p,str(p.relative_to(out.parent)))
print(json.dumps(summary,indent=2));print(target)
