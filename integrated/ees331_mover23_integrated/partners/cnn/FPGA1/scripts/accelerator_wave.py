"""One complete array-only run: Conv/DW, task timing, 128 outputs."""
import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
from reference import execute, output_shape, write_golden
from array_vectors import generate_queue

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build'/'accelerator_wave'
ENGINE='dut.systolic_path.engine.'


def s(name, meaning, bits=1, fmt='28'):
    return (name if bits==1 else f'{name}[{bits-1}:0]',fmt,meaning)


def d(name, meaning, bits=32):return s(name,meaning,bits,'24')
def h(name, meaning):return s(name,meaning,32,'22')
def v(name, meaning, bits=8):return s(name,meaning,bits,'420')


COMMON=[s('clk','时钟；周期 10 ns'),s('core_busy','整个加速器/队列忙'),d('active_task','当前执行的任务编号，0～8'),
        d('active_op','当前算子：0 Conv、1 DW',4)]
VIEWS={
    'timing':[
        s('clk','时钟；周期10ns'),d('active_task','当前任务编号；仅在下发新任务时切换'),
        d('active_op','当前算子编号',4),s('exec_done','前一任务完成，队列在本上升沿接受'),
        s('exec_start','下一任务启动，执行模块在本上升沿接受'),
        d('queue_buffered','等待下发的任务数；为0时可能需要补取任务'),
        s('task_fetch','RAM当前访问属于任务读取，可与阵列计算重叠'),
        s('bias_load','卷积读取Bias阶段，包含等待'),s('weight_load','卷积读取权重阶段，包含等待'),
        s('input_load','读取输入阶段，包含等待和补零；包含有效输入和padding补零'),
        s('array_running','阵列初始化或计算期间为1'),d('mac_active_count','本上升沿实际有效乘加的PE数量；大于1表示计算并行',7),
        s('postprocess','结果移位/饱和并暂存的阶段'),s('writeback','向内存接口提交输出并等待完成，包含读改写'),
        s('rd','外部RAM读请求'),s('wr','外部RAM写请求'),s('ram_wait','外部RAM请求尚未得到ready，正在等待')],
    'overview':[
        s('clk','时钟；周期 10 ns'),s('rst_n','0 复位，1 正常工作'),
        s('queue_start','启动整个队列；整次运行仅一个脉冲'),s('core_busy','从取任务到最终写回一直忙'),
        s('queue_active','队列控制器正在处理'),d('queue_state','0空闲/1检查/2边取边调度/5排空/6完成/7错误',4),
        d('queue_fetched','已取回描述符数，最后为 9'),d('queue_buffered','等待执行的 窗口条目数，最大为 4'),
        d('active_task','当前正在执行的任务编号；exec_start 的上升沿后更新'),
        d('active_op','当前算子：0 Conv、1 DW',4),
        s('exec_start','下发当前任务；整次运行共 9 个脉冲'),s('array_running','阵列本块处于初始化/计算阶段'),
        s('exec_done','当前一个任务已完成；整次共 9 次，不等于整队列 DONE'),
        d('queue_completed','已完成任务数，从 0 逐步到 9'),
        s('final_output_issue','当前正在提交第 8 号任务的最终特征字节写请求'),
        s('status_done','全部任务完成后才置 1，并保持'),s('status_error','正常运行始终为 0')],
    'memory':COMMON+[
        s('we','MMIO 写使能'),h('addr','MMIO 寄存器地址'),h('wdata','MMIO 写入数据'),
        s('re','MMIO 读使能'),h('rdata','MMIO 读回值；STATUS 运行中为1，完成后为2'),
        h('active_input','当前任务输入 RAM 地址'),h('active_output','当前任务输出 RAM 地址'),
        h('active_size','高16位H、低16位W'),h('active_channels','高16位OC、低16位IC'),
        h('active_param','kernel/stride/padding/quant_shift/激活配置'),
        s('rd','外部 RAM 读请求'),s('wr','外部 RAM 写请求'),s('mready','本次 RAM 操作可在该上升沿完成'),
        h('ma','外部 RAM 对齐字地址'),h('mr','RAM 返回的32bit数据'),h('md','写往 RAM 的32bit数据')],
    'array':COMMON+[
        d(ENGINE+'state','卷积FSM：2/3读Bias，4/5读权重，6/7读窗口，8启动，9计算，10后处理，11/12写回',4),
        s(ENGINE+'dw','1表示独立通道 Depthwise；0表示普通卷积'),
        d(ENGINE+'mb','本块输出通道起点'),d(ENGINE+'nb','本块展平输出位置起点'),d(ENGINE+'kb','本批乘加项起点'),
        d(ENGINE+'nr','本块有效PE行数，最大8',4),d(ENGINE+'nc','本块有效PE列数，最大8',4),
        d(ENGINE+'nk','本批乘加项数，最大8',4),
        s(ENGINE+'bias_we','写入 Bias 缓冲'),s(ENGINE+'a_we','写入权重缓冲'),s(ENGINE+'b_we','写入输入窗口缓冲'),
        d(ENGINE+'row','缓冲行/结果行索引',3),d(ENGINE+'col','缓冲列/结果列索引',3),d(ENGINE+'kidx','本批数据索引',3),
        v(ENGINE+'tile.wr_value','写入输入/权重缓冲的有符号INT8'),v(ENGINE+'tile.wr_bias','写入Bias缓冲的INT32',32),
        s(ENGINE+'tile.start','启动当前块的一批乘加'),d(ENGINE+'tile.tick','本批计算拍数',6),
        s('array_running','当前块忙；取数时为0'),s(ENGINE+'tile.done','当前批完成'),
        v(ENGINE+'raw','当前选中的阵列INT32累加结果；state=10时解读',32),
        v(ENGINE+'shifted','阵列结果算术右移后的值',32),
        v(ENGINE+'out_value','量化饱和后输出INT8')],
    'output':COMMON+[
        s('final_output_issue','最终128维卷积任务正在提交字节写请求'),
        d('output_index','最近接受的写请求编号；最终任务从0到127'),
        h('output_address_seen','最近接受的字节地址；最终任务从0x18001到0x18080'),
        v('output_value_seen','最近接受的有符号 INT8 特征；沿后更新'),
        s('wr','实际外部 RAM 字写请求'),s('mready','RAM 请求在该沿完成'),h('ma','RAM 对齐字地址'),h('md','含目标字节的32bit写数据'),
        s('exec_done','当前任务写回完成'),d('queue_completed','全部结束时为9'),s('status_done','所有结果写回后才置1'),s('status_error','应始终为0')]
}


