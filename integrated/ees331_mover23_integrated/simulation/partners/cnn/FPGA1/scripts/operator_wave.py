"""Generate the heterogeneous scheduling waveform and independently checked results."""
import argparse,csv,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/operator_vectors'
UNITS=['阵列上下文0','阵列上下文1','ReLU6','ADD','ReLU','PReLU','MaxPool','Requant']
SIGNALS=[
('clk','28','时钟，10 ns 一周期'),
('queue_fetched[31:0]','24','已经完整读取的任务数；第一条读完即可启动'),
('dispatch_id[31:0]','24','本次选择的原始任务编号，只在 unit_start 非0时有效'),
('unit_start[7:0]','28','各执行单元的单周期启动脉冲，位编号见下表'),
('conv0_busy','28','阵列上下文0正在执行 Conv/DW/MatMul'),
('conv1_busy','28','阵列上下文1正在执行 Conv/DW/MatMul'),
('relu_busy','28','ReLU 单元正在读数、计算或写回'),
('relu6_busy','28','ReLU6 单元忙'),
('add_busy','28','残差 ADD 单元忙'),
('prelu_busy','28','PReLU 单元忙'),
('pool_busy','28','2x2 MaxPool 单元忙'),
('requant_busy','28','增强量化单元忙'),
('compute[7:0]','28','本上升沿实际进行计算的单元：阵列为有效PE乘加，标量为CALC阶段'),
('unit_done[7:0]','28','各单元任务完成，最后一笔RAM写回已经得到响应'),
('queue_completed[31:0]','24','成功完成任务总数，不代表连续完成到哪个任务编号'),
('hazard_wait','28','窗口里存在因数据冲突等待的任务，不表示其他单元都停止'),
('resource_wait','28','窗口里存在因目标单元/PE资源不足等待的任务'),
('ram_owner[3:0]','24','当前RAM事务：0读取任务；1~8对应单元0~7'),
('rd','28','RAM读请求'),('wr','28','RAM写请求'),('mready','28','当前RAM事务完成'),
('dut.regs.done_sticky','28','整个队列成功完成'),
('dut.regs.error_sticky','28','任务错误，本正常示例始终0')]
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--open',action='store_true');args=parser.parse_args()
    subprocess.run([sys.executable,str(ROOT/'scripts/run_tests.py'),'operator_queue','--waves'],cwd=ROOT,check=True)
    with (OUT/'comparison.csv').open() as f:comparisons=list(csv.DictReader(f))
    assert comparisons and all(x['expected']==x['actual'] for x in comparisons)
    with (OUT/'events.csv').open() as f:events=list(csv.DictReader(f))
    starts={int(x['task']):int(x['time_ns']) for x in events if x['event']=='DISPATCH'}
    ends={int(x['task']):int(x['time_ns']) for x in events if x['event']=='DONE'}
    summary=dict(line.split('=') for line in (OUT/'summary.txt').read_text().splitlines())
    assert starts[2]<starts[1] and starts[1]>=ends[0]
    from accelerator_wave import scan_wave
    wave=OUT/'operators.vcd';save=OUT/'operators.gtkw'
    declared,_=scan_wave(wave)
    for name,_,_ in SIGNALS:assert 'tb_operator_queue.'+name in declared,name
    save.write_text(f'[dumpfile] "{wave.as_posix()}"\n[timestart] 0\n[size] 1600 1000\n[signals_width] 300\n'+
        ''.join(f'@{fmt}\ntb_operator_queue.{name}\n' for name,fmt,_ in SIGNALS),encoding='utf-8')
    # The table is generated from observed events, never hardcoded cycle estimates.
    doc=['# 多算子并行波形','','先看各 busy 行的重叠，再看 compute 判断真正同拍计算。',
         'busy 包含取数、等待RAM、计算和写回；共享RAM每次只完成一笔访问。','',
         f'任务0 ReLU：{starts[0]}~{ends[0]} ns。任务1等待同一ReLU单元，直到 {starts[1]} ns 才启动。',
         f'任务2 ADD：{starts[2]} ns 已启动，越过了等待中的任务1。',
         f'最多同时在途 {summary["max_live"]} 条任务；阵列与标量同拍计算 {summary["array_vector_compute"]} 次。','',
         '|任务|单元|启动/ns|完成/ns|','|---|---|---:|---:|']
    for e in events:
        if e['event']=='DISPATCH':
            task=int(e['task']);doc.append(f'|{task}|{UNITS[int(e["unit"])]}|{starts[task]}|{ends[task]}|')
    doc+=['','|bit|执行单元|','|---|---|']+[f'|{i}|{name}|' for i,name in enumerate(UNITS)]
    doc+=['','|波形行|含义|','|---|---|']+[f'|{name}|{meaning}|' for name,_,meaning in SIGNALS]
    (OUT/'guide.md').write_text('\n'.join(doc)+'\n',encoding='utf-8')
    result=dict(status='passed',tasks=len(starts),bytes_compared=len(comparisons),
                **{k:int(v) for k,v in summary.items()},wave=str(wave),guide=str(OUT/'guide.md'))
    (OUT/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    if args.open:
        fallback=Path(r'D:\ke\fpga\oss-cad-suite-windows-x64-20260811\oss-cad-suite')
        viewer=shutil.which(os.environ.get('GTKWAVE','gtkwave')) or str(fallback/'bin/gtkwave.exe')
        base=Path(viewer).resolve().parent.parent;env=dict(os.environ)
        env['PATH']=os.pathsep.join([str(base/'bin'),str(base/'lib'),env.get('PATH','')])
        env['GTK_EXE_PREFIX']=env['GTK_DATA_PREFIX']=str(base)
        cache=base/'lib/gdk-pixbuf-2.0/2.10.0/loaders.cache'
        if cache.is_file():env['GDK_PIXBUF_MODULE_FILE']=str(cache)
        with (OUT/'gtkwave.log').open('w') as log:
            process=subprocess.Popen([viewer,'-f',str(wave),'-a',str(save),'-4','do_initial_zoom_fit 1'],
                                     cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            try:code=process.wait(timeout=2)
            except subprocess.TimeoutExpired:print('GTKWave opened')
            else:raise RuntimeError(f'GTKWave exited {code}')
if __name__=='__main__':main()
