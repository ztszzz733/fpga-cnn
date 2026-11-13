"""Prepare and seal a portable CNN-to-storage handoff; never implements a MOVER."""
import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from cnn_tile_handoff_case import generate,verify,verify_unaligned_lanes

ROOT=Path(__file__).resolve().parents[1]
PRIOR=ROOT/'deliverables/self_cnn_ten_reduced_20261109_202945_990658_self_ten'
CACHE=ROOT.parent.parent/'.self_ten_pw8_build_frame_priority_dwcache_post16_k3par4_pool4_6_3'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def md(p,s):p.write_text(s,encoding='utf-8')

REPLY='''# CNN侧补充回复：非对齐分工与补交材料 v0.2

日期：2026-11-09。范围仅CNN侧。本文件记录CNN侧的接口选择与交付；跨方接口仍需存储侧回签。

## 1. 非对齐访问分工

CNN侧选择核对意见中的方案1：**由存储侧在DATA MOVER中实现本地非对齐访问。**

- CNN提供本地byte地址、有效字节长度和紧凑HWC布局，不为MOVER额外引入8字节对齐暂存区或打包/拆包拷贝。
- MOVER本地起址应允许任意byte地址，包括模8为1～7的起址；由存储侧实现字节选通、跨拍拼接及邻接字节保护。
- 长度允许正整数短尾；不能因为bytes不是8的倍数而覆盖有效区间之外的字节。
- 本包搬运清单中的DDR命令起址均为8字节对齐。任意DDR非对齐行首还需存储侧确认具体支持范围、窄访问/边界策略或明确错误返回；本包不把该项写成已经实现。
- 任何内部对齐扩大访问均不得越过PS保留区，写操作不得改坏邻接字节。PS物理地址与范围仍由对应责任方确认。

## 2. 随包实际补交

1. 8×8×32输出的K3→Post→Add样例：输入10×10×32，含输入、权重、Post/Add参数、残差及三阶段golden。
2. 4×4×2输入、2×2×2输出的短行样例：量化结果每行4字节，第二行本地起址模8为4；DDR行跨度8字节。它是CNN独立生成的新向量，**不是未收到的CPU小向量的逐字节复刻**。
3. 每例的manifest/layout/moves/tasks、SHA256、标准库整数参考及核对脚本。
4. 96组本地起址模8为0～7、双方向、不同短尾长度的期望测试向量，供存储侧接入真实MOVER测试台。
5. 当前16算子十图报告完整副本、输出、指标、图片/时间线、源码快照与源码哈希。
6. 两个新tile样例的现有K3/Post/Add真实RTL检查结果（见包首页状态）。

原8×8×32讨论稿的净数据量28032字节保持不变；实际任务包给输出区增加poison保护间隔。**实际地址以每例layout.json为准**，不再照抄讨论稿的连续偏移。保护间隔和未用上下文guard不属于有效特征数据。

## 3. 接口逐项补充

详见[C1接口补充](C1_CNN_MOVER接口建议_v0.2.md)。CNN侧建议接受单命令在途、src/dst/bytes/flags各32位、rsp_valid/rsp_ready消费响应；flags[0]取0为DDR→LOCAL、取1为LOCAL→DDR，其余位必须0。具体错误数值编码为CNN侧建议，待与存储侧统一；不声称已经双方冻结。

成功bytes_done=bytes；失败bytes_done=0只表示没有可向上游承诺的有效完成量，**不表示目标内存完全未改动**。错误后CNN停止依赖任务，故障缓冲在存储确认排空/恢复前不得复用。

## 4. 验证与未交付边界

样例软件检查、真实CNN/SRAM算术检查和新DDR/MOVER联合检查是三种不同状态，分别记录。本包不包含存储侧MOVER实现，不包含新的CNN→MOVER适配RTL，也没有实际PS DDR或EES331同顶层资源/时序验收。

请存储侧回签：本地任意byte起址能力、DDR侧起址规则、flags/错误编码、响应保持、超时排空/恢复状态；随后用本包清单做MOVER独立验证，再接CNN适配层。
'''

