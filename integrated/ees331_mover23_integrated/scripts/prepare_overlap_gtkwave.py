"""Select actual simulator signals and prepare a portable GTKWave session."""
import argparse,hashlib,json,re,shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def prepare(run):
    result=json.loads((run/'result.json').read_text())
    if result['tests'].get('overlap',{}).get('status')!='PASS':
        raise RuntimeError('A passing overlap simulation is required')
    source=run/'overlap/wave.vcd'
    out=ROOT/'deliverables/gtkwave_overlap';out.mkdir(parents=True,exist_ok=True)
    cnn='tb_soc_overlap.dut.u_cnn.'
    mapping={'clk':'tb_soc_overlap.sys_clk','queue_active':cnn+'queue_active','queue_done':cnn+'queue_done',
             'task_dispatch':cnn+'dispatch_id','unit_start':cnn+'unit_start','unit_busy':cnn+'unit_busy',
             'task_completed':cnn+'queue_completed','hazard_wait':cnn+'hazard_wait',
             'pe_fire_map':cnn+'pe_fire_map','bank_requests':cnn+'cnn_valid','bank_grants':cnn+'cnn_ready',
             'own_load_compute_count':'tb_soc_overlap.own_load_compute',
             'own_store_compute_count':'tb_soc_overlap.own_store_compute'}
    for i,prefix in enumerate(['systolic_path','systolic_path_1']):
        for name in ['full','producer','consumer','compute_active','ld_valid','ld_ready','st_valid','st_ready','ws']:
            mapping[f'ctx{i}_{name}']=cnn+prefix+'.engine.'+name
    text=source.read_text();header,body=text.split('$enddefinitions $end',1)
    scope=[];signals={}
    for kind,value in re.findall(r'\$(\w+)\s+(.*?)\s*\$end',header,re.S):
        parts=value.split()
        if kind=='scope':scope.append(parts[1])
        elif kind=='upscope':scope.pop()
        elif kind=='var':signals['.'.join(scope+[parts[3]])]=(int(parts[1]),parts[2])
    missing=set(mapping.values())-signals.keys()
    if missing:raise RuntimeError(f'Missing wave signals: {missing}')
    codes={signals[path][1] for path in mapping.values()}
    declarations=['$version Selected from real simulation; values unchanged $end','$timescale 1ps $end','$scope module soc_overlap $end']
    for name,path in mapping.items():
        width,code=signals[path]
        declarations.append(f'$var wire {width} {code} {name}'+(f' [{width-1}:0]' if width>1 else '')+' $end')
    declarations+=['$upscope $end','$enddefinitions $end']
    filtered=[];now=0;first=None;end=None;detail=None
    done_code=signals[cnn+'queue_done'][1];store_code=signals['tb_soc_overlap.own_store_compute'][1]
    for line in body.splitlines():
        line=line.strip()
        if not line:continue
        if line.startswith('#'):
            if end is not None:break
            now=int(line[1:]);first=now if first is None else first;filtered.append(line)
        elif line.startswith('$'):filtered.append(line)
        else:
            code=line.split()[-1] if line[0] in 'bBrR' else line[1:]
            if code in codes:filtered.append(line)
            if code==done_code and line[0]=='1':end=now
            if code==store_code and line[0]=='b' and int(line.split()[0][1:],2)>0 and detail is None:detail=now
    (out/'overlap.vcd').write_text('\n'.join(declarations+filtered)+'\n')
    session=['[*] 19 task overlap simulation; actual waveform','[dumpfile] "overlap.vcd"','[savefile] "overlap.gtkw"',
             f'[timestart] {max(first,detail-500000)}','[size] 1700 1100','[pos] 0 0','*-27 -1 '+' '.join(['-1']*26),
             '[sst_width] 200','[signals_width] 290','[sst_expanded] 0']
    for name,path in mapping.items():
        width,_=signals[path];session+=['@28' if width==1 else '@22','soc_overlap.'+name+(f'[{width-1}:0]' if width>1 else '')]
    (out/'overlap.gtkw').write_text('\n'.join(session)+'\n')
    launcher='@echo off\nsetlocal\ncd /d "%~dp0"\nstart "" "%~dp0..\\..\\tools\\gtkwave\\portable\\gtkwave64\\bin\\gtkwave.exe" -f "%~dp0overlap.vcd" -a "%~dp0overlap.gtkw"\n'
    (out/'open_gtkwave.cmd').write_text(launcher)
    tcl=f'''set out [file dirname [file normalize [info script]]]
set log [open [file join $out validation.log] w]
set names [gtkwave::getDisplayedSignals]
puts $log "COUNT=[llength $names]"
puts $log "DUMP=[gtkwave::getDumpFileName]"
if {{[llength $names] != {len(mapping)}}} {{puts $log "FAIL signal count";close $log;gtkwave::/File/Quit}}
gtkwave::setZoomRangeTimes {max(first,detail-500000)} {min(end,detail+2500000)}
gtkwave::setNamedMarker A {detail} STORE_COMPUTE_OVERLAP
gtkwave::/Edit/Set_Trace_Max_Hier 1
gtkwave::/View/Scale_To_Time_Dimension/ns
update
after 500
gtkwave::/File/Write_Save_File_As [file join $out overlap.gtkw]
puts $log "PASS GTKWave overlap session"
close $log
gtkwave::/File/Quit
'''
    (out/'verify.tcl').write_text(tcl)
    audit={'source_run':str(run),'source_vcd_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
           'metrics':result['tests']['overlap']['metrics'],'signal_mapping':mapping,'first_ps':first,'end_ps':end,'detail_ps':detail}
    (out/'provenance.json').write_text(json.dumps(audit,indent=2)+'\n')
    shutil.copyfile(run/'overlap/events.csv',out/'events.csv')
    shutil.copyfile(run/'overlap/manifest.json',out/'manifest.json')
    print(out)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);prepare(p.parse_args().run.resolve())
