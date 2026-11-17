from pathlib import Path
import json,re,subprocess,os,hashlib,sys,csv
from collections import deque
B=Path(__file__).resolve().parents[2];S=B/'simulation'
def local(s):return Path('D:/'+s[len('/mnt/d/'):] if s.startswith('/mnt/d/') else s)
R=local(json.loads((S/'build/pw8_linear_full_active.json').read_text())['run_dir'])
D=B/('deliverables/pw8_linear_full_'+R.name);assert (D/'summary.json').exists()
J=json.loads((R/'result.json').read_text());assert J['status']=='PASS'
W=D/'wave';W.mkdir(exist_ok=True)
E=Path('D:/code/FPGA1/cpu_control (2)/cpu_control/tools/gtkwave/portable/gtkwave64/bin')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def enum(n):
 s=(R/'new/source'/n).read_text();m=re.search(r'typedef\s+enum\s+logic\s*\[[^]]+\]\s*\{([^}]+)\}\s*state_t',s,re.S);assert m,n
 tokens=re.sub(r'//[^\n]*','',m[1]).split(',');return [x.strip() for x in tokens if x.strip()]
k3=enum('rtl/cnn_self/self_conv_spatial4_engine.sv');pw=enum('rtl/cnn_self/self_pw8_engine.sv');post=enum('rtl/cnn_quant/quant_post_pipe_engine.sv');pad=enum('rtl/cnn_quant/pad_hwc_engine.sv');mem=enum('rtl/cnn_ddr/cnn_paged_mover.sv');mover=enum('storage_v2/rtl/data_mover.sv')
tables={'v4':mem,'v5':mover}
for k in range(12):tables['v'+str(12+k)]=k3 if k<2 else pw if k<8 else post if k<11 else pad
def ascii_bits(s):return ''.join(f'{x:08b}' for x in s.encode('ascii').ljust(24,b' ')[:24])
values={code:[ascii_bits(s) for s in names] for code,names in tables.items()}
source=R/'new/full/control.vcd';target=R/'new/full/control_detail.vcd'
jobs=json.loads((D/'timeline_data.json').read_text())['runs']['new']['jobs']
chosen=next(x for x in jobs if x['kind']=='PW8' and x['width']==7)
first_work=None;time_ns=0;signal_defs={};header=True;changed=0
recent=deque();before={};selected=[2,1,4,5,7,6,8,9,10,12+chosen['unit_id']]
selected_codes={'v'+str(k) for k in selected};detail_header=[];window_started=False
def translated(code,bits):
 global changed
 if code in values:
  n=int(bits,2);bits=values[code][n] if n<len(values[code]) else ascii_bits('UNKNOWN_'+str(n));changed+=1
 return 'b'+bits+' '+code+'\n'
with source.open() as fin,target.open('w',newline='\n') as fout:
 for line in fin:
  if header:
   if line.startswith('$var '):
    toks=line.split();code=toks[3];name=toks[4];width=int(toks[2]);signal_defs[code]={'name':name,'width':width}
    if code in selected_codes:
     if code in tables:line=f'$var wire 192 {code} {name}_TEXT $end\n'
     detail_header.append(line)
   elif '$enddefinitions' in line:
    header=False;fout.write('$timescale 1ns $end\n$scope module soc $end\n'+''.join(detail_header)+'$upscope $end\n$enddefinitions $end\n')
  elif line.startswith('#'):
   time_ns=int(line[1:])
   if first_work is not None and time_ns>first_work+8640:break
   if window_started:fout.write(line)
  elif line.startswith('b'):
   bits,code=line[1:].split()
   if code not in selected_codes:continue
   if window_started:fout.write(translated(code,bits));continue
   recent.append((time_ns,code,bits))
   cutoff=max(chosen['begin']*10,time_ns-1600)
   while recent and recent[0][0]<cutoff:
    _,c,b=recent.popleft();before[c]=b
   if code=='v6' and chosen['begin']*10<=time_ns<=chosen['end']*10 and (int(bits,2)>>chosen['unit_id'])&1:
    first_work=time_ns;window_started=True;fout.write('#'+str(cutoff)+'\n')
    for c,b in before.items():fout.write(translated(c,b))
    for t,c,b in recent:fout.write('#'+str(t)+'\n'+translated(c,b))
assert len(signal_defs)==24 and first_work is not None
fst=W/'control.fst'
with (W/'conversion.log').open('w') as log:
 p=subprocess.run([str(E/'vcd2fst.exe'),str(source),str(fst)],stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW,timeout=240)
assert p.returncode==0 and fst.stat().st_size>0
detail_fst=W/'control_detail.fst'
with (W/'conversion_detail.log').open('w') as log:p=subprocess.run([str(E/'vcd2fst.exe'),str(target),str(detail_fst)],stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW,timeout=60)
assert p.returncode==0 and detail_fst.stat().st_size>0
main_order=[2,0,1,3,11,4,5,7,6,8,9,10,*range(12,24)]
detail_order=[2,1,4,5,7,6,8,9,10,12+chosen['unit_id']]
widths={int(code[1:]):v['width'] for code,v in signal_defs.items()};names={int(code[1:]):v['name'] for code,v in signal_defs.items()}
def width(k,mode):return 192 if mode=='pw8_detail' and 'v'+str(k) in tables else widths[k]
def name(k,mode):
 w=width(k,mode);return 'soc.'+names[k]+('_TEXT' if w==192 else '')+(f'[{w-1}:0]' if w>1 else '')