INTERFACE='''# C1：CNN→MOVER接口补充建议 v0.2

状态：CNN侧建议，待存储侧确认。这里没有映射CPU CSR，也没有分配PS物理地址。

## 1. 建议业务端口（相对于CNN）

| 信号 | 位宽 | 方向 | 语义 |
|---|---:|---|---|
| cmd_valid | 1 | 输出 | 命令有效，反压时全部字段保持稳定 |
| cmd_ready | 1 | 输入 | 与valid同拍时接收；单命令未完成/响应未消费前不接第二条 |
| cmd_src/cmd_dst/cmd_bytes/cmd_flags | 各32 | 输出 | byte地址/长度/控制；见下表 |
| rsp_valid | 1 | 输入 | 命令真正完成，或错误已确定；保持至ready消费 |
| rsp_ready | 1 | 输出 | CNN接收该完成响应 |
| rsp_status | 32 | 输入 | 成功/错误分类，编码建议见下 |
| rsp_bytes_done | 32 | 输入 | 成功等于请求长度；失败报告0，不提供可续传偏移 |

以上是业务接口，不是现有算子valid/ready/response本地存储端口。首版一条业务命令在途不禁止MOVER在该命令内部使用多个AXI突发/事务；完成必须覆盖命令全部事务。

| flags | src | dst |
|---|---|---|
| bit0=0：DDR_TO_LOCAL | DDR保留区byte偏移 | 本地RAM byte地址 |
| bit0=1：LOCAL_TO_DDR | 本地RAM byte地址 | DDR保留区byte偏移 |

flags[31:1]=0；未知控制位拒绝执行。layout/moves中的flags_proposed依据本候选编码，未代表存储RTL已经接受。

## 2. 对齐、长度与范围

- 本地允许任意byte起址，正整数bytes；每个字节精确复制，区间之外保持不变，由存储侧实现选通和拼接。
- 本包DDR起址均按8字节对齐，bytes可以不是8的倍数。任意DDR非对齐起址能力待另行回签，不能静默向下取整或越界扩大访问。
- 零长度建议报ERR_LENGTH，不访问内存；未知flags/非法范围也应在接受后返回明确错误，不进行静默截断。
- 使用足够宽的加法检查DDR offset+bytes、本地address+bytes以及configured_base+offset；范围右端是排他边界，不能32位回绕。
- DDR保留基址和长度由系统配置，样例的64KiB DDR镜像仅是测试范围，不是板上地址分配。

## 3. rsp_status建议编码

| 值 | 名称 | 含义 |
|---:|---|---|
| 0 | OK | 请求范围全部成功完成 |
| 1 | ERR_FLAGS | 未知flags |
| 2 | ERR_LENGTH | 零长度或非法长度 |
| 3 | ERR_RANGE | 越界、地址加法溢出 |
| 4 | ERR_DDR_ALIGNMENT | 当前版本不支持的DDR起址对齐 |
| 5 | ERR_AXI_READ | DDR读响应错误 |
| 6 | ERR_AXI_WRITE | DDR写响应错误 |
| 7 | ERR_TIMEOUT | 未在约定时间完成，仍需排空/恢复 |
| 8 | ERR_ABORTED | 由双方定义的停止/恢复流程结束任务 |
| 9 | ERR_FAULT_LOCKED | 存储仍处故障锁定，不能继续使用 |

编码仅供统一讨论。错误bytes_done=0不保证写操作原子性；可能存在部分数据已经修改。不得据此自动从0重试或释放原缓冲。

## 4. 完成、异常与复位

DDR→LOCAL成功需等本地RAM实际写入完成；LOCAL→DDR成功需等相关AXI B响应全部成功。本地算子done不代表DDR可见；所有下游消费者和必要写回完成后才能回收。

CNN在命令接受后等待其唯一响应；错误时锁存故障、停止新依赖任务并保护相关区域。超时不能伪造AXI事务取消。存储侧应明确排空/恢复状态的查询或握手方式（尚待定稿），未确认排空前不得复位后立即复用旧范围。旧响应必须与新一轮任务隔离。
'''

