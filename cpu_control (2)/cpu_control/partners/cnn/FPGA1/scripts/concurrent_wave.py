"""Run real queued Conv/DW tasks and show streaming fetch + shared PE scheduling."""
import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from accelerator_wave import scan_wave

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build'/'concurrent_vectors'/'mixed'
SIGNALS=[
 ('clk','28','时钟，周期10ns'),
 ('queue_fetched[31:0]','24','已完整读回的描述符数；到1即可启动第一条'),
 ('context_start[1:0]','28','启动脉冲，bit0/bit1分别启动上下文0/1'),
 ('allocated[1:0]','28','任务占用上下文：11表示两条任务同时在途'),
 ('task_id0[31:0]','24','上下文0的任务编号，仅allocated[0]=1时有效'),
 ('task_id1[31:0]','24','上下文1的任务编号，仅allocated[1]=1时有效'),
 ('pe_mask0[7:0]','28','上下文0占用的物理行；00000011表示第0、1行'),
 ('pe_mask1[7:0]','28','上下文1占用的物理行；11111100表示第2～7行'),
 ('rows0[3:0]','24','上下文0获得的行数，每行8个PE'),
 ('rows1[3:0]','24','上下文1获得的行数，每行8个PE'),
 ('array_running[1:0]','28','各分区处于初始化/计算阶段；11表示两边都在运行'),
 ('macs0[31:0]','24','此时钟上升沿，上下文0实际乘加的PE数'),
 ('macs1[31:0]','24','此时钟上升沿，上下文1实际乘加的PE数；与macs0同时非0才是真正同拍计算'),
 ('context_done[1:0]','28','上下文完成脉冲；包含该任务最后一次写回完成'),
 ('queue_completed[31:0]','24','成功完成的任务总数，完成顺序可能不同于派发顺序'),
 ('fetch_phase','28','当前RAM事务属于任务读取，可与阵列计算重叠'),
 ('hazard_wait','28','队首任务与在途任务的RAM读写范围冲突，必须等待'),
 ('resource_wait','28','上下文或连续空闲PE行不足，队首任务等待'),
 ('ram_owner[3:0]','24','当前RAM事务归属：0取任务，1上下文0，2上下文1；无事务时仅保留旧值'),
 ('rd','28','RAM读请求'),('wr','28','RAM写请求'),('mready','28','RAM接受当前访问'),
 ('dut.regs.done_sticky','28','整个队列成功完成'),('dut.regs.error_sticky','28','错误，本示例应始终0')]

