import hashlib,json
from pathlib import Path
from datetime import datetime
ROOT=Path('D:/code/FPGA1/cpu_control (2)/cpu_control')
OUT=ROOT/'deliverables/cnn_pool23_resource_audit'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    runs={}
    for d in sorted((ROOT/'build/runs').glob('20261025_*_pool_resources_*')):
        j=json.loads((d/'result.json').read_text(encoding='utf-8'));runs[j['component']]=(d,j)
    required=['full','post','add','dw7','pad','fabric','dispatch','leases','results','programmer']
    assert all(k in runs and runs[k][1]['status']!='RUNNING' for k in required)
    old={'k3':'20261025_155929_013040_self_cnn_synth','k1':'20261024_012253_161051_self_cnn_synth'}
    for k,v in old.items():
        d=ROOT/'build/runs'/v;j=json.loads((d/'result.json').read_text());assert j['status']=='PASS'
        p='rtl/cnn_self/'+('self_conv_spatial4_engine.sv' if k=='k3' else 'self_pw8_engine.sv')
        assert j['sources_sha256'][p]==sha(ROOT/p)
        runs[k]=(d,j)
    for k in required:
        assert runs[k][1]['sources_unchanged']
        for p,v in runs[k][1]['source_sha256'].items():assert sha(ROOT/p)==v,p
    order=[('k3','3×3 / DW3卷积',4),('k1','1×1 PW8卷积',12),('post','后处理（GROUP_BYTES=16）',4),('add','残差Add（GROUP_BYTES=16）',1),('dw7','DW7（8通道）',1),('pad','补边Pad',1),('fabric','4-bank / 23客户端存储仲裁',1),('dispatch','任务调度器（2048项）',1),('leases','缓冲区生命周期管理（60槽）',1),('results','结果交接（60槽）',1),('programmer','固定网络模板展开（512步）',1)]
    keys=['Slice LUTs','Slice Registers','Block RAM Tile','DSPs'];total=[0]*4;ops=[0]*4;missing=[];rows=[];evidence=[]
    for key,label,n in order:
        d,j=runs[key];ok=j['status']=='PASS' and all(x in j.get('utilization',{}) for x in keys)
        v=[j['utilization'][x]['used']*n for x in keys] if ok else None
        if v:
            total=[a+b for a,b in zip(total,v)]
            if key in ('k3','k1','post','add','dw7','pad'):ops=[a+b for a,b in zip(ops,v)]
        else:missing.append(label)
        row=dict(component=key,label=label,instances=n,status=j['status'],totals=v,run=str(d),errors=j.get('errors',[]));rows.append(row)
        evidence.append(dict(component=key,result=str(d/'result.json'),result_sha256=sha(d/'result.json'),report_sha256=sha(d/'utilization.rpt') if (d/'utilization.rpt').exists() else None))
    OUT.mkdir(parents=True,exist_ok=True)
    summary=dict(created=datetime.now().isoformat(),measurement='Sequential OOC component synthesis; sum is NOT a whole-top synthesis result',part='xc7z020clg484-1',full_synthesis_status=runs['full'][1]['status'],configuration=runs['full'][1]['configuration'],resources_order=keys,rows=rows,known_component_sum=total,operator_pool_sum=ops,missing_components=missing,shared_sram_bytes=67108864,shared_sram_included=False,cpu_imem_uart_included=False,place_route_performed=False,evidence=evidence)
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    def fmt(v):return f'{v:,.0f}' if v==int(v) else f'{v:,.1f}'
    lines=['# 当前23算子CNN资源统计','',f'生成时间：{summary["created"]}。Vivado 2025.2，器件XC7Z020-CLG484-1，10ns时钟约束，仅综合，未布局布线。','',
    '## 统计范围','', '与完整15图PASS的参数一致：K3×4（每核4空间MAC）、K1×12（PW8）、Post×4、Add/DW7/Pad各1，15图片上下文、2048任务容量、60缓冲槽。复用卷积单核报告前已核对当前源文件哈希；其余模块此次逐个综合。未修改功能RTL或重新跑全网仿真。','',
    '整体顶层为self_fixed_network_top。第一次整体综合触发电脑可用物理内存低于1.5GiB的保护，终止该任务及其子进程，状态MEMORY_GUARD，不是整体综合PASS。随后逐模块统计。**下表是独立综合结果按实例数相加，不能当作整体布局布线的精确数值。** 顶层常量传播、端口裁剪及跨层优化会改变数量；保留的调试计数器也计入单核。','',
    '共享64MiB SRAM仅在综合临时副本中把datasram_tdp_bank存储体标为黑盒，保留原23客户端仲裁、地址宽度和接口。算子内部RAM照常计入。没有把64MiB偷偷缩小成片内RAM，也没有实现DDR控制器。当前已验证入口不含CPU、IMEM、UART、板级时钟；仓库旧SoC入口没有接入这个23算子顶层，不能冒充整机资源。','',
    '## 完整模块清单','', '| 模块 | 数量 | LUT合计 | FF合计 | BRAM Tile合计 | DSP合计 | 结果 |','|---|---:|---:|---:|---:|---:|---|']
    for row in rows:
        vals=' | '.join(fmt(x) for x in row['totals']) if row['totals'] else '未取得 | 未取得 | 未取得 | 未取得'
        lines.append(f'| {row["label"]} | {row["instances"]} | {vals} | {row["status"]} |')
    lines+=['| **已测模块算术合计** | — | '+' | '.join(fmt(x) for x in total)+' | 非整体综合总量 |','| **其中已测算子小计** | — | '+' | '.join(fmt(x) for x in ops)+' | 未完成算子不计入 |','| **XC7Z020容量** | — | 53,200 | 106,400 | 140 | 220 | 器件报告 |','',
    'BRAM Tile按36Kb块等效计，0.5表示一个18Kb块。LUT、FF、BRAM、DSP是不同资源，不能彼此直接相加。', '',
    '状态说明：PASS仅表示该模块综合和报告生成完成，不代表整机可放置或10ns时序通过；MEMORY_GUARD表示电脑可用物理内存低于1.5GiB而中止，不是FPGA资源超限判定；TIMEOUT表示480秒内未完成；FAIL表示工具给出具体综合错误。超时/保护时终止该运行的进程树，没有把未完成报告作为成功数值。','',
    '## 当前还不能给出的数字','', '未完成模块：'+('、'.join(missing) if missing else '分模块均已完成；仍缺整体综合结果')+'。这些项不能填0。上述已测合计不是全SoC总量，也不证明100MHz上板能过时序。','',
    '## 大任务容量的额外代价','',
    '以下是源码声明容量，不是最终映射LUT/FF数量：','',
    '| 表/数组 | 当前规模 | 声明容量 |','|---|---:|---:|',
    '| leases.hold任务保持表 | 2048×2048 bit | 512 KiB |',
    '| leases.pending活动槽保持掩码 | 60×2048 bit | 15 KiB（122,880 bit） |',
    '| dispatch.commands | 2048×512 bit | 128 KiB |',
    '| fixed_program.cmds | 512×512 bit | 32 KiB |',
    '| fixed_program.holds | 512×512 bit | 32 KiB |','',
    '这批设计为有限多图仿真保留了较大的可编程任务表。异步读取、宽掩码和并行比较可能映射成分布式RAM、寄存器和大量选择逻辑，不能假设会自动成为紧凑BRAM。尤其pending还逐槽并行检查整个任务完成掩码。进一步优化应优先考虑稀疏依赖编号/消费者计数、较小循环任务窗口、同步BRAM任务表，而不是直接复制更多算子；这些改动本次没有实施。','',
    '64MiB实验共享存储与器件全部140个36Kb块的630KiB原始容量相差约104倍；630KiB还包含奇偶位，且不能全部留给共享存储。现有实验布局需外部存储及控制器，或重新规划片内分块/复用容量，不能据本表宣称直接上板。','',
    '## 可追溯报告','']
    for key,label,n in order:
        d,j=runs[key];lines.append(f'- {label}：[result.json](<{(d/"result.json").as_posix()}>)'+(f'；[资源报告](<{(d/"utilization.rpt").as_posix()}>)' if (d/'utilization.rpt').exists() else f'；[日志](<{(d/"process.log").as_posix()}>)'))
        if j.get('errors'):lines.extend(['','```text',*j['errors'],'```',''])
    lines+=['',f'- 整体综合中止记录：[result.json](<{(runs["full"][0]/"result.json").as_posix()}>)。','- summary.json保存参数、每项资源、报告哈希与原始结果路径。']
    (OUT/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(dict(out=str(OUT),sum=total,operators=ops,missing=missing,rows=rows),ensure_ascii=False))
if __name__=='__main__':main()
