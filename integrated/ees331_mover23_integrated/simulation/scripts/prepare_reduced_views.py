"""Prepare named operator states and a load-checkable GTKWave session."""
from pathlib import Path
import json,csv,shutil,sys,os
SIM=Path(__file__).resolve().parents[1];BASE=SIM.parent
active=os.environ.get('SOC_RUN_DIR',json.loads((SIM/'build/reduced_soc_active.json').read_text())['run_dir'])
if active.startswith('/mnt/d/'):active='D:/'+active[len('/mnt/d/'):]
run=Path(active);which=sys.argv[1] if len(sys.argv)>1 else 'full';src=run/which
out=BASE/'deliverables'/os.environ.get('SOC_DELIVERY_NAME','reduced_cnn_single_20261112');out.mkdir(parents=True,exist_ok=True)
shutil.copyfile(src/'soc_states.fst',out/(which+'_states.fst'))
for f in ('metrics.json','events.csv','output_timing.csv','outputs.bin'):
 if (src/f).exists():shutil.copyfile(src/f,out/(which+'_'+f))
units=['K3_'+str(i) for i in range(2)]+['K1_'+str(i) for i in range(6)]+['POST_0','POST_1','ADD','PAD']
signals=[];lines=['[*]','[dumpfile] "'+which+'_states.fst"','[size] 1800 1050','[signals_width] 460','[sst_width] 230']
def group(name):lines.extend(['@200','-'+name])
def sig(name,bits=1,color=3,alias=None,decimal=False):
 full='SOC.'+name+(('['+str(bits-1)+':0]') if bits>1 else '')
 lines.extend(['@'+('24' if decimal else '22' if bits!=1 or 'TEXT' in name else '28'),'[color] '+str(color), ('+{'+alias+'} ' if alias else '')+full]);signals.append(full)
group('CPU AND PS')
for n in ('RESET_RELEASED','PS_MAILBOX_READ','PS_MAILBOX_WRITE','CPU_WRITE_CNN','CPU_RAM_READ','CPU_RAM_WRITE'):sig(n,color=2)
for n in ('CPU_LAST_CFG_ADDR','CPU_LAST_CFG_DATA'):sig(n,32,2)
group('CNN AND MEMORY')
for n in ('CNN_RUNNING','CNN_COMPUTE_DONE','CNN_ERROR','MEMORY_FAULT'):sig(n)
for n in ('MEMORY_STATE_TEXT','MOVER_STATE_TEXT'):sig(n,color=5)
for n in ('DDR_RETURNING_DATA','DDR_SENDING_DATA'):sig(n,color=6)
sig('COMPLETED_TASKS',11,3,decimal=True)
for n in ('PAGE_MISSES','DDR_READ_BYTES','DDR_WRITE_BYTES'):sig(n,32,5,decimal=True)
group('INDIVIDUAL OPERATOR STATES')
for i,u in enumerate(units):sig(u+'.STATE_TEXT',color=3+(i//2)%4,alias=u+'_STATE')
view=out/(which+'_states.gtkw');view.write_text('\n'.join(lines)+'\n')
(out/(which+'_states_signals.json')).write_text(json.dumps(signals,indent=2)+'\n')
gtkw=Path('D:/code/FPGA1/cpu_control (2)/cpu_control/tools/gtkwave/portable/gtkwave64/bin/gtkwave.exe')
(out/('open_'+which+'.cmd')).write_text('@echo off\ncd /d "%~dp0"\nstart "" "'+str(gtkw)+'" "'+which+'_states.fst" "'+view.name+'"\n')
events=list(csv.DictReader((src/'events.csv').open()))
cfg_end=next(int(e['cycle']) for e in events if e['event']=='INPUT_READY')
first_k1=next((int(e['cycle']) for e in events if e['event']=='START' and 2<=int(e['unit'])<8),0)
end=json.loads((src/'metrics.json').read_text())['cycles']*10000
windows={which+'_states':(0,end),which+'_cpu_config':(0,(cfg_end+1000)*10000),which+'_operator_detail':(first_k1*10000,(first_k1+128)*10000)}
for name,(begin,finish) in windows.items():
 target=out/(name+'.gtkw')
 if target!=view:target.write_bytes(view.read_bytes())
 wave=which+'_states.fst'
 if which=='full' and name!=which+'_states':
  suffix=name[len('full_'):];wave=name+'.fst'
  shutil.copyfile(src/('soc_'+suffix+'.fst'),out/wave)
  target.write_text(target.read_text().replace(which+'_states.fst',wave))
 tcl='set out [file dirname [file normalize [info script]]]\n'
 tcl+='gtkwave::setZoomRangeTimes %d %d\n'%(begin,finish)
 tcl+='gtkwave::/View/Scale_To_Time_Dimension/'+('ms' if finish-begin>1000000000 else 'us')+'\n'
 tcl+='gtkwave::/Edit/Set_Trace_Max_Hier 1\n'
 tcl+='gtkwave::/File/Write_Save_File_As [file join $out '+target.name+']\n'
 tcl+='set shown [gtkwave::getDisplayedSignals]\nset log [open [file join $out validation_'+name+'.log] w]\n'
 tcl+='puts $log "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"\n'
 tcl+='foreach s $shown {puts $log $s}\n'
 tcl+='if {[llength $shown] == '+str(len(signals))+'} {puts $log "PASS GTKWave 12-operator view"} else {puts $log "FAIL signal count"}\n'
 tcl+='close $log\ngtkwave::/File/Quit\n';(out/('verify_'+name+'.tcl')).write_text(tcl)
 if target!=view:(out/('open_'+name+'.cmd')).write_text('@echo off\ncd /d "%~dp0"\nstart "" "'+str(gtkw)+'" "'+wave+'" "'+target.name+'"\n')
print(out, 'signals='+str(len(signals)))