def prepare(out):
    assert not out.exists(),'preserve existing delivery'
    out.mkdir(parents=True);(out/'tools').mkdir();(out/'docs').mkdir();(out/'evidence').mkdir()
    for name in ('cnn_tile_handoff_case.py','run_tile_handoff_rtl.py','verify_cnn_storage_bundle.py'):shutil.copyfile(ROOT/'scripts'/name,out/'tools'/name)
    sig=read(CACHE/'signature.json');prior=read(PRIOR/'result.json')
    assert prior['status']=='PASS' and sig['signature']==prior['source_signature'] and sig['exe_sha256']==prior['exe_sha256']
    snapshot=out/'source_snapshot';snapshot.mkdir()
    for name,h in sig['signature']['sources'].items():
        assert sha(ROOT/name)==h,name
        dest=snapshot/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
    save(snapshot/'build_signature.json',sig)
    filelist=snapshot/'rtl/filelists/cnn_self_stream.f';filelist.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(ROOT/'rtl/filelists/cnn_self_stream.f',filelist)
    shutil.copytree(PRIOR,out/'evidence/ten_image_16_units')
    original=(ROOT/'docs/CNN_tile任务包与MOVER适配定义_补交说明_v0.1_2026-11-09.md').read_text(encoding='utf-8')
    original=original.replace('../deliverables/self_cnn_ten_reduced_20261109_202945_990658_self_ten/README.md','../evidence/ten_image_16_units/README.md').replace('../rtl/','../source_snapshot/rtl/')
    md(out/'docs/原讨论稿_v0.1.md','> 历史讨论稿：未生成任务包等表述为当时状态；本次交付进展请见v0.2回复及包首页。本副本仅重定位工程链接，原文内容保留。\n\n'+original)
    md(out/'docs/CNN侧补充回复_v0.2.md',REPLY);md(out/'docs/C1_CNN_MOVER接口建议_v0.2.md',INTERFACE)
    cases=out/'cases'
    generate(cases,'tile_8x8x32',10,10,32,32);generate(cases,'short_row_2x2x2',4,4,2,2)
    verify_unaligned_lanes(cases)
    results={p.name:verify(p) for p in cases.iterdir() if p.is_dir()}
    save(out/'software_validation.json',dict(status='PASS',cases=results,unaligned_vectors=96,
        scope='Software oracle/layout/byte-copy checks; no real MOVER verification'))
    for case in [p for p in cases.iterdir() if p.is_dir()]:
        m=read(case/'manifest.json');l=read(case/'layout.json');n=m['shape']['output_w']*m['shape']['out_channels']
        md(case/'README.md',f'''# {case.name}

确定性合成诊断向量，非真实模型准确率样例。形状与所有地址以layout.json为准。

- 净数据{m['payload_bytes']}字节；包含保护间隔和未用上下文guard的占用结束为0x{m['local_guarded_used_end']:X}，逻辑检查范围32KiB。
- 输出每行{n}字节；DDR输出行跨度{l['regions']['add_output']['ddr_row_stride']}字节；逐行命令见moves.csv。
- input/weights/params/residual为搬入数据，golden只作核对。local_initial全0xA5；ddr_initial结果区为0xD7。
- ddr_expected是完整DDR镜像期望，用于同时检查结果和邻接/行间padding保护。
- native_fixture仅供现有真实CNN/SRAM检查器：权重/参数/残差经实际SRAM A口预加载，输入经现有IO口写入，绕过了新MOVER/DDR。原RTL共享SRAM参数仍32MiB，32KiB只是本样例地址范围，不能当作新32KiB RAM已综合。

原生算子命令在tasks.json；逐通道五字参数及其零点/移位见layout.json，整数参考见tools中的脚本。所有文件哈希见manifest.json。
''')
    md(out/'README.md','''# CNN向存储侧补交材料 v0.2

请先看[分工与补充回复](docs/CNN侧补充回复_v0.2.md)和[C1接口建议](docs/C1_CNN_MOVER接口建议_v0.2.md)。

**CNN侧要求由存储侧MOVER处理本地非对齐byte访问；CNN保持紧凑HWC布局，不增加8字节对齐暂存拷贝。此为CNN侧回复，需存储侧回签。**

## 文件入口

- [主tile样例](cases/tile_8x8x32/README.md)：输入10×10×32，卷积→量化→Add输出8×8×32。
- [短行样例](cases/short_row_2x2x2/README.md)：输入4×4×2，输出2×2×2，每行4字节，第二行本地起址模8为4，DDR行跨度8字节。
- [96组非对齐期望向量](cases/unaligned_lane_vectors.json)：两个方向、8种本地byte lane、6种长度；供存储RTL接入，不是MOVER已验证结果。
- [已有16算子十图报告](evidence/ten_image_16_units/README.md)、[逐图交互图](evidence/ten_image_16_units/task_timeline/index.html)。完整副本包括原指标、输出、图表、来源哈希。
- source_snapshot保留当时算术RTL、完整测试台及哈希/编译参数；不含工具链和预训练大模型。

## 无第三方库的软件核对

在解压根目录执行：

```text
python tools/cnn_tile_handoff_case.py cases
```

脚本核对文件哈希、标量整数卷积/量化/Add、布局、搬运清单、完整DDR期望镜像和邻接字节。本地byte-copy是软件契约模型，不是存储MOVER RTL实现。golden不会预加载到native_fixture的结果区。

封包后可核对整个材料包（Python3.9或更新版本）：

```text
python tools/verify_cnn_storage_bundle.py .
```

## 真实算子RTL复核

本包复用已有16算子真实RTL测试台，配置十上下文但只激活一个tile，检查三个任务的每个写出字节、MAC数、响应排空、分配释放和保护区。它不覆盖新的MOVER或实际PS DDR。

Linux/WSL具备兼容Verilator和C++工具链时，可从源码重建：

```text
python3 tools/run_tile_handoff_rtl.py . --build
```

可用--verilator和--verilator-root指定工具链。若已有与build_signature.json中哈希完全匹配的可执行程序，也可使用--exe。为保留随包原始证据，脚本在已有evidence/tile_core_rtl时拒绝覆盖；复现请使用新的解压副本，先将该证据目录改名后执行。

## 当前未包含的验收

未提供存储侧MOVER RTL、CNN→新MOVER适配RTL、实际PS DDR验收或EES331同顶层资源/时序报告。当前已有独立算子/整网报告不能替代这些项目。旧十图报告中的原机器路径保留作来源记录；PNG和HTML可直接查看，GTKWave会话如含原路径需手动选择随包VCD。十图原始大数据和预训练模型未重复打包；完整网复跑仍需对应原数据，本包两个tile诊断向量则自包含。native stress是现有SRAM端口冲突/慢速读回压力，不等于AXI随机反压或错误覆盖。

最终状态和压缩包内哈希清单由封包检查生成。
''')
    save(out/'handoff_status.json',dict(status='PREPARED_NOT_SEALED',generated_at=datetime.now().isoformat(),
        mover_non_aligned_owner='Storage side; CNN-side selection pending storage ACK',software='PASS',
        mover_rtl='NOT_SUPPLIED_NOT_TESTED',cnn_mover_adapter='NOT_IMPLEMENTED',ps_ddr='NOT_TESTED',
        same_top_resources='NOT_AVAILABLE',historical_ten_image_report='COPIED_WITH_SOURCE_HASHES'))
    print(str(out),flush=True)

