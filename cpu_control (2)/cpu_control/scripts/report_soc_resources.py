"""Merge source-verified measurements; leave unavailable counts unavailable."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path('D:/code/FPGA1/cpu_control (2)/cpu_control')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    run=Path(sys.argv[1]);run=run if run.is_absolute() else ROOT/run
    j=json.loads((run/'result.json').read_text(encoding='utf-8'));assert j['status']!='RUNNING'
    component_runs={k:run for k in j['components']}
    extra=None
    if len(sys.argv)>2:
        extra=Path(sys.argv[2]);extra=extra if extra.is_absolute() else ROOT/extra
        clock=json.loads((extra/'result.json').read_text(encoding='utf-8'));assert clock['status']!='RUNNING'
        j['components']['clock']=clock['components']['clock'];component_runs['clock']=extra
    old=ROOT/'deliverables/cnn_pool23_resource_audit';cnn=json.loads((old/'summary.json').read_text(encoding='utf-8'))
    full_record=ROOT/'build/runs/20261025_174301_396810_pool_resources_full/result.json'
    full_sources=json.loads(full_record.read_text(encoding='utf-8'))['source_sha256']
    for k,s in full_sources.items():assert sha(ROOT/k)==s,k
    for e in cnn['evidence']:
        p=Path(e['result']);assert sha(p)==e['result_sha256'];v=json.loads(p.read_text(encoding='utf-8'))
        sources=v.get('source_sha256',v.get('sources_sha256',{}))
        primary={'k3':'rtl/cnn_self/self_conv_spatial4_engine.sv','k1':'rtl/cnn_self/self_pw8_engine.sv'}.get(e['component'])
        # Old standalone runs list extra unused files. Verify their measured
        # engine, while the current whole-CNN manifest is checked above.
        for k,s in sources.items():
            if k.endswith('.sv') and (primary is None or k==primary):assert sha(ROOT/k)==s,k
    keys=['Slice LUTs','Slice Registers','Block RAM Tile','DSPs'];cap=[53200,106400,140,220]
    rows=[dict(name='CNN已测22个算子',values=cnn['known_component_sum'],scope='不含DW7和任务管理/仲裁')]
    for key,label in [('cpu','CPU核'),('bridge','UART输入输出桥'),('clock','时钟直连/复位同步')]:
        r=j['components'][key];assert r['status']!='RUNNING'
        for k,v in r['source_sha256'].items():assert sha(ROOT/k)==v,k
        vals=[r['utilization'][k] for k in keys] if r['status']=='PASS' else None
        rows.append(dict(name=label,values=vals,status=r['status'],report=str(component_runs[key]/key/'utilization.rpt'),scope='现有模块默认参数独立OOC综合'))
    sums=[sum(r['values'][i] for r in rows if r['values']) for i in range(4)]
    percentages=[round(a/b*100,2) for a,b in zip(sums,cap)]
    out=ROOT/'deliverables'/('soc_resource_audit_'+run.name);out.mkdir(parents=True,exist_ok=True)
    result=dict(resources_order=keys,capacity=cap,rows=rows,known_component_sum=sums,known_component_sum_percent=percentages,integrated_soc_total_available=False,missing_cnn_components=cnn['missing_components'],shared_sram_bytes_in_full_simulation=67108864,imem_default_bytes=65536,legacy_soc_sram_default_bytes=262144,memory_capacity_budget=dict(imem_bram36=16,legacy_data_sram_bram36=64,cnn_known_bram36=112,combined=192,meaning='Common 1024x32-bit per RAMB36E1 capacity budget only, NOT a measured SoC utilization'),source_validation=True,new_run=str(run),old_audit=str(old),source_evidence_sha256={str(run/'result.json'):sha(run/'result.json'),str(old/'summary.json'):sha(old/'summary.json')})
    if extra:result['source_evidence_sha256'][str(extra/'result.json')]=sha(extra/'result.json')
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    def fmt(n):return f'{n:,.0f}' if n==int(n) else str(n)
    lines=['# CPU、CNN及外围资源统计','',
    '**尚未取得完整SoC的准确资源总数。** 本次尝试CPU核、UART桥、时钟/复位的独立综合，并核验旧CNN报告对应RTL仍未改变。下表为成功测得部分相加，不能视作整体综合值或严格资源下限。','',
    '| 部分 | LUT | 寄存器FF | BRAM Tile | DSP |','|---|---:|---:|---:|---:|']
    for r in rows:lines.append('| '+r['name']+' | '+(' | '.join(fmt(n) for n in r['values']) if r['values'] else '未取得 | 未取得 | 未取得 | 未取得')+' |')
    lines+=['| **已测部分合计** | '+' | '.join(fmt(n) for n in sums)+' |','| **占器件容量比例** | '+' | '.join(str(n)+'%' for n in percentages)+' |','| **XC7Z020-CLG484-1容量** | '+' | '.join(fmt(n) for n in cap)+' |','',
    'BRAM Tile按36Kb块等效计；两个18Kb块算一个Tile。不同类型资源分别比较，不互相相加。','',
    '## 实际统计范围','',
    'CNN采用此前完整15图验证的配置：K3×4（每核4空间MAC）、K1×12 PW8、Post×4、Add/DW7/Pad各1，15上下文、2048任务、60缓冲槽。已取得的22算子含K3/K1/Post/Add/Pad，未包括DW7。当前23算子CNN顶层仍是self_fixed_network_top，仓库face_soc_top接的是旧mobilefacenet_accelerator_top，不能综合旧SoC然后冒称本版整机。','',
    'CPU为rtl/soc/cpu_core.sv，包含cpu_control和合作方交付的完整cpu_datapath，不是只测控制器。各外部存储/MMIO端口保留可观测，避免CPU因常量指令被裁掉。采用模块默认地址范围SRAM_SIZE=256KiB，CPU数值不包含指令/数据存储本体。UART桥采用现有默认CLOCK_HZ=50MHz、BAUD=115200、MAX_PAYLOAD=256，包含桥内UART收发器。时钟模块只有直连和3级复位释放同步，不包含尚未设计的PLL。三者10ns约束独立OOC综合，未布局布线；这不等于整个系统已达100MHz。','',
    '## 尚未计入的部分','',
    '- DW7：旧综合480秒超时，未得到数值。','- CNN调度、存储仲裁、结果交接、模板展开：旧综合触发电脑内存保护，未得到数值。','- 缓冲区生命周期管理：旧综合明确失败，hold_reg4194304位及use_owners_reg67584位无法按当前写法推断RAM，且超过拆位规模限制。','- UART桥：本次触发电脑可用物理内存<1.5GiB保护，未取得资源报告。初次clock也在内存尚未释放时中止，原记录保留；内存释放后仅补测clock，结果见表。','- 指令存储器、共享数据存储器，以及未来可能需要的外存控制器、CPU到新CNN的配置适配、板级实现开销。','',
    '这些缺项没有按0处理。源哈希未变且阻塞已明确，本轮没有重复启动同样的大CNN综合，没有修改功能RTL，也没有重跑图片仿真。单独综合相加会与集成后的常量传播、端口裁剪、共享逻辑和物理优化结果不同。','',
    '## 存储容量预算','',
    '| 项目 | 容量 | 常用32位RAMB36映射预算 |','|---|---:|---:|',
    '| 旧SoC默认IMEM | 64KiB | 16 Tile |','| 旧SoC默认DATASRAM | 256KiB | 64 Tile |','| 已测CNN内部RAM | — | 112 Tile（实际模块测量相加） |','| 上述相加 | — | **192 Tile，器件只有140** |','',
    '16/64是按一个RAMB36E1存1024×32位有效数据的容量预算，并非这两个存储模块实际综合出的利用率。ROM内容、读写端口和推断方式会改变最终映射；空INIT_FILE可能被优化，不能把优化出的0当作可烧录64KiB指令存储的成本。','',
    '完整15图实验用的是64MiB共享SRAM，并非旧SoC的256KiB；64MiB不可能全部放进这块板的片内BRAM。本报告未把实验容量偷偷缩小后当成整机结果。若要上板，需要另定共享存储容量、分块/复用方案或外部存储方案；外存接口逻辑的资源尚未统计。','',
    '## 原始证据','',f'- [本次综合记录](<{(run/"result.json").as_posix()}>)',f'- [CNN各算子及未知项详细清单](<{(old/"README.md").as_posix()}>)']
    for r in rows[1:]:
        p=Path(r['report']);lines.append('- '+r['name']+('：[资源报告](<'+p.as_posix()+'>)' if p.exists() else '：[日志](<'+(p.parent/'process.log').as_posix()+'>)'))
    lines+=['', '本次综合耗时（电脑时间）：'+ '；'.join(k+' '+str(v.get('seconds'))+'秒' for k,v in j['components'].items())+'。','', 'summary.json保存数值、缺项、原始报告路径与证据哈希。']
    text='\n'.join(lines)+'\n';assert '\ufffd' not in text;(out/'README.md').write_text(text,encoding='utf-8')
    (out/'validation.json').write_text(json.dumps(dict(source_hashes_verified=True,integrated_total_claimed=False,files={p.name:sha(p) for p in [out/'README.md',out/'summary.json']}),indent=2),encoding='utf-8')
    print(json.dumps(dict(out=str(out),known_sum=sums,percentages=percentages,new_parts=rows[1:]),ensure_ascii=True))
if __name__=='__main__':main()
