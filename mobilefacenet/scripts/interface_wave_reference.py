# -*- coding: utf-8 -*-
"""Independent scalar golden values and edge-by-edge checks for interface_wave."""
import csv
import json
from pathlib import Path
import struct

from interface_wave import OUT, TB, DUT, QUEUE, ENG


def write_csv(name, rows):
    with (OUT/name).open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def signed(value, bits):
    return value-(1 << bits) if value & (1 << (bits-1)) else value


def edges(path):
    """Yield settled values before/after each rising edge; VCD time unit is 1 ps."""
    stack, names, widths, values = [], {}, {}, {}
    time, before = 0, {}
    with path.open(encoding='ascii') as f:
        header = True
        for line in f:
            p = line.split()
            if not p: continue
            if header:
                if p[0] == '$scope': stack.append(p[2])
                elif p[0] == '$upscope': stack.pop()
                elif p[0] == '$var':
                    name = '.'.join(stack+[p[4]])
                    names[name], widths[name] = p[3], int(p[2])
                elif p[0] == '$enddefinitions': header = False
                continue
            if line.startswith('#'):
                if before.get(names[TB+'clk']) == '0' and values.get(names[TB+'clk']) == '1':
                    yield time//1000, before, values.copy(), names, widths
                before = values.copy(); time = int(line[1:])
            elif line[0] in 'bB': values[p[1]] = p[0][1:].lower()
            elif line[0] in '01xz': values[line[1:].strip()] = line[0]
        if before.get(names[TB+'clk']) == '0' and values.get(names[TB+'clk']) == '1':
            yield time//1000, before, values.copy(), names, widths