def require(condition, message):
    if not condition:raise RuntimeError(message)


def generate():
    return generate_queue(OUT/'vectors')


def read_csv(path):
    with path.open(encoding='utf-8-sig') as file:return list(csv.DictReader(file))


def scan_wave(path):
    wanted={'tb_task_queue.'+name for name in ('queue_start','exec_start','exec_done','status_done','status_error','core_busy','queue_buffered','array_running')}
    stack=[];id_names={};declared=set();changes={name:[] for name in wanted};time=0;header=True
    with path.open() as stream:
        for line in stream:
            p=line.split()
            if not p:continue
            if header:
                if p[0]=='$scope':stack.append(p[2])
                elif p[0]=='$upscope':stack.pop()
                elif p[0]=='$var':
                    name='.'.join(stack+[p[4]]);declared.add(name+(p[5] if p[5].startswith('[') else ''))
                    if name in wanted:id_names.setdefault(p[3],[]).append(name)
                elif p[0]=='$enddefinitions':header=False
                continue
            if line.startswith('#'):time=int(line[1:]);continue
            if line.startswith('b'):value,code=p[0][1:],p[1]
            elif line[0] in '01xz':value,code=line[0],line[1:].strip()
            else:continue
            if code in id_names and all(c in '01' for c in value):
                for name in id_names[code]:changes[name].append((time//1000,int(value,2)))
    return declared,{name.split('.')[-1]:data for name,data in changes.items()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--open',action='store_true')
    parser.add_argument('--view',choices=VIEWS,default='timing')
    args=parser.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'result.json').write_text(json.dumps({'status':'running'}),encoding='utf-8')
    folder,layers,goldens=generate()
    subprocess.run([sys.executable,str(ROOT/'scripts'/'run_tests.py'),'task_queue','--queue-dir',str(folder),'--overview'],check=True)
    tasks=read_csv(OUT/'tasks.csv');outputs=read_csv(OUT/'output_events.csv')
    comparisons=read_csv(ROOT/'build'/'queue_comparison.csv')
    require(len(tasks)==9 and [int(x['task']) for x in tasks]==list(range(9)),'task order/count')
    require([int(x['op']) for x in tasks]==[0,1,0,1,0,0,1,0,0],'operator sequence')
    expected_bytes=sum(x.size for x in goldens)
    require(len(comparisons)==expected_bytes,'layer output byte count')
    require(all(int(x['expected'])==int(x['actual']) for x in comparisons),'RAM golden comparison')
    require(len(outputs)==expected_bytes,'logical output count')
    for i,layer in enumerate(layers):
        events=[x for x in outputs if int(x['task'])==i];gold=goldens[i].reshape(-1)
        offsets=[int(x['address'])-layer['output_addr'] for x in events]
        require(sorted(offsets)==list(range(gold.size)),f'task {i} output address coverage')
        require(all(int(e['value'])==int(gold[offset]) for e,offset in zip(events,offsets)),f'task {i} issued value')
    actual=(ROOT/'build'/'queue_features.bin').read_bytes()
    require(len(actual)==128 and actual==(folder/'features.golden.bin').read_bytes(),'128 RAM features mismatch')
    (OUT/'features.actual.bin').write_bytes(actual)
    shutil.copyfile(ROOT/'build'/'queue_comparison.csv',OUT/'layer_comparison.csv')
    shutil.copyfile(ROOT/'build'/'queue_metrics.csv',OUT/'metrics.csv')
    wave=OUT/'accelerator.vcd';declared,changes=scan_wave(wave)
    highs=lambda name:[time for time,value in changes[name] if value==1]
    require(len(highs('queue_start'))==1,'must start queue exactly once')
    require(len(highs('exec_start'))==9 and len(highs('exec_done'))==9,'must dispatch/complete nine times')
    require(not highs('status_error'),'unexpected ERROR')
    require(len(highs('status_done'))==1 and highs('status_done')[0]>int(tasks[-1]['done_ns']),'DONE too early')
    first=int(tasks[0]['start_ns']);last=int(tasks[-1]['done_ns'])
    require(not any(first<=t<=last and value==0 for t,value in changes['core_busy']),'BUSY dropped between tasks')
    require(max(value for _,value in changes['queue_buffered'])==4,'prefetch depth not exercised')
    timing=[{k:int(v) for k,v in row.items()} for row in read_csv(OUT/'timing_cycles.csv')]
    phase_names=('task_fetch','bias_load','weight_load','input_load','array_running','postprocess','writeback')
    for row in timing:
        require(sum(row[name] for name in phase_names if name!='task_fetch')<=1,'unexpected overlap within this dependent task chain')
        require(row['macs']==0 or row['array_running']==1,'MAC outside array RUN')
    expected_macs=sum(int(np.prod(output_shape(layer)))*layer['kernel']**2*(layer['in_channels'] if layer['op']=='conv' else 1)
                      for layer in layers if layer['op'] in ('conv','depthwise'))
    require(sum(row['macs'] for row in timing)==expected_macs,'PE activity count does not match convolution workload')
    for i in range(len(layers)):
        lo,hi=int(tasks[i]['start_ns']),int(tasks[i]['done_ns'])
        require(any(lo<=t<=hi and value==1 for t,value in changes['array_running']),f'conv task {i} did not use array')
    for view,signals in VIEWS.items():
        for name,_,_ in signals:require('tb_task_queue.'+name in declared,f'VCD signal missing: {name}')
        (OUT/f'{view}.gtkw').write_text(f'[dumpfile] "{wave.as_posix()}"\n[timestart] 0\n[size] 1500 1000\n[signals_width] 310\n'
            +''.join(f'@{fmt}\ntb_task_queue.{name}\n' for name,fmt,_ in signals),encoding='utf-8')
    gaps=[]
    for previous,current in zip(tasks,tasks[1:]):
        lo=int(previous['done_ns']);hi=int(current['start_ns'])
        fetching=sum(row['task_fetch'] for row in timing if lo<=row['time_ns']<hi)
        gaps.append(dict(previous=int(previous['task']),next=int(current['task']),done_ns=lo,start_ns=hi,
                         gap_ns=hi-lo,gap_cycles=(hi-lo)//10,descriptor_fetch_cycles=fetching))
    with (OUT/'task_gaps.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(gaps[0]));writer.writeheader();writer.writerows(gaps)
    phase_rows=[]
    for task in tasks:
        samples=[row for row in timing if int(task['start_ns'])<=row['time_ns']<int(task['done_ns'])]
        phase_rows.append(dict(task=int(task['task']),duration_cycles=(int(task['done_ns'])-int(task['start_ns']))//10,
                               **{name+'_cycles':sum(row[name] for row in samples) for name in phase_names if name!='task_fetch'},
                               ram_wait_cycles=sum(row['ram_wait'] for row in samples),peak_parallel_macs=max(row['macs'] for row in samples)))
    with (OUT/'phase_cycles.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(phase_rows[0]));writer.writeheader();writer.writerows(phase_rows)
    schedule=['# 调度时序与并行活动','','默认 timing.gtkw 只展示活动、任务切换、等待及有效MAC数量，不展示固定配置和数据结果。',
              '下列完成/启动时间均指握手被接受的上升沿；信号的拉高时刻会早一拍。',
              '', '## 相邻任务什么时候开始', '', '|前任务→后任务|完成 ns|启动 ns|间隔周期|取任务周期|', '|---|---|---|---|---|']
    for gap in gaps:schedule.append(f"|{gap['previous']}→{gap['next']}|{gap['done_ns']}|{gap['start_ns']}|{gap['gap_cycles']}|{gap['descriptor_fetch_cycles']}|")
    schedule += ['', '当前示例各层存在依赖，后层等待前层写回；实际间隔见上表。',
                 '描述符持续预取；第一条完整任务即可派发，无需等待一批填满。',
                 '', '## 并行关系', '',
                 '- 本示例是有依赖的层链，任务串行；独立任务最多两条共享阵列，见 concurrent_wave.py。',
                 '- 每个上下文内仍按装载、计算、写回运行；任务预取和另一上下文可与它并行。',
                 '- mac_active_count统计即将在本沿乘加的PE数。大于1时，多个PE在同一沿并行计算。',
                 f"- 本次运行最多同拍 {max(row['macs'] for row in timing)} 个PE有效乘加，总计 {expected_macs} 次乘加；其余PE可能因尾块或数据传播而空闲。",
                 '- 阵列内部可以同拍计算并转发数据；RAM读取和输入/权重装载阶段重叠属于供数协作。',
                 '- rd与wr互斥；writeback阶段出现rd，是INT8写回的读改写操作。',
                 '- ram_wait与取数/写回阶段可以同时为1，表示该阶段正在等RAM，不是另一个并行计算任务。',
                 '', '## 推荐放大位置', '',
                 f"- {int(tasks[0]['done_ns'])-35}～{int(tasks[1]['start_ns'])+35} ns：有依赖任务的实际交接。",
                 f"- {int(tasks[3]['done_ns'])-35}～{int(tasks[4]['start_ns'])+35} ns：中间任务的实际交接。",
                 f"- {tasks[6]['start_ns']}～{tasks[6]['done_ns']} ns：DW7反复取数、分批计算、最后写回。",
                 '', '## 每行解释', '', '|行|信号|解释|', '|---|---|---|']
    schedule += [f'|{i}|{name}|{meaning}|' for i,(name,_,meaning) in enumerate(VIEWS['timing'],1)]
    schedule += ['', '每任务各阶段周期数见 phase_cycles.csv；ram_wait是其他阶段的一部分，不能再加一次。',
                 '这些是RTL功能仿真的周期关系，时钟周期在Testbench设为10ns，并非布局布线后的最高频率结论。']
    (OUT/'timing_guide.md').write_text('\n'.join(schedule)+'\n',encoding='utf-8')
    final_events=[row for row in outputs if int(row['task'])==8]
    with (OUT/'features_comparison.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.writer(stream);writer.writerow(['index','address_hex','write_request_ns','expected','actual'])
        for i,event in enumerate(final_events):
            require(int(event['index'])==i and int(event['address'])==0x18001+i,'final feature order')
            writer.writerow([i,f'0x{0x18001+i:08X}',event['time_ns'],int(goldens[-1].reshape(-1)[i]),actual[i] if actual[i]<128 else actual[i]-256])
    coverage={'array_tasks':len(layers),'int8_endpoint_values':sum(int(np.sum((x==-128)|(x==127))) for x in goldens)}
    doc=['# 纯脉动阵列：完整任务链波形','','当前硬件仅支持普通Conv和Depthwise。每条任务都使用同一8×8阵列。',
         '没有独立卷积、激活、ADD、COPY、FINAL_OUTPUT通路；最后一层Conv直接写出128维INT8。',
         'MMIO只提交任务表地址和条数，CONTROL=0x3D；算子配置只能来自32字节RAM描述符。',
         '描述符OP仅0/1，参数[31:20]必须为0；原直接启动方式报ERROR，5个旧算子配置寄存器读0、写无效。',
         '',f'本次逐层比较{expected_bytes}个INT8结果均通过。时序交接、阶段周期见 timing_guide.md。',
         '', '|任务|算子|输入C×H×W → 输出|开始ns|完成ns|输出地址|','|---|---|---|---|---|---|']
    for layer,task in zip(layers,tasks):
        shape='×'.join(map(str,output_shape(layer)))
        doc.append(f"|{task['task']}|{layer['op']} {layer['kernel']}×{layer['kernel']} s{layer['stride']} p{layer['padding']}|{layer['in_channels']}×{layer['height']}×{layer['width']} → {shape}|{task['start_ns']}|{task['done_ns']}|0x{layer['output_addr']:X}|")
    doc += ['',f"STATUS.DONE在{highs('status_done')[0]} ns置1。末层Conv从{tasks[-1]['start_ns']} ns开始。",
            'final_output_issue表示末层卷积的输出写请求，不是独立FINAL算子。',
            '输出序号为提交写请求的顺序；末层按输出通道顺序写0x18001～0x18080。',
            '', '|序号|写请求ns|预期值|','|---|---|---|']
    for event in final_events[:8]+final_events[-2:]:doc.append(f"|{event['index']}|{event['time_ns']}|{event['value']}|")
    for view,signals in VIEWS.items():
        doc += ['',f'## {view}.gtkw 每行含义','','|行|信号|解释|','|---|---|---|']
        doc += [f'|{i}|{name}|{meaning}|' for i,(name,_,meaning) in enumerate(signals,1)]
    doc += ['', '输入/控制看上升沿前，结果看上升沿后；两级ready分别表示接收命令和RAM完成，不能混用。',
            '本例仅使用Conv/DW；新增激活、残差等算子的并行时序请运行operator_wave.py。']
    (OUT/'guide.md').write_text('\n'.join(doc)+'\n',encoding='utf-8')
    result=dict(status='passed',tasks=9,layer_bytes=expected_bytes,feature_bytes=128,done_ns=highs('status_done')[0],
                final_task_start_ns=int(tasks[-1]['start_ns']),first_features=[int(x) for x in goldens[-1].reshape(-1)[:8]],coverage=coverage)
    (OUT/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2));print(f'Wave: {wave}\nGuide: {OUT / "guide.md"}',flush=True)
    if args.open:
        suite=Path(r'D:\ke\fpga\oss-cad-suite-windows-x64-20260811\oss-cad-suite')
        viewer=shutil.which(os.environ.get('GTKWAVE','gtkwave')) or str(suite/'bin'/'gtkwave.exe')
        base=Path(viewer).resolve().parent.parent;env=dict(os.environ)
        env['PATH']=os.pathsep.join([str(base/'bin'),str(base/'lib'),env.get('PATH','')])
        if os.name=='nt':
            env['GTK_EXE_PREFIX']=str(base);env['GTK_DATA_PREFIX']=str(base)
            cache=base/'lib'/'gdk-pixbuf-2.0'/'2.10.0'/'loaders.cache'
            if cache.is_file():env['GDK_PIXBUF_MODULE_FILE']=str(cache)
        with (OUT/'gtkwave.log').open('w') as log:
            process=subprocess.Popen([viewer,'-f',str(wave),'-a',str(OUT/f'{args.view}.gtkw'),'-4','do_initial_zoom_fit 1'],env=env,stdout=log,stderr=subprocess.STDOUT)
            try:code=process.wait(timeout=2)
            except subprocess.TimeoutExpired:print(f'GTKWave started PID {process.pid}: {args.view}')
            else:raise RuntimeError(f'GTKWave exited {code}; see {OUT / "gtkwave.log"}')


if __name__=='__main__':main()
