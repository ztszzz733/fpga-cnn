"""Trace MMIO -> descriptor FIFO -> configuration -> buffer loading -> real array."""
import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from systolic_wave import wrap

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build'/'task_setup_wave'


def signal(name, description, bits=1, fmt='28'):
    return (name if bits==1 else f'{name}[{bits-1}:0]',fmt,description)


def dec(name, description, bits=32):
    return signal(name,description,bits,'24')


def signed(name, description, bits=8):
    return signal(name,description,bits,'420')


def hexword(name, description):
    return signal(name,description,32,'22')


VIEWS={
    'queue':[
        signal('clk','时钟：每 10 ns 一个周期'),signal('rst_n','0 复位；1 正常工作'),
        signal('mmio_we','外部 CPU/Testbench 正在写 MMIO'),
        hexword('mmio_addr','MMIO 寄存器地址'),hexword('mmio_wdata','写入 MMIO 的 32 bit 数据'),
        signal('mmio_ready','MMIO 请求可在当前上升沿被接受'),
        signal('queue_start','寄存器产生的启动脉冲，启动整条队列'),
        signal('queue_active','任务队列正在处理'),dec('queue_state','队列状态编号，见下文',4),
        dec('desc_word','当前描述符的第几个 32 bit 字：0～7',3),
        signal('mem_read','RAM 读请求，保持到 ready'),hexword('mem_addr','外部 RAM 对齐字地址'),
        signal('mem_ready','当前 RAM 请求在本上升沿完成'),hexword('mem_rdata','RAM 返回的 32 bit 字'),
        signal('desc_valid','完整 256 bit 描述符已拼好'),signal('desc_ready','FIFO 可以接收描述符'),
        dec('queue_buffered','FIFO 中当前等待执行的任务数'),
        signal('exec_start','当前任务出队，启动一次算子，配置在该沿锁存'),
        dec('task_op','队头任务的算子编号；仅在 exec_start 时采样',4),
        hexword('cfg_input','卷积控制器已锁存的输入地址'),hexword('cfg_output','已锁存的输出地址'),
        hexword('cfg_weight','已锁存的权重地址'),hexword('cfg_bias','已锁存的 bias 地址'),
        hexword('cfg_size','已锁存的高 16 位 height、低 16 位 width'),
        hexword('cfg_channels','已锁存的高 16 位输出通道、低 16 位输入通道'),
        hexword('cfg_param','已锁存的 kernel/stride/padding/量化/激活配置'),
        signal('core_busy','加速器或任务队列忙'),dec('queue_completed','已完成的任务数'),
        signal('status_done','MMIO STATUS.DONE 粘滞位'),signal('status_error','MMIO STATUS.ERROR 粘滞位')],
    'buffers':[
        signal('clk','时钟'),signal('exec_start','卷积任务开始，锁存描述符配置'),
        dec('conv_state','卷积控制器状态编号，见下文',4),
        signal('read_request','控制器向读取缓存提交一次读请求'),signal('read_ready','读取缓存可以接收请求'),
        hexword('read_address','需要的实际字节地址；与外部对齐字地址不同'),
        signal('mem_read','读取缓存未命中时发出的外部 RAM 读请求'),
        hexword('mem_addr','外部 RAM 的 4 字节对齐地址'),signal('mem_ready','外部 RAM 已完成当前请求'),
        hexword('mem_rdata','外部 RAM 返回的原始 32 bit 数据'),
        signal('read_done','读取缓存已给出需要的数据，可写缓冲'),
        hexword('read_data','读取缓存返回：一个 INT8 字节或完整 INT32 bias'),
        signal('bias_we','1：在本上升沿把 wr_bias 写入 bias[wr_row]'),
        signal('a_we','1：在本上升沿把 wr_value 写入权重 A[wr_row][wr_k]'),
        signal('b_we','1：在本上升沿把 wr_value 写入窗口 B[wr_row][wr_col][wr_k]'),
        dec('wr_row','写缓冲的行索引；普通卷积 B 缓冲只用行 0',3),
        dec('wr_col','写 B 缓冲的输出位置索引',3),dec('wr_k','本块内第几项乘加数据',3),
        signed('wr_value','送往 A/B 缓冲的有符号 INT8 数据'),signed('wr_bias','送往 Bias 缓冲的 INT32 数据',32),
        dec('tile_rows','本块有效 PE 行数：2',4),dec('tile_cols','本块有效 PE 列数：2',4),
        dec('tile_depth','本批乘加项数：3',4),signal('tile_dw','0 普通卷积，1 Depthwise'),
        signal('tile_accumulate','0 从 bias 开始，1 保留上一批累加值'),
        signal('tile_start','控制器 RUN_START 状态产生，启动本块计算'),
        signal('tile_busy','当前块正在初始化或计算'),signal('array_ce','阵列允许推进'),
        signal('load_bias','PE 装载 bias 的使能'),signal('tile_done','当前块完成脉冲')],
    'array':[
        signal('clk','时钟'),signal('rst_n','复位'),signal('tile_start','启动当前块'),
        signal('tile_busy','当前块忙'),signal('array_ce','阵列推进使能'),signal('load_bias','PE 装入 bias'),
        dec('run_tick','RUN 拍编号；核对操作数时看沿前值',6),signal('tile_done','当前块完成')]
}
for cell in ('00','01','10','11'):
    VIEWS['array'] += [signal('fire'+cell,f'PE{cell} 本上升沿是否有效乘加'),
                      signed('w'+cell,f'PE{cell} 当前权重'),signed('x'+cell,f'PE{cell} 当前输入'),
                      signed('acc'+cell,f'PE{cell} 当前 INT32 累加值',32)]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=ROOT/'examples'/'systolic_wave.json')
    parser.add_argument('--open',action='store_true')
    parser.add_argument('--view',choices=VIEWS,default='queue')
    args=parser.parse_args()
    case=json.loads(args.input.read_text(encoding='utf-8-sig'))
    for key in ('weights','input_windows'):
        require(len(case[key])==2 and all(len(row)==3 for row in case[key]),f'{key}: expected 2x3')
        require(all(type(v) is int and -128<=v<=127 for row in case[key] for v in row),f'{key}: expected INT8')
    require(len(case['bias'])==2 and all(type(v) is int and -2**31<=v<2**31 for v in case['bias']),'expected two INT32 biases')
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'result.json').write_text(json.dumps({'status':'running'}),encoding='utf-8')
    (OUT/'case_used.json').write_text(json.dumps(case,indent=2),encoding='utf-8')
    descriptor=[0x100,0x101,0x401,0x201,0x300,0x10002,0x20003,0x11]
    def words(values):
        return b''.join((v&0xffffffff).to_bytes(4,'little') for v in values)
    # CHW layout: channel0 has positions 4,7; channel1 5,8; channel2 6,9.
    input_chw=[case['input_windows'][c][k] for k in range(3) for c in range(2)]
    segments=[(0x101,input_chw),(0x201,sum(case['weights'],[])),(0x300,words(case['bias'])),(0x1000,words(descriptor))]
    (OUT/'ram.hex').write_text(''.join(f'@{address:08x}\n'+''.join(f'{v&255:02x}\n' for v in data) for address,data in segments),encoding='ascii')
    subprocess.run([sys.executable,str(ROOT/'scripts'/'run_tests.py'),'task_setup_wave'],check=True)
    with (OUT/'events.csv').open() as file:
        events=[dict(time=int(row['time_ns']),kind=row['kind'],a=int(row['a']),b=int(row['b']),c=int(row['c']),v=int(row['value_hex'],16)) for row in csv.DictReader(file)]
    def group(kind):return [e for e in events if e['kind']==kind]
    desc=group('DESC_READ')
    require([(e['a'],e['v']) for e in desc]==[(0x1000+4*i,v) for i,v in enumerate(descriptor)],'descriptor read mismatch')
    expected_mmio=[(0x40000008,0x1000),(0x40000018,1),(0x40000000,0x3d)]
    require([(e['a'],e['v']) for e in group('MMIO')]==expected_mmio,'MMIO launch mismatch')
    for name in ('QUEUE_START','FIFO_PUSH','DISPATCH','TILE_START','LOAD_BIAS','TILE_DONE','EXEC_DONE','QUEUE_DONE'):
        require(len(group(name))==1,f'expected one {name}')
    def signed32(v):return v-2**32 if v>=2**31 else v
    require([(e['a'],signed32(e['v'])) for e in group('BIAS')]==list(enumerate(case['bias'])),'bias buffer mismatch')
    require([(e['a'],e['c'],signed32(e['v'])) for e in group('WEIGHT')]==[(r,k,case['weights'][r][k]) for r in range(2) for k in range(3)],'weight buffer mismatch')
    require([(e['a'],e['b'],e['c'],signed32(e['v'])) for e in group('INPUT')]==[(0,c,k,case['input_windows'][c][k]) for c in range(2) for k in range(3)],'window buffer mismatch')
    require(desc[-1]['time']<group('FIFO_PUSH')[0]['time']<group('DISPATCH')[0]['time']<group('BIAS')[0]['time'],'task dispatch order')
    require(group('BIAS')[-1]['time']<group('WEIGHT')[0]['time']<group('INPUT')[0]['time'],'buffer load order')
    require(group('INPUT')[-1]['time']<group('TILE_START')[0]['time']<group('LOAD_BIAS')[0]['time'],'array started before data ready')
    with (OUT/'actual.csv').open() as file:
        samples=[{key:int(value) for key,value in row.items()} for row in csv.DictReader(file)]
    require(len(samples)==17,'expected 17 RUN cycles')
    accum={(r,c):case['bias'][r] for r in range(2) for c in range(2)}
    comparisons=[]
    for tick,sample in enumerate(samples):
        require(sample['tick']==tick,'RUN tick sequence')
        for r in range(2):
            for c in range(2):
                cell=f'{r}{c}';k=tick-r-c;valid=int(0<=k<3)
                require(sample['fire'+cell]==valid,f'PE{cell} valid mismatch tick {tick}')
                if valid:
                    w=case['weights'][r][k];x=case['input_windows'][c][k]
                    require(sample['w'+cell]==w and sample['x'+cell]==x,f'PE{cell} operand mismatch tick {tick}')
                    accum[r,c]=wrap(accum[r,c]+w*x)
                require(sample['acc'+cell]==accum[r,c],f'PE{cell} accumulator mismatch tick {tick}')
                comparisons.append(dict(time_ns=sample['time_ns'],tick=tick,pe=cell,expected=accum[r,c],actual=sample['acc'+cell]))
    with (OUT/'comparison.csv').open('w',newline='',encoding='utf-8-sig') as file:
        writer=csv.DictWriter(file,fieldnames=list(comparisons[0]));writer.writeheader();writer.writerows(comparisons)
    with (OUT/'output.csv').open() as file:actual=[int(row['value']) for row in csv.DictReader(file)]
    expected=[max(-128,min(127,accum[r,c])) for r in range(2) for c in range(2)]
    require(actual==expected,'final RAM bytes mismatch')
    require(len(group('RAM_WRITE'))==4,'expected four output byte writebacks')
    wave=OUT/'task_setup.vcd'
    for name,signals in VIEWS.items():
        (OUT/f'{name}.gtkw').write_text(f'[dumpfile] "{wave.as_posix()}"\n[timestart] 0\n[size] 1500 1000\n[signals_width] 250\n'
            +''.join(f'@{fmt}\ntb_task_setup_wave.{sig}\n' for sig,fmt,_ in signals),encoding='utf-8')
    doc=['# 从任务到阵列：波形对照','','所有事件时间是接受操作的时钟上升沿；在沿前看控制/数据，在沿后看锁存结果。',
         '这是完整 top + RAM 的单任务队列；输入、权重和 bias 与 systolic_wave.json 一致。',
         '本例 Conv1x1：H=1、W=2、IC=3、OC=2、stride=1、padding=0、quant_shift=0、无激活。',
         '由于加入了任务读取和 RAM 等待，计算时间与独立阵列例子的 185 ns 等时间不同。',
         '', '## 阶段时间', '', '| 时间 ns | 事件 | 详情 |','|---|---|---|']
    descriptions={'QUEUE_START':'队列接受 START','FIFO_PUSH':'完整描述符入 FIFO','DISPATCH':'出队并锁存卷积配置',
                  'TILE_START':'tile 接受 start，rows=2/cols=2/depth=3','LOAD_BIAS':'PE 装入 bias',
                  'TILE_DONE':'控制器接受 tile_done','EXEC_DONE':'队列接受当前卷积完成','QUEUE_DONE':'STATUS 将置 DONE'}
    for e in events:
        kind=e['kind'];detail=''
        if kind=='MMIO':detail=f"地址 0x{e['a']:08X}，数据 0x{e['v']:08X}"
        elif kind in ('DESC_READ','RAM_READ','RAM_WRITE'):detail=f"地址 0x{e['a']:08X}，数据 0x{e['v']:08X}"
        elif kind=='BIAS':detail=f"bias[{e['a']}] = {signed32(e['v'])}"
        elif kind=='WEIGHT':detail=f"A[{e['a']}][{e['c']}] = {signed32(e['v'])}"
        elif kind=='INPUT':detail=f"B[0][{e['b']}][{e['c']}] = {signed32(e['v'])}"
        else:detail=descriptions.get(kind,'')
        doc.append(f"| {e['time']} | {kind} | {detail} |")
    doc += ['', '## 计算阶段', '', '| 上升沿 ns | 沿前 tick | acc00 | acc01 | acc10 | acc11 |','|---|---|---|---|---|---|']
    for sample in samples[:6]:
        doc.append('| '+' | '.join(str(sample[k]) for k in ('time_ns','tick','acc00','acc01','acc10','acc11'))+' |')
    doc += ['',f'最终 RAM 输出：{actual}；所有 68 项 PE 结果和 14 次缓冲写入均已核对。',
            '', '## 每行信号含义']
    for name,signals in VIEWS.items():
        doc += ['',f'### {name}.gtkw','','| 行 | 信号 | 含义 |','|---|---|---|']
        doc += [f'| {i} | {sig} | {desc} |' for i,(sig,_,desc) in enumerate(signals,1)]
    doc += ['', '## 状态编号', '',
            'queue_state：0 IDLE，1 VALIDATE，2 FILL（读描述符），3 DISPATCH，4 RUN，5 RELEASE，6 DONE，7 ERROR。',
            'conv_state：0 IDLE，1 CHECK，2/3 BIAS_REQ/WAIT，4/5 A_REQ/WAIT，6/7 B_REQ/WAIT，8 RUN_START，9 RUN_WAIT，10 POST，11/12 WRITE_REQ/WAIT，13 DONE，14 ERROR。',
            '', '## 观察注意', '',
            '- exec_start 的沿前看任务，沿后看 cfg_*；FIFO 出队后队头输出可归零，已锁存配置仍有效。',
            '- read_address 是字节地址；mem_addr 是对齐后的 32 bit 字地址。例如权重 0x201 对应 mem_addr=0x200。',
            '- read_data 的 INT8 字节按低 8 位返回：0x000000FF 在 wr_value 中解释为 -1。',
            '- read_done 不一定对应新的一次 mem_read；读取缓存可能命中。bias_we/a_we/b_we 为 1 的沿才写缓冲。',
            '- tile_rows/cols/depth 提前出现不代表已经启动；tile_start=1 的上升沿才接受该配置。',
            '- tile_done 与 exec_done、STATUS.DONE 是不同层级的完成信号。表内 TILE_DONE 时间是下一层接受该脉冲的上升沿。',
            '- 普通卷积的 B 缓冲只写 wr_row=0，后续输入沿阵列向下传播复用。',
            '- 缓冲开始装载前的 X 是未初始化内容；只在对应写使能或 fire 为 1 时解读数据。']
    (OUT/'guide.md').write_text('\n'.join(doc)+'\n',encoding='utf-8')
    (OUT/'result.json').write_text(json.dumps({'status':'passed','descriptor_words':8,'buffer_writes':14,'pe_samples':68,'outputs':actual,
        'milestones':{name:group(name)[0]['time'] for name in descriptions}},indent=2),encoding='utf-8')
    print(f'PASS: 8 descriptor words, 14 buffer writes, 68 PE samples, 4 RAM outputs {actual}')
    print(f'Waveform: {wave}\nGuide: {OUT / "guide.md"}')
    for name in descriptions:print(f'{name}: {group(name)[0]["time"]} ns')
    if args.open:
        suite=Path(r'D:\ke\fpga\oss-cad-suite-windows-x64-20260811\oss-cad-suite')
        viewer=shutil.which(os.environ.get('GTKWAVE','gtkwave')) or str(suite/'bin'/'gtkwave.exe')
        tool_root=Path(viewer).resolve().parent.parent;env=dict(os.environ)
        env['PATH']=os.pathsep.join([str(tool_root/'bin'),str(tool_root/'lib'),env.get('PATH','')])
        if os.name=='nt':
            env['GTK_EXE_PREFIX']=str(tool_root);env['GTK_DATA_PREFIX']=str(tool_root)
            cache=tool_root/'lib'/'gdk-pixbuf-2.0'/'2.10.0'/'loaders.cache'
            if cache.is_file():env['GDK_PIXBUF_MODULE_FILE']=str(cache)
        with (OUT/'gtkwave.log').open('w') as log:
            process=subprocess.Popen([viewer,'-f',str(wave),'-a',str(OUT/f'{args.view}.gtkw'),'-4','do_initial_zoom_fit 1'],env=env,stdout=log,stderr=subprocess.STDOUT)
            try:code=process.wait(timeout=2)
            except subprocess.TimeoutExpired:print(f'GTKWave started: PID {process.pid} ({args.view} view)')
            else:raise RuntimeError(f'GTKWave exited ({code}); see {OUT / "gtkwave.log"}')


if __name__=='__main__':main()