def build_goldens():
    layers = json.loads((OUT/'vectors/layer_config.json').read_text())['layers']
    memory = bytearray((OUT/'vectors/queue_ram.bin').read_bytes())
    tasks = []
    for l in layers:
        ci, co, h, w, k, pad = [l[n] for n in ('in_channels','out_channels','height','width','kernel','padding')]
        oh = (h+2*pad-k)//l['stride']+1; ow = (w+2*pad-k)//l['stride']+1
        x = [signed(v,8) for v in memory[l['input_addr']:l['input_addr']+ci*h*w]]
        wc = co*(1 if l['op']=='depthwise' else ci)*k*k
        weight = [signed(v,8) for v in memory[l['weight_addr']:l['weight_addr']+wc]]
        bias = list(struct.unpack_from('<'+'i'*co,memory,l['bias_addr']))
        terms, raw, result = {}, [], []
        reduction = k*k*(1 if l['op']=='depthwise' else ci)
        for oc in range(co):
            for pos in range(oh*ow):
                products = []
                for r in range(reduction):
                    ic = oc if l['op']=='depthwise' else r//(k*k)
                    ky,kx = divmod(r%(k*k),k)
                    iy = (pos//ow)*l['stride']+ky-pad
                    ix = (pos%ow)*l['stride']+kx-pad
                    xv = x[(ic*h+iy)*w+ix] if 0<=iy<h and 0<=ix<w else 0
                    wi = oc*reduction+r
                    products.append((xv,weight[wi],xv*weight[wi]))
                terms[oc,pos] = products
                rv = signed((bias[oc]+sum(p[2] for p in products)) & 0xffffffff,32)
                raw.append(rv); result.append(max(-128,min(127,rv>>l['quant_shift'])))
        tasks.append(dict(layer=l,x=x,weights=weight,bias=bias,terms=terms,raw=raw,result=result,
                          memory=memory.copy(),spatial=oh*ow,oh=oh,ow=ow,reduction=reduction))
        memory[l['output_addr']:l['output_addr']+len(result)] = bytes(v & 255 for v in result)
    return tasks


def main():
    tasks = build_goldens()
    descriptors = (OUT/'vectors/queue.bin').read_bytes()
    checks, buffers, tiles, outputs, reads, fifo, mmio = [], [], [], [], [], [], []
    task_index, pushes, desc_read = -1, 0, 0
    pending_read, miss_addr = None, None
    started = []
    for ns, pre, post, names, widths in edges(OUT/'interfaces.vcd'):
        def get(name, after=False, low=None, bits=None):
            val = (post if after else pre).get(names[name], 'x')
            val = val.rjust(widths[name], val[0] if val[0] in 'xz' else '0')
            if low is not None:
                end = len(val)-low; val = val[end-bits:end]
            return None if any(c in val for c in 'xz') else int(val,2)
        def check(name, expected, after=False, low=None, bits=None):
            actual = get(name,after,low,bits)
            label = name.removeprefix(TB)+(f'[{low+bits-1}:{low}]' if low is not None else '')
            checks.append(dict(time_ns=ns,edge='after' if after else 'before',task=task_index,
                               signal=label,expected=str(expected),actual=str(actual),match=actual==expected))
            if actual != expected: raise AssertionError(f'{ns}ns {label}: {actual} != {expected}')
        if get(TB+'rst_n') != 1: continue
        if get(DUT+'mmio_we') and get(DUT+'mmio_ready'):
            addr,value = get(DUT+'mmio_addr'),get(DUT+'mmio_wdata')
            expected = {0x40000008:0x3000,0x40000018:3,0x40000000:0x3d}[addr]
            check(DUT+'mmio_wdata',expected)
            reg = {0x40000008:'input_addr',0x40000018:'feature_size',0x40000000:'op_type'}[addr]
            check(DUT+'regs.'+reg,15 if reg=='op_type' else expected,True)
            mmio.append(dict(time_ns=ns,mmio_addr=f'{addr:08X}',mmio_wdata=f'{expected:08X}',
                             registered=reg,expected_after=15 if reg=='op_type' else expected))
        push = bool(get(QUEUE+'fifo.in_valid') and get(QUEUE+'fifo.in_ready'))
        pop = bool(get(QUEUE+'fifo.out_valid') and get(QUEUE+'fifo.out_ready'))
        if push:
            desc = int.from_bytes(descriptors[pushes*32:(pushes+1)*32],'little')
            for n in ('reader.descriptor','fifo.in_data'): check(QUEUE+n,desc)
            fifo.append(dict(time_ns=ns,event='PUSH',task=pushes,
                             level_before=get(QUEUE+'fifo.level'),level_after=get(QUEUE+'fifo.level',True)))
            pushes += 1
        if pop:
            task_index += 1
            desc = int.from_bytes(descriptors[task_index*32:(task_index+1)*32],'little')
            for n in ('head_data','fifo.out_data'): check(QUEUE+n,desc)
            words = struct.unpack_from('<8I',descriptors,task_index*32)
            for n,word in zip(('op','input','output','weight','bias','size','channels','param'),words):
                check(QUEUE+'task_'+n,word & 15 if n=='op' else word)
            check(QUEUE+'exec_start',1)
            fifo.append(dict(time_ns=ns,event='POP',task=task_index,
                             level_before=get(QUEUE+'fifo.level'),level_after=get(QUEUE+'fifo.level',True)))
        check(QUEUE+'buffered',get(QUEUE+'fifo.level'))
        check(QUEUE+'fifo.level',get(QUEUE+'fifo.level')+int(push)-int(pop),True)
        if get(QUEUE+'reader.start'):
            check(QUEUE+'reader.base_address',0x3000+pushes*32)
        if get(QUEUE+'reader.rsp_valid'):
            addr=0x3000+desc_read*4
            expected=int.from_bytes(descriptors[desc_read*4:desc_read*4+4],'little')
            check(QUEUE+'reader.cmd_addr',addr); check(QUEUE+'reader.rsp_data',expected)
            reads.append(dict(time_ns=ns,kind='descriptor',task=desc_read//8,
                              req_addr=f'{addr:08X}',cmd_addr=f'{addr:08X}',rsp_data=f'{expected:08X}',
                              response_data=f'{expected:08X}'))
            desc_read += 1
        if task_index<0: continue
        task=tasks[task_index];l=task['layer']
        state=get(ENG+'state');mb=get(ENG+'mb');nb=get(ENG+'nb');kb=get(ENG+'kb')
        row=get(ENG+'row');col=get(ENG+'col');ki=get(ENG+'kidx')
        if get(ENG+'reads.req_valid') and get(ENG+'reads.req_ready'):
            oc=mb+row;r=kb+ki;pos=nb+col
            if state==2: address=l['bias_addr']+oc*4
            elif state==4: address=l['weight_addr']+oc*task['reduction']+r
            elif state==6:
                ic=oc if l['op']=='depthwise' else r//(l['kernel']**2)
                ky,kx=divmod(r%(l['kernel']**2),l['kernel'])
                iy=(pos//task['ow'])*l['stride']+ky-l['padding']
                ix=(pos%task['ow'])*l['stride']+kx-l['padding']
                address=l['input_addr']+(ic*l['height']+iy)*l['width']+ix
            else: raise AssertionError('Unexpected read phase')
            check(ENG+'read_address',address);check(ENG+'reads.req_addr',address)
            pending_read=(address,state!=2,ns)
        if get(ENG+'reads.cmd_valid') and get(ENG+'reads.cmd_ready'):
            miss_addr=pending_read[0] & ~3;check(ENG+'reads.cmd_addr',miss_addr)
        if get(ENG+'reads.rsp_valid'):
            expected=int.from_bytes(task['memory'][miss_addr:miss_addr+4],'little')
            check(ENG+'reads.rsp_data',expected)
        if get(ENG+'reads.response_valid'):
            address,byte_mode,request_ns=pending_read
            word=int.from_bytes(task['memory'][address & ~3:(address & ~3)+4],'little')
            expected=task['memory'][address] if byte_mode else word
            check(ENG+'reads.response_data',expected)
            reads.append(dict(time_ns=ns,kind='cache_response',task=task_index,
                              req_addr=f'{address:08X}',cmd_addr=f'{address & ~3:08X}',rsp_data=f'{word:08X}',
                              response_data=f'{expected:08X}'))
        for kind,enable in [('bias','bias_we'),('weight','a_we'),('input','b_we')]:
            if not get(ENG+enable): continue
            oc=mb+row;r=kb+ki;pos=nb+col
            if kind=='bias': expected=task['bias'][oc];signal='wr_bias';bits=32
            elif kind=='weight': expected=task['weights'][oc*task['reduction']+r];signal='wr_value';bits=8
            else: expected=task['terms'][oc if l['op']=='depthwise' else mb,pos][r][0];signal='wr_value';bits=8
            check(ENG+'tile.'+signal,expected & ((1<<bits)-1))
            for n,v in [('wr_row',row),('wr_col',col),('wr_k',ki)]: check(ENG+'tile.'+n,v)
            buffers.append(dict(time_ns=ns,task=task_index,kind=kind,mb=mb,nb=nb,kb=kb,
                                wr_row=row,wr_col=col,wr_k=ki,expected_signed=expected,
                                expected_hex=f'{expected & ((1<<bits)-1):0{bits//4}X}'))
        if get(ENG+'tile.start'):
            nr=min(8,l['out_channels']-mb);nc=min(8,task['spatial']-nb);nk=min(8,task['reduction']-kb)
            for n,v in [('nr',nr),('nc',nc),('nk',nk)]: check(ENG+n,v)
            check(ENG+'tile.accumulate',int(kb!=0))
            started.append(dict(task=task_index,start_ns=ns,mb=mb,nb=nb,kb=kb,nr=nr,nc=nc,nk=nk,done_ns=None))
        if get(ENG+'tile.done'):
            started[-1]['done_ns']=ns
            for rr in range(get(ENG+'nr')):
                for cc in range(get(ENG+'nc')):
                    oc=mb+rr;pos=nb+cc
                    expected=task['bias'][oc]+sum(v[2] for v in task['terms'][oc,pos][:kb+get(ENG+'nk')])
                    low=(rr*8+cc)*32
                    check(ENG+'sums',expected & 0xffffffff,low=low,bits=32)
                    tiles.append(dict(time_ns=ns,task=task_index,mb=mb,nb=nb,kb=kb,
                                      row=rr,col=cc,sums_bits=f'{low+31}:{low}',expected_signed=expected,
                                      expected_hex=f'{expected & 0xffffffff:08X}'))
        if state==10:
            raw=task['raw'][(mb+row)*task['spatial']+nb+col]
            check(ENG+'raw',raw & 0xffffffff)
            check(TB+'quant_shift',l['quant_shift'])
            check(ENG+'clp',l['quant_shift'],low=12,bits=8)
        if get(ENG+'cmd_valid') and get(ENG+'cmd_write') and get(ENG+'cmd_ready'):
            offset=(mb+row)*task['spatial']+nb+col
            expected=task['result'][offset];address=l['output_addr']+offset
            check(ENG+'out_value',expected & 255);check(ENG+'output_address',address)
            outputs.append(dict(time_ns=ns,task=task_index,row=row,col=col,output_channel=mb+row,
                                spatial_position=nb+col,raw=task['raw'][offset],shift=l['quant_shift'],
                                out_value_signed=expected,out_value_hex=f'{expected & 255:02X}',
                                output_address=f'{address:08X}'))
    for filename,rows in [('wave_checks.csv',checks),('buffer_expected.csv',buffers),('sums_expected.csv',tiles),
                          ('output_expected.csv',outputs),('read_expected.csv',reads),('fifo_expected.csv',fifo),
                          ('tile_expected.csv',started)]: write_csv(filename,rows)
    doc=['# 三任务波形正确值对照', '',
         '**本表的数值从输入、权重、偏置独立计算，再与本次 VCD 实际波形比较；并非直接把波形值当作预期值。**',
         f'本次共通过 {len(checks)} 项信号值检查，覆盖任务、读取、缓冲装载、分块结果和 39 次输出。',
         '', '## 时间和显示方式', '',
         '- 所有时间单位为 ns，时钟周期 10 ns。波形文件原始单位为 ps：例如 1175 ns = 1175000 ps。',
         '- 下表未特别说明时，查看该上升沿**之前**的值，即被这个时钟沿接收的值。寄存器更新看沿后；FIFO 表同时给出沿前/沿后数量。',
         '- 地址/打包数据用十六进制；输入、权重、累加和输出数值用有符号十进制。FF 表示 INT8 的 −1，FFFFFFFF 表示 INT32 的 −1。',
         '- 有效信号为 0 时的数据不需要与本表匹配。量化先算术右移再饱和；负数右移向负无穷取整。',
         '', '## 1. CPU 写寄存器', '', '|采样时间|mmio_addr|mmio_wdata|沿后寄存器|沿后值|', '|---|---|---|---|---|']
    doc += [f"|{r['time_ns']}|{r['mmio_addr']}|{r['mmio_wdata']}|{r['registered']}|{r['expected_after']}|" for r in mmio]
    doc += ['', '`input_addr=0x3000`、`feature_size=3`、`op_type=15`。任务表范围 queue_base=0x3000、queue_end=0x3060。',
            '', '## 2. 三条任务的配置', '', '|字段|任务 0|任务 1|任务 2|','|---|---|---|---|']
    labels=['头字（版本+操作）','task_input','task_output','task_weight','task_bias','task_size','task_channels','task_param']
    words=[struct.unpack_from('<8I',descriptors,i*32) for i in range(3)]
    for j,label in enumerate(labels): doc.append('|'+label+'|'+'|'.join(f'{v[j]:08X}' for v in words)+'|')
    doc += ['|task_op|0|1|0|','|clp[19:12] / quant_shift|1|2|1|','|reader.base_address|00003000|00003020|00003040|',
            '', '读取器 cmd_addr 每个字加 4；任务 0 为 3000～301C，任务 1 为 3020～303C，任务 2 为 3040～305C。对应 rsp_data 依次是上表的 8 个字。',
            '', '256 位总线从高位到低位显示如下：最右边 8 个十六进制数字才是头字。descriptor → FIFO in_data → out_data/head_data 应传递同一条任务。']
    for i in range(3): doc += ['', f'任务 {i}：', '', '```text',f'{int.from_bytes(descriptors[i*32:(i+1)*32],"little"):064X}','```']
    doc += ['', '## 3. FIFO 入队、出队', '', '|时间|事件|任务|buffered/level 沿前|沿后|','|---|---|---|---|---|']
    doc += [f"|{r['time_ns']}|{r['event']}|{r['task']}|{r['level_before']}|{r['level_after']}|" for r in fifo]
    doc += ['', '出队沿前查看 head_data/out_data/task_*；沿后 FIFO 队首可能立即变成下一条，当前计算配置已锁存。',
            '', '## 4. 输入、权重、偏置及正确结果', '', '数组按 CHW：先一个通道的全部行列，再下一个通道。权重按输出通道、输入通道、核行、核列排列。']
    def matrix(title,values,h,w):
        return ['',title,'','```text']+[' '.join(f'{v:5d}' for v in values[y*w:(y+1)*w]) for y in range(h)]+['```']
    for i,t in enumerate(tasks):
        l=t['layer'];k=l['kernel']
        doc += ['',f"### 任务 {i}：{l['op']} {k}×{k}",'',f"padding={l['padding']}，stride=1，shift={l['quant_shift']}；偏置 {t['bias']}。"]
        for c in range(2): doc += matrix(f'输入通道 {c}',t['x'][c*9:(c+1)*9],3,3)
        for oc in range(l['out_channels']):
            for ic in range(1 if l['op']=='depthwise' else 2):
                offset=oc*t['reduction']+ic*k*k
                doc += matrix(f'权重：输出通道 {oc}，输入通道 {oc if l["op"]=="depthwise" else ic}',t['weights'][offset:offset+k*k],k,k)
        for c in range(l['out_channels']):
            a=c*t['spatial'];b=a+t['spatial']
            doc += matrix(f'通道 {c}：量化前结果（完整累加后对应 sums）',t['raw'][a:b],t['oh'],t['ow'])
            doc += matrix(f'通道 {c}：量化后结果（out_value / RAM）',t['result'][a:b],t['oh'],t['ow'])
    doc += ['', '## 5. 分块配置及 sums 检查时刻', '',
            'start 时间查看 nr/nc/nk；done 时间查看 sums。行代表输出通道，列代表展平空间位置。有效结果在 sums[(row×8+col)×32 +: 32]。',
            '', '|任务|start ns|done ns|mb|nb|kb|nr|nc|nk|accumulate|','|---|---|---|---|---|---|---|---|---|---|']
    doc += ['|'+ '|'.join(str(r[n]) for n in ('task','start_ns','done_ns','mb','nb','kb','nr','nc','nk'))+f"|{int(r['kb']!=0)}|" for r in started]
    doc += ['', '任务 1 按 8+1 项累加，任务 2 按 8+8+2 项累加。中间块的 sums 是部分和，不能直接拿最终结果来比较。完整有效 PE 的每块预期值见 sums_expected.csv；无效行列不作为输出检查。',
            '', '### PE(0,0) 每块累加值', '', '|任务|时间 ns|nb|kb|sum_00 应为|','|---|---|---|---|---|']
    doc += [f"|{r['task']}|{r['time_ns']}|{r['nb']}|{r['kb']}|{r['expected_signed']}|" for r in tiles if r['row']==0 and r['col']==0]
    doc += ['', '## 6. 全部结果写回对照', '',
            '这些是 cmd_valid && cmd_write && cmd_ready 的采样时间；外部 RAM 的读改写完成会更晚。row/col 是当前分块内索引。',
            '', '|时间 ns|任务|row|col|raw|shift|out_value 十进制|8 位十六进制|output_address|','|---|---|---|---|---|---|---|---|---|']
    doc += ['|'+'|'.join(str(r[n]) for n in ('time_ns','task','row','col','raw','shift','out_value_signed','out_value_hex','output_address'))+'|' for r in outputs]
    doc += ['', '## 7. 逐项查表文件', '',
            '- [read_expected.csv](read_expected.csv)：24 个任务字和全部缓存返回值。缓存行的 cmd_addr/rsp_data 是对应整字的地址与预期内容；缓存命中时不代表实际再次发出了 RAM 请求。实际请求/返回仍以 valid/ready 为准。',
            '- [buffer_expected.csv](buffer_expected.csv)：每次 bias_we/a_we/b_we 有效时的 wr_row/wr_col/wr_k 和正确输入数值。',
            '- [sums_expected.csv](sums_expected.csv)：每块完成时每个有效 PE 的预期值，注明 sums 位段。',
            '- [output_expected.csv](output_expected.csv)：全部写回的时间、位置、量化前后值及地址。',
            '- [wave_checks.csv](wave_checks.csv)：预期值与 VCD 实际值逐项比较；match 全为 True。',
            '', '重新生成：`python mobilefacenet/scripts/interface_wave_reference.py`（先运行 interface_wave.py 生成本轮仿真）。']
    (OUT/'reference.md').write_text('\n'.join(doc)+'\n',encoding='utf-8')
    summary=dict(status='passed',checks=len(checks),descriptor_words=desc_read,buffer_writes=len(buffers),
                 valid_pe_block_results=len(tiles),outputs=len(outputs),tile_runs=len(started))
    (OUT/'reference_result.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))


if __name__=='__main__': main()