time_end=J['variants']['new']['full']['metrics']['cycles']*10
sessions={}
for mode,order,times in [('full',main_order,(0,time_end)),('pw8_detail',detail_order,(max(chosen['begin']*10,first_work-1600),first_work+8640))]:
 save=W/(mode+'.gtkw');tcl=W/('verify_'+mode+'.tcl');logname='validation_'+mode+'.log'
 selected_fst=fst if mode=='full' else detail_fst
 lines=['[*] PW8 full-image comparison; recorded RTL controls; detail ASCII names decoded from frozen source',f'[dumpfile] "{selected_fst.as_posix()}"',f'[savefile] "{save.as_posix()}"','[timestart] 0','[size] 1800 1050','[signals_width] 420','*-37.6 0 0 0','@200','-INPUT / EXECUTION / MEMORY']
 for k in order:
  flag='@22' if width(k,mode)==192 else '@28' if width(k,mode)==1 else '@24' if k==1 else '@28'
  color=2 if k<4 else 5 if k<6 else 3 if k<12 else 2 if k<14 else 3 if k<20 else 6
  lines += [flag,'[color] '+str(color),name(k,mode)]
 save.write_text('\n'.join(lines)+'\n',encoding='utf-8')
 tcl.write_text(f'''set out [file dirname [file normalize [info script]]]
gtkwave::setZoomRangeTimes {times[0]} {times[1]}
gtkwave::/View/Scale_To_Time_Dimension/{'ms' if mode=='full' else 'us'}
gtkwave::/Edit/Set_Trace_Max_Hier 1
gtkwave::/File/Write_Save_File_As [file join $out {mode}.gtkw]
set shown [gtkwave::getDisplayedSignals]
set log [open [file join $out {logname}] w]
puts $log "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"
foreach s $shown {{puts $log $s}}
if {{[llength $shown] == {len(order)} && [llength [lsort -unique $shown]] == {len(order)}}} {{puts $log "PASS GTKWave unique controls"}} else {{puts $log "FAIL signal count"}}
close $log
gtkwave::/File/Quit
''',encoding='utf-8')
 (W/('open_'+mode+'.cmd')).write_text('@echo off\nstart "" "'+str(E/'gtkwave.exe')+'" -f "%~dp0'+selected_fst.name+'" -a "%~dp0'+mode+'.gtkw"\n',encoding='utf-8')
 sessions[mode]={'signals':len(order),'signal_names':[name(k,mode) for k in order],'time_range_ns':times}
j={'status':'CONVERTED_NOT_YET_GTK_VALIDATED','fst_bytes':fst.stat().st_size,'fst_sha256':sha(fst),'detail_fst_bytes':detail_fst.stat().st_size,'raw_vcd_bytes':source.stat().st_size,'raw_vcd_sha256':sha(source),'readable_detail_vcd':str(target),'decoded_detail_state_updates':changed,'state_enums':tables,'chosen_pw8_node':chosen['node'],'first_mac_ns':first_work,'sessions':sessions}
(W/'wave_result.json').write_text(json.dumps(j,indent=2)+'\n')
(W/'validate.ps1').write_text('''$ErrorActionPreference = 'Stop'
$waveExe = 'EXE'
foreach ($viewName in @('full','pw8_detail')) {
 $dumpName = if ($viewName -eq 'full') { 'control.fst' } else { 'control_detail.fst' }
 $gtkwArguments = @('-f', ('"'+(Join-Path $PSScriptRoot $dumpName)+'"'), '-a', ('"'+(Join-Path $PSScriptRoot ($viewName+'.gtkw'))+'"'), '-S', ('"'+(Join-Path $PSScriptRoot ('verify_'+$viewName+'.tcl'))+'"'))
 $waveProcess = Start-Process -FilePath $waveExe -ArgumentList $gtkwArguments -WindowStyle Hidden -PassThru
 if (-not $waveProcess.WaitForExit(60000)) { Stop-Process -Id $waveProcess.Id; throw 'GTKWave verification timeout' }
 $verification = Get-Content -LiteralPath (Join-Path $PSScriptRoot ('validation_'+$viewName+'.log')) -Raw
 if ($verification -notmatch 'PASS GTKWave unique controls') { throw $verification }
 Write-Output $verification
}
'''.replace('EXE',str(E/'gtkwave.exe')),encoding='utf-8')
p=D/'README.md';text=p.read_text(encoding='utf-8');text+='''
## 打开本次控制波形

- `wave/open_full.cmd`：24根唯一信号，全程输入提交、任务完成、算子状态、MAC活动与共享存储握手。
- `wave/open_pw8_detail.cmd`：第一段7×7 PW8实际MAC附近1024拍，10根唯一信号，便于观察连续运算和等待。
- [波形记录及译码表](wave/wave_result.json)。GTKWave显示的`*_STATE_TEXT`来自实际RTL状态编号，按本次冻结源码的枚举译成ASCII；不是额外硬件状态。原始数值状态仍保留在运行目录`control.vcd`。

`MAC_RUN`表示PW8计算阶段，实际退休拍应结合`ACTUAL_WORK`对应位；计算阶段包含流水填充。`MEM_PENDING`表示已接收请求尚未应答，也可能和MAC重叠。详见上面的信号说明。
''';p.write_text(text,encoding='utf-8',newline='\n')
print(W);print(json.dumps(j,indent=2))
