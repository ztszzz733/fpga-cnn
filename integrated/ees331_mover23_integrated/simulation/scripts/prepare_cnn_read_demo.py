from pathlib import Path
import subprocess,json,csv
SIM=Path(__file__).resolve().parents[1];BASE=SIM.parent
run=Path(json.loads((SIM/'build/mover_speed_soc_active.json').read_text())['run_dir'])
g=Path('/mnt/d/code/FPGA1/.neureka_build/neureka/verilator/include/gtkwave');z=SIM/'.tools/zlib-linux/usr'
out=BASE/'deliverables/cnn_read_demo_20261112';out.mkdir(parents=True,exist_ok=True)
events=list(csv.DictReader((run/'full/events.csv').open()));start=next(int(e['cycle']) for e in events if e['event']=='START' and int(e['unit'])==2)
begin=(start+150)*10000;end=(start+1174)*10000
objects=[SIM/'build/state_export_tool'/(n+'.o') for n in ('fstapi','fastlz','lz4')]
exe=SIM/'build/reduced_state_export/export_cnn_read_demo'
subprocess.run(['c++','-O2','-std=c++17','-I'+str(g),'-I'+str(z/'include'),str(SIM/'scripts/export_cnn_read_demo.cpp'),*map(str,objects),str(z/'lib/x86_64-linux-gnu/libz.a'),'-o',str(exe)],check=True)
subprocess.run([str(exe),str(run/'full/soc_reduced.fst'),str(out/'cnn_reads.fst'),str(begin),str(end),str(out/'result.json')],check=True)
r=json.loads((out/'result.json').read_text());signals=[];lines=['[*]','[dumpfile] "cnn_reads.fst"','[size] 1800 1000','[signals_width] 430']
def sig(n,bits=1,color=3):
 full='CNN_READ.'+n+('['+str(bits-1)+':0]' if bits>1 else '');signals.append(full)
 lines.extend(['@'+('22' if bits>1 or n.endswith('STATE') else '28'),'[color] '+str(color),full])
for n in ('CLK','K1_0_STATE','K1_0_READ_REQUEST','K1_0_READ_ACCEPTED','K1_0_READ_DATA_VALID'):sig(n)
for n in ('K1_0_READ_ADDR','K1_0_READ_DATA'):sig(n,32,2)
sig('K1_0_READ_BYTES',3,2)
for n in ('MEMORY_STATE','MOVER_STATE','DDR_DATA_VALID','DDR_DATA_ACCEPTED'):sig(n,color=5)
for n in ('RAW_CNN_VALID','RAW_CNN_READY','RAW_CNN_WRITE','RAW_CNN_RESPONSE'):sig(n,color=4)
(out/'cnn_reads.gtkw').write_text('\n'.join(lines)+'\n')
exe_win=r'D:\code\FPGA1\cpu_control (2)\cpu_control\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe'
(out/'open_reads.cmd').write_text('@echo off\ncd /d "%~dp0"\nstart "" "'+exe_win+'" "cnn_reads.fst" "cnn_reads.gtkw"\n')
a=r['first_accept_ps'];tcl='set out [file dirname [file normalize [info script]]]\n'
tcl+='gtkwave::setZoomRangeTimes %d %d\n'%(r['first_return_ps']-100000,r['first_return_ps']+800000)
tcl+='gtkwave::/View/Scale_To_Time_Dimension/us\ngtkwave::/Edit/Set_Trace_Max_Hier 1\n'
tcl+='gtkwave::setMarker %d\n'%r['first_return_ps']
tcl+='gtkwave::/File/Write_Save_File_As [file join $out cnn_reads.gtkw]\n'
tcl+='set log [open [file join $out validation.log] w]\nset shown [gtkwave::getDisplayedSignals]\nputs $log "SIGNALS=[llength $shown]"\n'
tcl+='puts $log "DATA_VALID=[gtkwave::getTraceValueAtMarkerFromName {CNN_READ.K1_0_READ_DATA_VALID}]"\n'
tcl+='puts $log "READ_ADDR=[gtkwave::getTraceValueAtMarkerFromName {CNN_READ.K1_0_READ_ADDR[31:0]}]"\n'
tcl+='puts $log "READ_DATA=[gtkwave::getTraceValueAtMarkerFromName {CNN_READ.K1_0_READ_DATA[31:0]}]"\n'
tcl+='if {[llength $shown] == '+str(len(signals))+'} {puts $log "PASS CNN read view"} else {puts $log "FAIL"}\nclose $log\ngtkwave::/File/Quit\n'
(out/'verify.tcl').write_text(tcl)
print(json.dumps(r),flush=True)