def rows(path):
    with path.open(encoding='utf-8-sig') as f:return list(csv.DictReader(f))

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--open',action='store_true');args=parser.parse_args()
    subprocess.run([sys.executable,str(ROOT/'scripts/run_tests.py'),'concurrent_queue','--waves'],check=True)
    events=rows(OUT/'events.csv');timing=rows(OUT/'timing.csv');comparison=rows(OUT/'comparison.csv')
    assert comparison and all(x['expected']==x['actual'] for x in comparison)
    starts={int(x['task']):x for x in events if x['event']=='DISPATCH'}
    ends={int(x['task']):x for x in events if x['event']=='DONE'}
    assert len(starts)==len(ends)==7 and int(starts[1]['time_ns'])<int(ends[0]['time_ns'])
    overlap=[x for x in timing if int(x['macs0'])>0 and int(x['macs1'])>0]
    assert overlap,'No real simultaneous MACs in the selected example'
    wave=OUT/'concurrent.vcd';save=OUT/'timing.gtkw'
    declared,_=scan_wave(wave)
    for name,_,_ in SIGNALS:
        assert 'tb_concurrent_queue.'+name in declared, f'Missing VCD signal: {name}'
    save.write_text(f'[dumpfile] "{wave.as_posix()}"\n[timestart] 0\n[size] 1600 1000\n[signals_width] 330\n'+
        ''.join(f'@{fmt}\ntb_concurrent_queue.{name}\n' for name,fmt,_ in SIGNALS),encoding='utf-8')
    doc=['# 边取任务、边执行、共享PE的波形','','运行 concurrent_wave.py --open 可打开 timing.gtkw。',
         '当前最多两条独立任务并发；按整行分配，每行8个PE。分配持续到该任务最后一次RAM写回完成。',
         '',f"任务0在{starts[0]['time_ns']} ns派发，任务1在{starts[1]['time_ns']} ns派发；任务0到{ends[0]['time_ns']} ns才完成。",
         f'本示例逐项比较{len(comparison)}个INT8结果全部一致，末层输出128维。',
         '', '|任务|上下文|分配行数|派发ns|完成ns|','|---|---|---|---|---|']
    for i in range(7):doc.append(f"|{i}|{starts[i]['context']}|{starts[i]['rows']}|{starts[i]['time_ns']}|{ends[i]['time_ns']}|")
    doc+=['','## 如何看出真的并行','',
          '先看 allocated=11，确认两条任务同时在途；再看两个PE掩码互不重叠。',
          'mask0=00000011、mask1=11111100时，分别对应2×8和6×8。',
          '两个macs都大于0的时钟沿，才表示两个任务真的同时做乘加。任务已分配但macs=0时可能正在等数据或写回。',
          f"本次有{len(overlap)}拍两边同时乘加，首次在{overlap[0]['time_ns']} ns。建议放大该时刻前后100ns。",
          'hazard_wait=1时，队首任务在等待数据冲突解除，即使还有空闲PE也不能越过依赖执行。',
          '派发顺序固定，独立任务可以先完成；queue_completed是完成总数，不是最后完成的任务编号。',
          '', '## 每行含义','','|行|信号|含义|','|---|---|---|']
    doc += [f'|{i}|{name}|{meaning}|' for i,(name,_,meaning) in enumerate(SIGNALS,1)]
    doc += ['','每个分区内部仍按取数→计算→写回运行；尚未实现同一任务块的双缓冲。',
            '外部RAM访问仍为串行仲裁，不能把两条任务同时在途理解为RAM同时完成两次访问。',
            '这些是RTL功能仿真的10ns周期，未经布局布线，不能作为芯片最高频率结论。']
    (OUT/'guide.md').write_text('\n'.join(doc)+'\n',encoding='utf-8')
    result=dict(status='passed',tasks=7,bytes_compared=len(comparison),simultaneous_mac_cycles=len(overlap),
                first_simultaneous_mac_ns=int(overlap[0]['time_ns']),wave=str(wave),guide=str(OUT/'guide.md'))
    (OUT/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
    if args.open:
        suite=Path(r'D:\ke\fpga\oss-cad-suite-windows-x64-20260811\oss-cad-suite')
        viewer=shutil.which(os.environ.get('GTKWAVE','gtkwave')) or str(suite/'bin/gtkwave.exe')
        base=Path(viewer).resolve().parent.parent;env=dict(os.environ)
        env['PATH']=os.pathsep.join([str(base/'bin'),str(base/'lib'),env.get('PATH','')])
        if os.name=='nt':
            env['GTK_EXE_PREFIX']=str(base);env['GTK_DATA_PREFIX']=str(base)
            cache=base/'lib/gdk-pixbuf-2.0/2.10.0/loaders.cache'
            if cache.exists():env['GDK_PIXBUF_MODULE_FILE']=str(cache)
        with (OUT/'gtkwave.log').open('w') as log:
            process=subprocess.Popen([viewer,'-f',str(wave),'-a',str(save),'-4','do_initial_zoom_fit 1'],env=env,stdout=log,stderr=subprocess.STDOUT)
            try:code=process.wait(timeout=2)
            except subprocess.TimeoutExpired:print(f'GTKWave started: {process.pid}')
            else:raise RuntimeError(f'GTKWave exited {code}')

if __name__=='__main__':main()
