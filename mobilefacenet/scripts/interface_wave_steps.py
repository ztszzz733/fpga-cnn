# -*- coding: utf-8 -*-
"""Turn the verified interface VCD into a chronological signal-value checklist."""
import csv
import json
import struct

from interface_wave import OUT, TB, DUT, QUEUE, ENG
from interface_wave_reference import edges, main as verify_reference, signed


def read_csv(name):
    with (OUT/name).open(encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def main():
    verify_reference()
    frames = list(edges(OUT/'interfaces.vcd'))
    by_time = {f[0]:f for f in frames}
    def value(frame, name, after=False):
        _,pre,post,names,widths = frame
        bits = (post if after else pre).get(names[name], 'x')
        return None if any(c in bits for c in 'xz') else int(bits,2)
    def at(ns, name, after=False): return value(by_time[ns],name,after)
    def find(name, lo=0, hi=10**9):
        return [f for f in frames if lo<=f[0]<hi and value(f,name)==1]
    def hx(v, digits=8): return f'0x{v:0{digits}X}'
    def pairs(ns, scope, fields, after=False):
        result=[]
        for name,fmt in fields:
            v=at(ns,scope+name,after)
            rendered='X' if v is None else hx(v) if fmt=='h' else str(signed(v,8)) if fmt=='s8' else str(signed(v,32)) if fmt=='s32' else str(v)
            result.append(f'`{name}={rendered}`')
        return '；'.join(result)
    rows=[]
    def row(ns,stage,signals,meaning,edge='沿前'):
        rows.append(dict(time_ns=ns,edge=edge,stage=stage,signals=signals,meaning=meaning))
    doc=['# 按执行步骤核对波形：这一步应该出现什么值', '',
         '**对应本次三任务 interfaces.vcd。按下面的时间定位，然后检查“信号应有值”这一列。**',
         '', '时间单位为 ns；若 GTKWave 显示 ps，表中时间乘 1000。例如 1175 ns 对应 1175000 ps。',
         '', '**沿前**：定位到该上升沿左侧，查看本次被接收的信号值。**沿后**：查看该沿更新后的值；可定位到该时间加 1 ns。不要用沿后已经切换的 FIFO 队首去比较本次出队任务。',
         '', '|文中前缀|GTKWave 中的层级|', '|---|---|',
         '|MMIO|dut.regs（mmio_addr/wdata 在 dut）|',
         '|队列|dut.task_queue|', '|读取器|dut.task_queue.reader|', '|FIFO|dut.task_queue.fifo|',
         '|控制器|dut.systolic_path.engine|', '|缓存|dut.systolic_path.engine.reads|',
         '|分块/阵列|dut.systolic_path.engine.tile|',
         '|输出|控制器的 raw/out_value；输出暂存器 output_store|',
         '', '只检查当前步骤有效的数据；没有有效标志时，地址和数据线保持旧值是正常的。下面的值已与独立参考计算核对。',
         '', '## 第一步：CPU 配置并启动队列']
    def table(items):
        return ['', '|时间 ns|查看位置|正在做什么|信号应有值|该步骤的含义|',
                '|---|---|---|---|---|']+[
            f"|{r['time_ns']}|{r['edge']}|{r['stage']}|{r['signals']}|{r['meaning']}|" for r in items]
    for ns,name,expected in [(45,'input_addr',0x3000),(65,'feature_size',3),(85,'op_type',15)]:
        row(ns,'CPU 写寄存器',pairs(ns,DUT,[('mmio_we','d'),('mmio_addr','h'),('mmio_wdata','h')]),'本上升沿接收 CPU 写入')
        assert at(ns,DUT+'regs.'+name,True)==expected
        row(ns,'寄存器更新',f'`{name}={hx(expected) if name=="input_addr" else expected}`','队列输入配置更新','沿后')
    ns=find(DUT+'start')[0][0]
    row(ns,'队列接受 START',pairs(ns,DUT,[('start','d'),('op','d')]),'启动的是整个任务队列')
    row(ns,'保存任务表范围',pairs(ns,QUEUE,[('queue_base','h'),('queue_end','h')],True),
        '任务表起始 0x3000，共 3×32 字节，结束边界 0x3060','沿后')
    doc+=table(rows)
    doc+=['','## 第二步：先读取三条任务，分别放入 FIFO', '',
          '本次先把三条任务全部取齐，再启动计算。每条任务由 8 个 32 位字组成。']
    descriptors=(OUT/'vectors/queue.bin').read_bytes()
    fields=['任务头','task_input','task_output','task_weight','task_bias','task_size','task_channels','task_param']
    reads=read_csv('read_expected.csv');fifo=read_csv('fifo_expected.csv')
    for task in range(3):
        doc+=['',f'### 取任务 {task}']
        section=[]
        starts=[f[0] for f in find(QUEUE+'reader.start') if value(f,QUEUE+'reader.base_address')==0x3000+task*32]
        ns=starts[0]
        row(ns,'启动读取器',f'读取器 `start=1`，`base_address={hx(0x3000+task*32)}`','准备读取这条任务');section.append(rows[-1])
        for j,r in enumerate(r for r in reads if r['kind']=='descriptor' and int(r['task'])==task):
            ns=int(r['time_ns'])
            row(ns,f'读取第 {j} 个字：{fields[j]}',
                f"读取器 `rsp_valid=1`，`rsp_data=0x{r['rsp_data']}`，`cmd_addr=0x{r['cmd_addr']}`",
                f'收进 descriptor[{j*32+31}:{j*32}]');section.append(rows[-1])
        entry=next(r for r in fifo if r['event']=='PUSH' and int(r['task'])==task);ns=int(entry['time_ns'])
        desc=f'{int.from_bytes(descriptors[task*32:(task+1)*32],"little"):064X}'
        row(ns,'完整任务入 FIFO',
            '`descriptor_valid=1`，FIFO `in_valid=1`、`in_ready=1`；`descriptor=in_data`，等于下方完整值',
            f"沿前 `level=buffered={entry['level_before']}`");section.append(rows[-1])
        row(ns,'FIFO 入队后',f"`level=buffered={entry['level_after']}`",'数量增加 1','沿后');section.append(rows[-1])
        doc+=table(section)+['','本次 descriptor / in_data 的完整 256 位值：','','```text',desc,'```']
    task_times=json.loads((OUT/'result.json').read_text())['tasks_timing']
    buffers=read_csv('buffer_expected.csv');tiles=read_csv('tile_expected.csv');sums=read_csv('sums_expected.csv');outputs=read_csv('output_expected.csv')
    for task,timing in enumerate(task_times):
        lo,hi=timing['start_ns'],timing['done_ns']+1
        op=['1×1 普通卷积','3×3 DW 卷积','3×3 普通卷积'][task]
        doc+=['',f'## 第 {task+3} 步：执行任务 {task}（{op}）']
        ns=lo;section=[]
        entry=next(r for r in fifo if r['event']=='POP' and int(r['task'])==task)
        words=struct.unpack_from('<8I',descriptors,task*32)
        row(ns,'FIFO 出队，同时启动计算',
            f"`head_valid=1`、`head_ready=1`、`exec_start=1`；`head_data=out_data=任务 {task} 的完整256位值`；`buffered={entry['level_before']}`",
            '此刻的队首就是本次执行任务');section.append(rows[-1])
        row(ns,'检查队列送出的配置',
            '；'.join(f'`task_{n}={v & 15 if n=="op" else hx(v)}`' for n,v in zip(
                ('op','input','output','weight','bias','size','channels','param'),words)),
            '这些值在本上升沿被卷积控制器锁存');section.append(rows[-1])
        for n,v in zip(('cop','cia','coa','cwa','cba','cfs','cch','clp'),words):
            assert at(ns,ENG+n,True)==(v & 15 if n=='cop' else v)
        row(ns,'任务已锁存，队首可切换',
            f"FIFO `level=buffered={entry['level_after']}`；控制器 `cia={hx(words[1])}`、`coa={hx(words[2])}`、`clp={hx(words[7])}`；`quant_shift={words[7]>>12 & 255}`",
            '后续 task_* 改变不会改变已经锁存的任务','沿后');section.append(rows[-1])
        doc+=table(section)
        doc+=['','### 加载过程：按时间检查首次偏置、权重和输入数据', '',
              '下面展开各类数据的第一次读取；同类后续数据重复相同握手流程，全部写缓冲时刻见文末逐步明细。']
        detail=[]
        for kind,reqstate in [('bias',2),('weight',4),('input',6)]:
            req=next(f for f in frames if lo<=f[0]<hi and value(f,ENG+'state')==reqstate and value(f,ENG+'reads.req_valid')==1 and value(f,ENG+'reads.req_ready')==1)
            reqns=req[0]
            response=next(r for r in reads if r['kind']=='cache_response' and int(r['task'])==task and int(r['time_ns'])>reqns)
            end=int(response['time_ns']);address=at(reqns,ENG+'read_address')
            label={'bias':'偏置','weight':'权重','input':'输入'}[kind]
            row(reqns,'请求读取'+label,pairs(reqns,ENG,[('read_address','h')])+'；缓存 '+pairs(reqns,ENG+'reads.',[('req_addr','h'),('req_valid','d'),('req_ready','d'),('req_byte','d'),('req_bank','d')]),'控制器把字节地址交给缓存');detail.append(rows[-1])
            for f in frames:
                if not reqns<=f[0]<=end:continue
                ns=f[0]
                if value(f,ENG+'reads.cmd_valid')==1 and value(f,ENG+'reads.cmd_ready')==1:
                    row(ns,'缓存未命中，向 RAM 取整字','缓存 '+pairs(ns,ENG+'reads.',[('cmd_valid','d'),('cmd_ready','d'),('cmd_addr','h')]),'cmd_addr 按 4 字节对齐');detail.append(rows[-1])
                if value(f,ENG+'reads.rsp_valid')==1:
                    row(ns,'RAM 整字返回','缓存 '+pairs(ns,ENG+'reads.',[('rsp_valid','d'),('rsp_data','h')]),'这是 RAM 返回的完整 32 位整字');detail.append(rows[-1])
            b=next(r for r in buffers if int(r['time_ns'])==end and r['kind']==kind)
            signal='wr_bias' if kind=='bias' else 'wr_value'
            row(end,label+'数据写进缓冲',f"缓存 `response_valid=1`、`response_data=0x{response['response_data']}`；"+
                pairs(end,ENG,[('a_we','d'),('b_we','d'),('bias_we','d')])+f"；`wr_row={b['wr_row']}`、`wr_col={b['wr_col']}`、`wr_k={b['wr_k']}`；`{signal}={b['expected_signed']}`",
                '本上升沿写入分块缓冲');detail.append(rows[-1])
        pad=next((f for f in frames if lo<=f[0]<hi and value(f,ENG+'b_we')==1 and value(f,ENG+'padding')==1),None)
        if pad:
            ns=pad[0];row(ns,'输入窗口越界，直接补零',pairs(ns,ENG,[('padding','d'),('read_request','d'),('b_we','d')])+'；分块 '+pairs(ns,ENG+'tile.',[('wr_row','d'),('wr_col','d'),('wr_k','d'),('wr_value','s8')]),'此次不请求 RAM，直接写零');detail.append(rows[-1])
        if task==0:
            # First adjacent weight reuses the already cached aligned word.
            ns=1425
            row(ns,'相邻权重命中缓存',pairs(ns,ENG+'reads.',[('cmd_valid','d'),('response_valid','d'),('response_data','h')])+'；`a_we=1`、`wr_k=1`、`wr_value=-1`','无需再次发出 RAM 读取，直接使用上次整字中的下一个字节');detail.append(rows[-1])
        doc+=table(sorted(detail,key=lambda r:r['time_ns']))
        doc+=['','### 启动每一块计算，并检查本块完成值', '',
              '下面按空间块、累加块列出。sums 只检查当前 nr×nc 有效区域；中间累加块应为部分和。']
        for block in (r for r in tiles if int(r['task'])==task):
            section=[];ns=int(block['start_ns']);done=int(block['done_ns'])
            row(ns,'启动当前分块',pairs(ns,ENG,[('mb','d'),('nb','d'),('kb','d'),('nr','d'),('nc','d'),('nk','d')])+'；分块 '+pairs(ns,ENG+'tile.',[('start','d'),('accumulate','d'),('dw','d')]),'nr=有效行数，nc=有效列数，nk=本块累加项数');section.append(rows[-1])
            relevant=[r for r in sums if int(r['time_ns'])==done]
            values='；'.join(f"PE({r['row']},{r['col']})={r['expected_signed']}" for r in relevant)
            row(done,'当前分块完成','`tile.done=1`；有效 `sums`：'+values,
                '每个 PE 占 32 位；PE(r,c) 对应 sums[(r×8+c)×32 +: 32]');section.append(rows[-1])
            doc+=table(section)
        doc+=['','### 结果选择、量化与写回', '',
              '每行分两拍看：先在“量化采样”看 row/col/raw/shift，再在“写回采样”看 out_value/output_address。结果寄存器在量化采样沿后更新。', '',
              '|量化采样 ns（沿前）|写回采样 ns（沿前）|row|col|raw 应为|shift 应为|out_value 应为（十进制 / hex）|output_address 应为|',
              '|---|---|---|---|---|---|---|---|']
        for r in (r for r in outputs if int(r['task'])==task):
            ns=int(r['time_ns'])
            qns=max(f[0] for f in frames if lo<=f[0]<ns and value(f,ENG+'state')==10)
            doc.append(f"|{qns}|{ns}|{r['row']}|{r['col']}|{r['raw']}|{r['shift']}|{r['out_value_signed']} / 0x{r['out_value_hex']}|0x{r['output_address']}|")
            row(qns,'选择结果并量化',f"`row={r['row']}`、`col={r['col']}`、`raw={r['raw']}`、`quant_shift={r['shift']}`、`output_store.we=1`",'沿后 out_value 更新')
            row(ns,'提交结果写回',f"`cmd_valid=1`、`cmd_write=1`、`cmd_ready=1`、`out_value={r['out_value_signed']}`、`output_address=0x{r['output_address']}`",'后续 RAM 接口完成实际写入')
        ns=timing['done_ns'];section=[]
        row(ns,'当前任务完成',pairs(ns,DUT,[('exec_done','d'),('queue_completed','d')]),'exec_done 表示单个任务完成；completed 要等队列收尾后增加');section.append(rows[-1])
        increment=next(f for f in frames if f[0]>=ns and value(f,DUT+'queue_completed',True)==task+1)
        t=increment[0]
        row(t,'已完成数量增加',f'`completed=queue_completed={task+1}`','此后可分发下一条任务，或结束队列','沿后');section.append(rows[-1])
        doc+=table(section)
    ns=next(f[0] for f in frames if value(f,DUT+'regs.done_sticky',True)==1)
    section=[]
    row(ns,'全部任务结束',pairs(ns,DUT+'regs.',[('done_sticky','d'),('error_sticky','d')],True)+'；'+pairs(ns,DUT,[('queue_completed','d'),('queue_fetched','d'),('queue_buffered','d')],True),
        'DONE=1，ERROR=0，已完成3条、已取回3条、FIFO为空','沿后');section.append(rows[-1])
    doc+=['','## 第六步：整队列结束']+table(section)
    # Chronological appendix: every actual buffer write, rather than just first examples.
    appendix=['# 每次缓冲写入：逐时刻对照','','全部在所列上升沿之前查看。数据只有在对应写使能为1时才被保存。', '',
              '|时间 ns|任务|写入对象|a_we,b_we,bias_we|wr_row|wr_col|wr_k|wr_value / wr_bias（有符号）|hex|',
              '|---|---|---|---|---|---|---|---|---|']
    for b in buffers:
        enables={'weight':'1,0,0','input':'0,1,0','bias':'0,0,1'}[b['kind']]
        appendix.append(f"|{b['time_ns']}|{b['task']}|{b['kind']}|{enables}|{b['wr_row']}|{b['wr_col']}|{b['wr_k']}|{b['expected_signed']}|{b['expected_hex']}|")
    (OUT/'buffer_steps.md').write_text('\n'.join(appendix)+'\n',encoding='utf-8')
    doc+=['','## 完整明细与看波形时容易混淆的地方', '',
          '- [全部 307 次缓冲写入逐时刻表](buffer_steps.md)：继续追踪每个权重/输入写入时使用。',
          '- [全部任务字与缓存返回值](read_expected.csv)：rsp_valid/response_valid 有效的采样时刻及正确数值。',
          '- [严格按时间排序的总表](chronological_steps.md)：依次查看本文件的所有关键步骤。另有 [CSV 版本](step_checklist.csv)。',
          '- descriptor/in_data 是正在入队的任务，head_data/out_data 是等待出队的任务，它们不必在所有时刻相同。',
          '- task_* 在出队后切换到下一条是正常的；正在运行的配置看控制器 cia/coa/cwa/cba/cfs/cch/clp。',
          '- row/col/kidx 在装载期间表示写缓冲位置，row/col 在输出期间表示选哪个结果。',
          '- sums 在累加过程中变化，只有本表标出的有效分块完成时刻才能对照相应的部分和/最终值。',
          '- 缓存的 rsp_data 是整字，response_data 是提取后的字节或偏置；两者不是必须相等。',
          '', '重新生成本表：`python mobilefacenet/scripts/interface_wave_steps.py`。此命令先重新验证现有 VCD，不改变测试输入和 RTL。']
    (OUT/'step_checklist.md').write_text('\n'.join(doc)+'\n',encoding='utf-8')
    chronological=sorted(rows,key=lambda r:(r['time_ns'],r['edge']=='沿后'))
    (OUT/'chronological_steps.md').write_text('\n'.join([
        '# 波形关键步骤：严格按时间顺序', '',
        '单位 ns；沿前表示本上升沿接收的值，沿后表示寄存器更新后的值。模块前缀说明见 [按步骤对照文档](step_checklist.md)。',
        *table(chronological)])+'\n',encoding='utf-8')
    with (OUT/'step_checklist.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader()
        writer.writerows(chronological)
    print(f'Created step_checklist.md: {len(rows)} stage observations; 307 buffer-write steps.')


if __name__=='__main__':main()