def seal(out):
    rtl=read(out/'evidence/tile_core_rtl/result.json');assert rtl['status']=='PASS' and len(rtl['scenarios'])==6
    for name,h in rtl['sources'].items():assert sha(out/'source_snapshot'/name)==h,name
    for case in [p for p in (out/'cases').iterdir() if p.is_dir()]:verify(case)
    broken=[]
    # Check our portable entry documents; the original evidence retains provenance paths.
    for doc in [out/'README.md',out/'docs/CNN侧补充回复_v0.2.md',out/'docs/原讨论稿_v0.1.md']:
        for link in re.findall(r'\]\(([^)]+)\)',doc.read_text(encoding='utf-8')):
            if not (doc.parent/link).exists():broken.append((str(doc),link))
    assert not broken,broken
    status=read(out/'handoff_status.json');status.update(status='SEALED',tile_core_rtl='PASS_6_SCENARIOS',sealed_at=datetime.now().isoformat())
    save(out/'handoff_status.json',status)
    text='\n## 本次封包验证\n\n两例各3种真实CNN/SRAM RTL场景全部PASS；主例逐场景检查12288输出字节、589824MAC，短行例检查48输出字节、144MAC。该检查绕过新MOVER。软件布局/整数参考/逐行复制检查PASS；96组非对齐向量已生成并由软件模型检查，等待存储RTL执行。\n\n'
    text+='|场景|周期|结果|\n|---|---:|---|\n'
    for name,v in rtl['scenarios'].items():text+=f"|{name}|{v['cycles']}|PASS|\n"
    p=out/'README.md';md(p,p.read_text(encoding='utf-8')+text)
    save(out/'package_validation.json',dict(status='PASS',software='PASS',real_cnn_sram_rtl_scenarios=6,
        mover_rtl='NOT_TESTED',ps_ddr='NOT_TESTED',new_adapter='NOT_IMPLEMENTED',source_hashes='PASS',portable_entry_links='PASS'))
    files={str(p.relative_to(out)).replace('\\','/'):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(out.rglob('*')) if p.is_file()}
    save(out/'MANIFEST.sha256.json',dict(format='sha256-per-file',files=files))
    archive=out.with_suffix('.zip');assert not archive.exists(),'preserve existing archive'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file():z.write(p,'CNN_storage_handoff_v0.2/'+str(p.relative_to(out)).replace('\\','/'))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for name,info in files.items():
            blob=z.read('CNN_storage_handoff_v0.2/'+name);assert len(blob)==info['bytes'] and hashlib.sha256(blob).hexdigest()==info['sha256'],name
    archive.with_suffix('.zip.sha256').write_text(sha(archive)+'  '+archive.name+'\n',encoding='ascii')
    print(json.dumps(dict(status='PASS',archive=str(archive),bytes=archive.stat().st_size,files=len(files)+1,sha256=sha(archive)),ensure_ascii=False),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path);ap.add_argument('--seal',type=Path);a=ap.parse_args()
    if a.seal:seal(a.seal.resolve())
    else:prepare(a.out.resolve() if a.out else ROOT/'deliverables'/('cnn_storage_handoff_'+datetime.now().strftime('%Y%m%d_%H%M%S')))
