# -*- coding: utf-8 -*-
"""Select only the connections shown in the user's hardware block diagram."""
import argparse
import json

from interface_wave import OUT, TB, DUT, QUEUE, ENG, open_view


# Each physical connection appears once, even when its endpoints have two names.
GROUPS = {
    'clock': [(TB+'clk',1,'28','系统时钟：周期 10 ns，上升沿采样')],
    'CPU_and_registers': [
        (DUT+'mmio_wdata',32,'22','CPU → 寄存器组：图中共享的 32 位写数据'),
        (DUT+'regs.input_addr',32,'22','reg1 → 队列：任务表地址'),
        (DUT+'regs.feature_size',32,'24','reg2 → 队列：任务数量'),
        (DUT+'regs.op_type',4,'24','reg3 → 队列：队列启动类型')],
    'FIFO_and_queue': [
        (QUEUE+'head_data',256,'22','FIFO → 队列：256 位任务；与 FIFO out_data 是同一条线'),
        (QUEUE+'buffered',32,'24','FIFO → 队列：32 位数量；与 FIFO level 是同一条线'),
        (QUEUE+'fifo.in_ready',1,'28','FIFO → 读取器：1 位可接收标志，即 descriptor_ready')],
    'queue_to_compute': [
        *[(QUEUE+'task_'+n,32,'22','队列 → 阵列控制器：32×7 中的 task_'+n)
          for n in ('input','output','weight','bias','size','channels','param')],
        (QUEUE+'queue_base',32,'22','队列 → 阵列控制器：任务表起始地址'),
        (QUEUE+'queue_end',64,'22','队列 → 阵列控制器：任务表结束边界'),
        (QUEUE+'task_op',4,'24','队列 → 阵列控制器：4 位操作类型')],
    'task_reader': [
        (QUEUE+'reader.base_address',32,'22','队列 → 读取器：本条任务地址'),
        (QUEUE+'reader.idle',1,'28','读取器 → 队列：1 位空闲标志'),
        (QUEUE+'reader.rsp_data',32,'22','RAM → 读取器：32 位任务字，经过队列模块的纯接线中转'),
        (QUEUE+'reader.cmd_addr',32,'22','读取器 → RAM：32 位读地址'),
        (QUEUE+'reader.descriptor',256,'22','读取器 → FIFO：256 位完整任务；与 FIFO in_data 同线')],
    'read_cache': [
        (ENG+'reads.req_addr',32,'22','阵列控制器 → 缓存：read_address / req_addr 同线'),
        (ENG+'reads.cmd_addr',32,'22','缓存 → RAM：32 位整字读取地址'),
        (ENG+'reads.rsp_data',32,'22','RAM → 缓存：32 位整字数据'),
        (ENG+'reads.response_data',32,'22','缓存 → 分块缓冲与阵列：32 位数据')],
    'compute_configuration': [
        *[(ENG+n,4,'24','阵列控制器 → 阵列：4×3 中的 '+n) for n in ('nr','nc','nk')],
        *[(ENG+n,3,'24','阵列控制器 → 阵列：3×3 中的 '+n+
           ('；也连接输出处理的结果选择' if n in ('row','col') else '')) for n in ('row','col','kidx')]],
    'output': [
        (ENG+'sums',2048,'22','阵列 → 输出处理：64 个 PE 的 32 位结果'),
        (TB+'quant_shift',8,'24','阵列控制器 → 输出处理：clp[19:12]，图中 8 位'),
        (ENG+'output_store.we',1,'28','阵列控制器 → 输出处理：图中 1 位结果保存使能'),
        (ENG+'output_address',32,'22','阵列控制器 → RAM：结果写回地址'),
        (ENG+'cmd_wdata',32,'22','输出处理 → RAM：32 位写数据，低 8 位为 out_value，高 24 位为零')]
}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--open',action='store_true')
    args=parser.parse_args()
    source=OUT/'interfaces.vcd'
    if not source.is_file():
        parser.error('First run: python mobilefacenet/scripts/interface_wave.py')
    signals=[s for group in GROUPS.values() for s in group]
    wanted={s[0] for s in signals}
    declarations={};stack=[];body_start=None
    lines=source.read_text(encoding='ascii').splitlines(keepends=True)
    for i,line in enumerate(lines):
        p=line.split()
        if not p:continue
        if p[0]=='$scope':stack.append(p[2])
        elif p[0]=='$upscope':stack.pop()
        elif p[0]=='$var':
            name='.'.join(stack+[p[4]])
            if name in wanted:declarations[name]=(p[1],int(p[2]),p[3])
        elif p[0]=='$enddefinitions':body_start=i+1;break
    assert set(declarations)==wanted, wanted-set(declarations)
    for name,width,_,_ in signals:assert declarations[name][1]==width,name
    # Keep only the selected wires in a new VCD; do not alter the original trace.
    tree={}
    for name,(typ,width,code) in declarations.items():
        node=tree;parts=name.split('.')
        for part in parts[:-1]:node=node.setdefault(part,{})
        node[parts[-1]]=(typ,width,code)
    header=['$comment Filtered from the verified three-task interfaces.vcd $end\n',
            '$timescale 1ps $end\n']
    def emit(node):
        for name,item in node.items():
            if isinstance(item,dict):
                header.append(f'$scope module {name} $end\n');emit(item);header.append('$upscope $end\n')
            else:
                typ,width,code=item
                span=f' [{width-1}:0]' if width>1 else ''
                header.append(f'$var {typ} {width} {code} {name}{span} $end\n')
    emit(tree);header.append('$enddefinitions $end\n')
    codes={v[2] for v in declarations.values()}
    body=[];seen=set()
    for line in lines[body_start:]:
        p=line.split()
        if not p:continue
        if line[0] in '#$':body.append(line)
        elif line[0] in 'bBrR':
            if p[1] in codes:body.append(line);seen.add(p[1])
        elif line[0] in '01xz':
            code=line[1:].strip()
            if code in codes:body.append(line);seen.add(code)
    assert codes<=seen,'Selected signals have no values'
    wave=OUT/'diagram.vcd';wave.write_text(''.join(header+body),encoding='ascii')
    save=[f'[dumpfile] "{wave.as_posix()}"','[timestart] 0','[size] 1600 1000','[signals_width] 460']
    doc=['# 图中连线与精简波形对应', '',
         f'保留图中 37 根主要信号，并在第一行加入 clk，共 **{len(signals)} 根信号**。使用已经验证的三个任务波形，不重新生成输入。',
         '打开 diagram.gtkw；原始精简波形为 diagram.vcd。原来的 interfaces.vcd 和 all.gtkw 保留。',
         '', '## 图上连线的解释', '',
         '- CPU 向三个寄存器的共享 32 位线按 mmio_wdata 选取。图中没有画出的 mmio_addr、读写握手没有额外加入。',
         '- reg1/reg2/reg3 分别按任务表地址、任务数量、op_type 对应。',
         '- FIFO 到读取器的 1 位线按 in_ready/descriptor_ready；读取器到队列的 1 位线按 idle 对应。',
         '- RAM 与缓存之间的双向 32 位标注拆成 cmd_addr（地址）和 rsp_data（数据）。',
         '- 输出到 RAM 的 32 位线按 cmd_wdata 展示，内容为 24 位零加 8 位 out_value。RAM 框包含访问接口，所以这里不是外部整字读改写后的 mem_wdata。',
         '- 图中 8+2×3+1 分别对应 quant_shift、row/col、output_store.we。row/col 与写缓冲位置共用同一组实际寄存器，只显示一次。',
         '- 第一行 clk 用于对齐采样沿，周期 10 ns；不额外加入复位、状态机、任务编号、PE 调试值，以及图中未明确画出的其他握手信号。',
         '', '|波形行|信号|位宽|对应图中连线|','|---|---|---|---|']
    count=0
    for title,group in GROUPS.items():
        save+=['@200','-'+title]
        for name,width,fmt,meaning in group:
            count+=1;save+=['@'+fmt,name+(f'[{width-1}:0]' if width>1 else '')]
            doc.append(f'|{count}|`{name.removeprefix(TB)}`|{width}|{meaning}|')
    doc+=['','同一条线省略的别名：descriptor=in_data，head_data=out_data，buffered=level，read_address=req_addr，row/col/kidx=wr_row/wr_col/wr_k。',
          '', '该视图刻意省略了多数有效标志；需要核对某个数据是否应该有效时，按 [分步骤对照文档](step_checklist.md) 中的具体时间定位。',
          '', '重新打开：`python mobilefacenet/scripts/diagram_wave.py --open`。']
    (OUT/'diagram.gtkw').write_text('\n'.join(save)+'\n',encoding='utf-8')
    (OUT/'diagram_signals.md').write_text('\n'.join(doc)+'\n',encoding='utf-8')
    (OUT/'diagram_result.json').write_text(json.dumps(dict(signals=count,source=str(source),wave=str(wave),
        original_size=source.stat().st_size,filtered_size=wave.stat().st_size),indent=2),encoding='utf-8')
    print(f'Created diagram.gtkw and diagram.vcd: {count} selected signals, all names and widths verified.')
    if args.open:
        open_view('diagram',wave=wave)


if __name__=='__main__':main()
