"""Package actual independent RTL test results and a deduplicated GTKWave view."""
from pathlib import Path
import argparse, hashlib, json, shutil
from plot_waveforms import read_vcd

ROOT=Path(__file__).resolve().parents[1]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('run',type=Path); args=ap.parse_args()
    source=args.run.resolve(); result=json.loads((source/'result.json').read_text())
    assert result['status'] in {'PASS','PARTIAL_FAILURE'}
    out=ROOT/'deliverables/vicuna2_small'; out.mkdir(exist_ok=True)
    rows=[]; evidence={}; views={}
    names=['clk_i','rst_ni','mem_ireq_o','mem_iaddr_o','mem_irvalid_i',
           'csr_vl_o','pend_vreg_wr_map_o','vect_pending_load','vect_pending_store',
           'vcore_result_valid','vcore_result_ready','mem_req_o[0]','mem_we_o[0]',
           'mem_addr_o[0]','mem_be_o[0]','mem_wdata_o[0]','mem_rvalid_i[0]',
           'mem_rdata_i[0]','mem_err_i[0]']
    for case in result['tests']:
        name=case['name']; src=source/name; dst=out/name; dst.mkdir(exist_ok=True)
        for item in src.iterdir():
            if item.is_file(): shutil.copyfile(item,dst/item.name)
        if case['status']=='PASS':
            assert (dst/'actual.bin').read_bytes()==(dst/'expected.bin').read_bytes()
        wave=dst/'wave.vcd'; cycles=None
        if wave.exists():
            v=read_vcd(wave); selected=[]; used=set()
            for name_hint in names:
                matches=[s for p,s in v.signals.items() if p.rsplit('.',1)[-1]==name_hint]
                if not matches: continue
                sig=min(matches,key=lambda s:(len(s.path.split('.')),len(s.path)))
                if sig.code not in used: selected.append(sig); used.add(sig.code)
            byname={s.path.rsplit('.',1)[-1]:s for s in selected}
            assert {'clk_i','rst_ni','mem_req_o[0]','mem_we_o[0]'}<=byname.keys()
            reset=next(t for t,b in byname['rst_ni'].events if b=='1')
            cycles=sum(b=='1' and t>reset for t,b in byname['clk_i'].events)
            evidence[name]={'post_reset_clock_rising_edges':cycles,
                'wave_sha256':hashlib.sha256(wave.read_bytes()).hexdigest(),
                'signals':[s.path for s in selected]}
            lines=['[*] Actual independent Vicuna RTL simulation; original driver timestamps',
                   f'[dumpfile] "{wave.as_posix()}"','[size] 1600 950','[signals_width] 290',
                   '*-20 -1 '+' '.join(['-1']*26)]
            for sig in selected:
                base=sig.path.rsplit('.',1)[-1]
                color=0 if base in {'clk_i','rst_ni'} else 6 if base.startswith('mem_i') else 3 if base.startswith(('csr_','pend_','vect_','vcore_')) else 4
                lines.extend(['@'+('28' if sig.width==1 else '22'),f'[color] {color}',sig.path+(f'[{sig.width-1}:0]' if sig.width>1 else '')])
            (dst/'controls.gtkw').write_text('\n'.join(lines)+'\n',encoding='utf-8')
            views[name]=len(selected)
        rows.append(f"| {name} | {case['status']} | {case.get('wall_seconds',0):.3f} | {cycles if cycles is not None else '—'} |")
    shutil.copyfile(source/'result.json',out/'result.json')
    for log in ['configure.log','compile.log','tests.log']:
        if (source/log).exists(): shutil.copyfile(source/log,out/log)
    (out/'wave_evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    view='fp32_prelu' if 'fp32_prelu' in views else next(iter(views))
    (out/'open_gtkwave.cmd').write_text('@echo off\r\nstart "" "%~dp0..\\..\\tools\\gtkwave\\portable\\gtkwave64\\bin\\gtkwave.exe" "%~dp0'+view+'\\wave.vcd" "%~dp0'+view+'\\controls.gtkw"\r\n',encoding='ascii')
    passed=sum(t['status']=='PASS' for t in result['tests'])
    text=f'''# Vicuna 2 小规模 RTL 验证结果

本次状态：**{result['status']}，{passed}/{len(result['tests'])} 项通过**。
来源：`{source.relative_to(ROOT).as_posix()}`。每项实际 SRAM 输出与独立 Python 参考逐字节比对。

使用同一个 CV32E40X 小控制核 + Vicuna 2 硬件模型，切换程序完成不同运算。
这是未来 CNN 内可编程算子区域的独立验证，尚未接入现有主 CPU、NVDLA、DATASRAM 或 UART。
现有主 CPU 仍保持原来的 RV32I 实现。

## 实测结果

| 程序 | 结果 | 仿真进程耗时/秒 | 复位释放后实际时钟上升沿数 |
|---|---|---:|---:|
{chr(10).join(rows)}

本轮配置耗时 {result.get('configure_seconds',0):.2f} 秒，模型编译耗时 {result.get('compile_seconds',0):.2f} 秒。
复用来源：{result.get('reused_model_from','本轮构建')}；原始模型编译耗时 {result.get('original_compile_seconds',result.get('compile_seconds',0)):.2f} 秒。
以上编译耗时仅对应本次成功构建调用，不包括此前配置排错、下载和工具准备。
程序运行耗时包含进程启动和波形写盘，不是硬件耗时。
时钟数包含启动、循环控制、访存、运算和结束等待，不是单条算子的延迟。
若假设时钟为 100 MHz，可将时钟数乘以 10 ns 估算该段硬件时间；本次未进行综合或频率收敛验证。

每项处理 19 个输入元素，覆盖正负数、零及向量尾部；点积输出一个数。
FP16/FP32 测试使用可精确表示的有限数，不等于完整 IEEE 754 一致性验证。
INT32 PReLU 以算术右移实现系数 1/4，输入为 4 的倍数。

## 本次发现的兼容限制

第一轮诊断保存在 `build/runs/20261013_203617_vicuna_small`，没有标为通过。
本次九项 PASS 是下列程序适配后的结果，硬件模型没有重新编译或修改：

- 默认封装将 `fencei_flush_ack_i` 固定为 0，控制核又把 FENCE 按 FENCE.I 处理，
  因而使用 FENCE 会等待不结束。本次无缓存测试用标量读操作收尾；封装会在向量写入未完成时
  阻止该标量访问，所以实际检查仍等待写回完成。完整 SoC 接入需要补齐刷新应答。
- 这版向量译码器缺少 `vmflt.vv` 的实现，直接使用的 FP32 PReLU 程序超时。
  当前程序用整数比较读取 FP32 位模式的符号，再做浮点乘法和掩码选择，实现有限数域 PReLU。
  这不代表浮点比较指令已经支持，也未验证 NaN 等特殊数行为。

## 如何查看波形

运行 `open_gtkwave.cmd` 查看 `{view}`，或打开各测试目录的 `wave.vcd` 和 `controls.gtkw`。
每个会话按时钟复位、取指、向量状态、数据存储接口排列，同一信号标识只展示一次。
各信号组使用不同颜色。

**原始 VCD 横轴是上游驱动的采样时间戳，不能直接按显示的 ps/ns 理解为真实硬件速度。**
驱动通常在每个执行周期记录三次采样；本表通过实际 `clk_i` 上升沿计数。

| 信号 | 方向与含义 |
|---|---|
| clk_i / rst_ni | 测试平台 → 控制核及向量单元：时钟、低有效复位 |
| mem_ireq_o / mem_iaddr_o | 控制核 → 指令存储模型：取指请求、地址 |
| mem_irvalid_i | 指令存储模型 → 控制核：指令返回有效 |
| csr_vl_o | 向量单元状态：当前一批有效元素数，最后一批会减小 |
| pend_vreg_wr_map_o | 向量单元 → 控制/观测：等待写入的向量寄存器位图；不等同于所有 PE 忙 |
| vect_pending_load / vect_pending_store | 向量单元 → 集成控制：尚未完成的向量读/写 |
| vcore_result_valid / vcore_result_ready | 向量结果接口 → 小控制核及返回握手；不是每个数据元素写 SRAM 的脉冲 |
| mem_req_o[0] / mem_we_o[0] | 集成核 → 数据存储模型：请求；we=0 读、we=1 写，须和 req 一起看 |
| mem_addr_o[0] / mem_be_o[0] | 集成核 → 数据存储模型：字节地址和四个字节的写使能 |
| mem_wdata_o[0] | 集成核 → 数据存储模型：32 位写数据 |
| mem_rvalid_i[0] / mem_rdata_i[0] | 数据存储模型 → 集成核：完成/返回有效与读数据 |
| mem_err_i[0] | 数据存储模型 → 集成核：访问错误 |

输入位于 0x2000 起的资料区；最终输出位于 0x4000 起。
观察 `mem_req_o[0]=1`、`mem_we_o[0]=1` 且地址进入 0x4000 区，即可定位结果写回。
随后向 0x0400 写零是程序的结束通知，不是算子输出。
真正的正确性依据是 `actual.bin` 与 `expected.bin` 相等，不能仅凭结束通知认定通过。

各目录保留实际汇编、ELF、输入镜像、存储转储、日志、VCD、逐项结果；总结果记录工具链和模型哈希。
`wave_evidence.json` 保存波形哈希、时钟计数和展示信号清单。

## 后续接入工作

还需实现主 CPU 的任务寄存器、内部程序加载/启动、共享 SRAM 仲裁、完成/故障通知，
以及 NVDLA 量化结果与向量程序的数据格式约定。本次通过不代表这些系统接口已经完成。
完整配置及固定源码版本见 `../../docs/vicuna2_small_validation.md`。
'''
    (out/'README.md').write_text(text,encoding='utf-8')
    print(json.dumps({'out':str(out),'status':result['status'],'views':views},ensure_ascii=False))

if __name__=='__main__': main()
