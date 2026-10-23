#!/usr/bin/env python3
"""Package this revision's actual self-CNN results, traces and editable diagram.

PNG waveforms are plotted from the simulator's trace.csv; they are not GTKWave
screenshots. Native GTKWave sessions independently display the original VCD.
"""
from __future__ import annotations
import argparse
import bisect
import csv
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageFont
from plot_waveforms import read_vcd

ROOT = Path(__file__).resolve().parents[1]
GROUPS = [
    ('CONTROL', 1, '#64748b', ['clk', 'clear', 'start', 'engine_enable', 'error']),
    ('SCHEDULER / OPERATORS', 4, '#2563eb', ['unit_start', 'unit_active', 'operator_busy', 'operator_work', 'completion_pulse', 'completed_count']),
    ('MEMORY PORTS', 3, '#b45309', ['mem_valid', 'mem_write', 'mem_ready', 'mem_response']),
    ('BUFFER LEASES', 6, '#7c3aed', ['buffer_live', 'buffer_release', 'external_hold']),
    ('RESULT HANDOFF', 5, '#15803d', ['result_valid', 'result_ready', 'result_accept', 'result_frame', 'result_addr', 'result_bytes', 'compute_done', 'done']),
]
CONTRACT = {
    'clk': ('clock/TB', 'CNN', 'Rising edge samples all synchronous handshakes', 'always'),
    'clear': ('configuration host', 'CNN and memory fabric', 'Abort batch and discard all old responses and reader ACKs', 'assert through cancellation'),
    'start': ('configuration host', 'dispatcher', 'One pulse starts the fully programmed batch', 'program_ready after last command'),
    'engine_enable': ('configuration host', 'dispatcher', 'Available K3 engines, latched at start', 'at start; at least one enabled'),
    'error': ('dispatcher', 'external system', 'Sticky batch fault; all work cancelled', 'until clear'),
    'unit_start': ('dispatcher', 'seven operators', 'One launch pulse per selected unit', 'command/node locked on launch'),
    'unit_active': ('dispatcher', 'scheduler/debug', 'Task assigned until drained operator completion', 'while task is in flight'),
    'operator_busy': ('seven operators', 'dispatcher/debug', 'Engine occupied, including memory waits', 'always; not proof of computation'),
    'operator_work': ('seven operators', 'debug', 'Bits0..3 actual MAC; bits4..6 accepted output write', 'one event per effective work cycle'),
    'completion_pulse': ('dispatcher', 'debug/checker', 'Operator completed after final write response', 'single cycle per completion'),
    'completed_count': ('dispatcher', 'status/debug', 'Number of completed tasks', 'current batch'),
    'mem_valid': ('operators', 'memory fabric', 'Request offered; all fields stable until accepted', 'valid and ready at rising edge'),
    'mem_write': ('operators', 'memory fabric', '1=write, 0=read', 'only while matching mem_valid bit is 1'),
    'mem_ready': ('memory fabric', 'operators', 'Accept corresponding request', 'valid and ready at rising edge'),
    'mem_response': ('memory fabric', 'operators', 'Accepted transaction completed; writes committed', 'after acceptance, one outstanding per port'),
    'buffer_live': ('buffer leases', 'scheduler/debug', 'Physical slots currently leased', 'current batch'),
    'buffer_release': ('buffer leases', 'storage/debug', 'All consumers completed and no external hold', 'reclaim notification before next reuse'),
    'external_hold': ('result handoff', 'buffer leases', 'Protect result slot from launch until reader ACK', 'result may still be computing'),
    'result_valid': ('result handoff', 'external reader', 'Descriptor valid and all result writes complete', 'held until valid and ready'),
    'result_ready': ('external reader', 'result handoff', 'All result bytes already read and responses drained', 'ACK edge with valid; not readiness to start reading'),
    'result_accept': ('result handoff', 'debug/external system', 'Previous edge accepted result ACK', 'one cycle after handshake'),
    'result_frame': ('result handoff', 'external reader', 'Frame identifier; completion order may differ', 'only while result_valid'),
    'result_addr': ('result handoff', 'external reader', 'Byte address of final payload', 'only while result_valid; stable until ACK'),
    'result_bytes': ('result handoff', 'external reader', 'Nonzero final payload byte count', 'only while result_valid; stable until ACK'),
    'compute_done': ('dispatcher', 'external system', 'All compute tasks finished', 'results may still await reader ACK'),
    'done': ('CNN top', 'external system', 'Compute complete, all results ACKed, all slots released', 'no cancellation active'),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def copy_file(source, target):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def verify_sources(result, key='source_sha256'):
    verified = {}
    for name, expected in result[key].items():
        path = ROOT / name.replace('\\', '/')
        actual = sha(path)
        if actual != expected:
            raise RuntimeError(f'Source changed since validation: {name}')
        verified[name] = actual
    return verified


def draw_wave(path, rows, left, right, title):
    # Distinct bits of operator_work are shown separately, without repeating the
    # original bus. Other buses are shown once and annotated in hex/decimal.
    fields = [('start', None, 'unit_start [6:0]', '#2563eb'),
              ('active', None, 'unit_active [6:0]', '#2563eb')]
    for bit, label in enumerate(('K3 #0 MAC', 'K3 #1 MAC', 'K1 MAC', 'DW7 MAC (8 lanes)', 'Post output accepted', 'Add output accepted', 'Pad output accepted')):
        fields.append(('work', bit, label, '#2563eb' if bit < 4 else '#0f766e'))
    fields += [('k3_0_write', None, 'K3 #0 write accept (derived)', '#b45309'),
               ('k3_1_write', None, 'K3 #1 write accept (derived)', '#b45309')]
    fields += [(s, None, label, color) for s, label, color in [
        ('valid', 'mem_valid [6:0]', '#b45309'), ('ready', 'mem_ready [6:0]', '#b45309'),
        ('write', 'mem_write [6:0]', '#b45309'), ('response', 'mem_response [6:0]', '#b45309'),
        ('complete', 'completion_pulse [6:0]', '#2563eb'), ('count', 'completed_count', '#2563eb'),
        ('live', 'buffer_live [7:0]', '#7c3aed'), ('result_frame', 'result_frame', '#15803d'),
        ('result_valid', 'result_valid', '#15803d'), ('result_ready', 'result_ready (read done)', '#15803d'),
        ('result_accept', 'result_accept', '#15803d'), ('compute_done', 'compute_done', '#64748b'),
        ('done', 'done (results released)', '#64748b')]]
    scalar = {'result_valid', 'result_ready', 'result_accept', 'compute_done', 'done', 'k3_0_write', 'k3_1_write'}
    font_path = 'C:/Windows/Fonts/consola.ttf'
    font = lambda size: ImageFont.truetype(font_path, size)
    width, row_height, top = 1900, 43, 165
    height = top + len(fields) * row_height + 88
    image = Image.new('RGB', (width, height), '#f8fafc')
    draw = ImageDraw.Draw(image)
    draw.text((26, 20), title, font=font(27), fill='#0f172a')
    draw.text((26, 62), 'Actual RTL trace.csv samples | bit order 0=K3a, 1=K3b, 2=K1, 3=DW7, 4=Post, 5=Add, 6=Pad', font=font(17), fill='#475569')
    draw.text((26, 89), 'MAC is real arithmetic; Post/Add/Pad work means an accepted output write. Dense pulses require a detail view.', font=font(16), fill='#475569')
    x0, x1 = 355, width - 35
    x = lambda cycle: x0 + (cycle-left) * (x1-x0) / (right-left)
    for i in range(9):
        cycle = left + (right-left) * i / 8
        xx = x(cycle)
        draw.line((xx, top-12, xx, top+len(fields)*row_height), fill='#dbe4ee')
        draw.text((min(xx-32, width-125), top-39), f'{cycle:,.0f}', font=font(15), fill='#64748b')
    cycles = [r['cycle'] for r in rows]
    begin = max(0, bisect.bisect_right(cycles, left)-1)
    end = min(len(rows), bisect.bisect_right(cycles, right)+1)
    selected = rows[begin:end]
    for index, (field, bit, label, color) in enumerate(fields):
        y = top + index * row_height
        draw.text((25, y+6), label, font=font(17), fill=color)
        is_scalar = bit is not None or field in scalar
        segments = []
        for row in selected:
            value = (row[field] >> bit) & 1 if bit is not None else row[field]
            if not segments or value != segments[-1][1]:
                segments.append((max(left, row['cycle']), value))
        previous = None
        for n, (start, value) in enumerate(segments):
            stop = min(right, segments[n+1][0] if n+1 < len(segments) else right)
            if stop <= start:
                continue
            aa, bb = x(start), x(stop)
            if is_scalar:
                yy = y+3 if value else y+27
                if previous is not None:
                    draw.line((aa, previous, aa, yy), fill=color, width=2)
                draw.line((aa, yy, bb, yy), fill=color, width=2)
                previous = yy
            else:
                draw.rectangle((aa, y+3, bb, y+29), outline=color)
                text = str(value) if field in ('count', 'result_frame') else f'{value:02X}'
                if bb-aa > len(text)*10+7:
                    draw.text((aa+4, y+6), text, font=font(16), fill=color)
    bottom = top + len(fields)*row_height
    draw.text((25, bottom+20), f'Cycle window {left:,}..{right:,}; 10 ns simulation period. Frame is meaningful only while result_valid=1.', font=font(16), fill='#475569')
    draw.text((25, bottom+46), 'No values are extrapolated beyond recorded samples. This is a trace rendering, not a GUI screenshot.', font=font(16), fill='#475569')
    image.save(path)


def architecture(path):
    mx = ET.Element('mxfile', host='app.diagrams.net', version='24.7.17')
    diagram = ET.SubElement(mx, 'diagram', id='self-cnn-pair', name='CNN seven execution units')
    model = ET.SubElement(diagram, 'mxGraphModel', dx='1600', dy='1200', grid='1', gridSize='10', page='1', pageWidth='1654', pageHeight='1169')
    root = ET.SubElement(model, 'root')
    ET.SubElement(root, 'mxCell', id='0'); ET.SubElement(root, 'mxCell', id='1', parent='0')
    def box(id, text, x, y, w, h, fill='#ffffff', dashed=False):
        cell = ET.SubElement(root, 'mxCell', id=id, value=text,
                             style=f'rounded=1;whiteSpace=wrap;html=1;fillColor={fill};strokeColor=#475569;fontSize=15;'+('dashed=1;' if dashed else ''),
                             vertex='1', parent='1')
        ET.SubElement(cell, 'mxGeometry', x=str(x), y=str(y), width=str(w), height=str(h), attrib={'as':'geometry'})
    def edge(id, source, target, label='', color='#475569'):
        cell = ET.SubElement(root, 'mxCell', id=id, value=label,
                             style=f'edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=block;strokeColor={color};fontSize=13;',
                             edge='1', parent='1', source=source, target=target)
        ET.SubElement(cell, 'mxGeometry', relative='1', attrib={'as':'geometry'})
    box('title','Self CNN: two K3 + one of every other operator<br>Two preloaded 7x7 RGB images; 22 real RTL tasks',300,15,1000,70,'#e2e8f0')
    box('host','External CPU / image bridge<br>Configuration and input preparation<br>Not instantiated in this isolated test',20,130,280,120,'#f1f5f9',True)
    box('scheduler','self_dispatch<br>64-entry command DAG<br>Choose any eligible free K3<br>unit_start/active/node',420,130,360,120,'#dbeafe')
    box('leases','self_buffer_leases<br>8 physical slots, owner generations<br>All declared consumers must finish',900,130,330,120,'#ede9fe')
    box('results','self_result_handoff<br>frame / address / length: 32 bits each<br>ACK only after external reads finish',1260,130,350,120,'#dcfce7')
    edge('cfg','host','scheduler','program_valid/ready; command[511:0]')
    edge('allocation','scheduler','leases','reserve + node[5:0] / buffer_ready','#7c3aed')
    edge('hold','results','leases','external_hold[7:0]','#7c3aed')
    box('units','CNN INTERNAL EXECUTION UNITS — independent engines, shared external memory bandwidth<br>Per unit: command[511:0] + start[1] from dispatcher; busy/done/error[1 each] return to dispatcher',105,305,1440,70,'#e2e8f0')
    labels = [('K3 #0','NEW self_conv_engine<br>ordinary / DW3, 1 MAC<br>2x2 tile + cached halo'),
              ('K3 #1','NEW self_conv_engine<br>ordinary / DW3, 1 MAC<br>2x2 tile + cached halo'),
              ('K1','NEW self_conv_engine<br>ordinary 1x1, 1 MAC<br>2x2 tile cache'),
              ('DW7','REUSED dw7_cached_engine<br>7x7 depthwise, 8 lanes<br>width=7, Cin multiple of 8'),
              ('Post','REUSED quant_post_engine<br>bias / scale / ties-away<br>ReLU / bounded clipping'),
              ('Add','REUSED quant_post_engine<br>two input scales<br>one final rounding'),
              ('Pad','REUSED pad_hwc_engine<br>HWC border +1 pixel<br>fill with input zero point')]
    for i,(name,desc) in enumerate(labels):
        box(f'u{i}',f'Port {i}: {name}<br>{desc}',35+i*228,405,215,165,'#dbeafe' if i<3 else '#dcfce7')
        edge(f'launch{i}','scheduler',f'u{i}',f'unit_start[{i}]','#2563eb')
    box('fabric','EXTERNAL MEMORY FABRIC / TB MODEL<br>7 one-outstanding ports, four-bank test arbitration<br>Per port: valid/write/byte/ready/response = 1 bit; addr/wdata/rdata = 32 bits<br>byte=1: low 8 bits; byte=0: aligned 32 bits; write response means committed',220,700,1160,130,'#ffedd5',True)
    for i in range(7):
        edge(f'mem{i}',f'u{i}','fabric',f'port {i}','#b45309')
    box('sram','SRAM TEST STORAGE<br>Immutable images / weights / parameters<br>8 x 2048-byte payload slots + 64-byte guards<br>Released payloads poisoned with 0xD7',270,915,550,135,'#ffedd5',True)
    box('reader','EXTERNAL RESULT READER (TB)<br>Reads actual SRAM bytes, verifies frame ownership<br>Then result_ready = 1<br>Production reader and bus arbitration are external',990,915,550,135,'#dcfce7',True)
    edge('store','fabric','sram','request / delayed response','#b45309')
    edge('desc','results','reader','valid / frame / addr / bytes','#15803d')
    edge('ack','reader','results','result_ready: all reads complete','#15803d')
    edge('externalread','sram','reader','actual output bytes','#b45309')
    ET.indent(mx)
    ET.ElementTree(mx).write(path, encoding='utf-8', xml_declaration=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--unit', type=Path, default=ROOT/'build/runs/20261023_145746_335613_self_conv_unit')
    parser.add_argument('--out', type=Path, default=ROOT/'deliverables/self_cnn_pair')
    args = parser.parse_args()
    run, out = args.run.resolve(), args.out.resolve()
    result = json.loads((run/'result.json').read_text())
    if result['status'] != 'PASS': raise RuntimeError('Only a completed PASS can be packaged')
    provenance = {'source_run':str(run),'source_sha256':verify_sources(result),'artifacts':{},'png_source':'dual/trace.csv, actual RTL samples; not screenshots'}
    out.mkdir(parents=True, exist_ok=True)
    copy_file(run/'result.json',out/'result.json')
    unit = json.loads((args.unit/'result.json').read_text())
    if unit['status'] != 'PASS': raise RuntimeError('Unit run is not PASS')
    provenance['unit_source_sha256'] = verify_sources(unit)
    copy_file(args.unit/'result.json',out/'unit_result.json')
    copy_file(args.unit/'simulation.log',out/'unit_simulation.log')
    for mode, metrics in result['scenarios'].items():
        src=run/mode
        output=bytes(int(x,16) for x in (src/'outputs.hex').read_text().split())
        if hashlib.sha256(output).hexdigest()!=metrics['output_sha256']: raise RuntimeError('Output hash mismatch '+mode)
        for name in ('metrics.json','sim.log','events.csv','outputs.hex','trace.csv','control.vcd'):
            if (src/name).exists(): copy_file(src/name,out/mode/name)
    for name, expected in result['fixture']['files_sha256'].items():
        if sha(run/'data'/name)!=expected: raise RuntimeError('Fixture hash mismatch '+name)
    for source in (run/'data').iterdir():
        if source.is_file(): copy_file(source,out/'data'/source.name)
    parameter=ROOT/'build/runs/20261023_150855_372167_self_conv_parameter_review/result.json'
    if parameter.exists():
        p=json.loads(parameter.read_text())
        if p['rtl_sha256']!=sha(ROOT/'rtl/cnn_self/self_conv_engine.sv'): raise RuntimeError('Parameter review RTL changed')
        if not all(v['status']=='PASS' for v in p['variants']): raise RuntimeError('Parameter sweep not PASS')
        copy_file(parameter,out/'parameter_review.json')
    synth_paths = [('full_top',ROOT/'build/runs/20261023_150436_706083_self_cnn_synth'),
                   ('conv3',ROOT/'build/runs/20261023_150913_240097_self_cnn_synth'),
                   ('conv1',ROOT/'build/runs/20261023_151108_866766_self_cnn_synth')]
    provenance['synthesis']={}
    for name, source in synth_paths:
        if not (source/'result.json').exists(): continue
        sr=json.loads((source/'result.json').read_text())
        if sr['status']=='RUNNING': continue
        # Synthesis scripts may have gained a K1/K3 option after the failed full
        # run. Preserve recorded hashes and report current matching separately.
        matches={n:(sha(ROOT/n.replace('\\','/'))==h) for n,h in sr.get('sources_sha256',{}).items() if (ROOT/n.replace('\\','/')).exists()}
        provenance['synthesis'][name]={'source_run':str(source),'status':sr['status'],'current_source_matches':matches}
        for filename in ('result.json','process.log','vivado.log','utilization.rpt','timing_summary.rpt','timing.rpt','primitive_counts.tsv'):
            if (source/filename).exists(): copy_file(source/filename,out/'synthesis'/name/filename)
    rows=[{k:int(v) for k,v in row.items()} for row in csv.DictReader((out/'dual/trace.csv').open())]
    for row in rows:
        accepted_writes=row['write'] & row['valid'] & row['ready']
        row['k3_0_write']=int(bool(accepted_writes & 1))
        row['k3_1_write']=int(bool(accepted_writes & 2))
    vcd=read_vcd(out/'dual/control.vcd')
    signals=[n for _,_,_,names in GROUPS for n in names]
    if len(signals)!=26 or len(set(signals))!=26: raise RuntimeError('Unexpected signal count')
    if set(vcd.signals)!={'self_pair_tb.'+n for n in signals}: raise RuntimeError('VCD header differs from expected physical signals')
    first_trace=next(r['cycle'] for r in rows if r['start'])
    first_vcd=next(t for t,b in vcd.signals['self_pair_tb.unit_start'].events if int(b,2))
    origin=first_vcd-first_trace*10
    lo,hi=rows[0]['cycle'],rows[-1]['cycle']
    dual=next(r['cycle'] for r in rows if r['work']&3==3)
    conv=next(r['cycle'] for r in rows if r['valid']&r['ready']&r['write']&7)
    post=next(r['cycle'] for r in rows if r['valid']&r['ready']&r['write']&16)
    ack=max(r['cycle'] for r in rows if r['result_valid'] and r['result_ready'])
    windows=[('overview',lo,hi,'Two-image computation and result handoff: full recorded run'),
             ('dual_mac',max(lo,dual-35),min(hi,dual+190),'Two K3 engines: actual simultaneous MAC activity'),
             ('conv_write',max(lo,conv-65),min(hi,conv+150),'First convolution writeback: request acceptance and response'),
             ('post_write',max(lo,post-65),min(hi,post+150),'First postprocessing writeback'),
             ('result_ack',max(lo,ack-160),hi,'Final result read confirmation and buffer release')]
    manifest=[]
    for name,left,right,title in windows:
        draw_wave(out/(name+'.png'),rows,left,right,title)
        start_ps=int((origin+left*10)*1000);end_ps=int((origin+right*10)*1000)
        gtk=['[dumpfile] "'+(out/'dual/control.vcd').as_posix()+'"','[size] 1800 1100','[signals_width] 330']
        for group,color,_,names in GROUPS:
            gtk+=['@200','-'+group]
            for signal in names:
                width=vcd.signals['self_pair_tb.'+signal].width
                gtk+=['@28' if width==1 else '@24' if signal in ('result_frame','result_bytes','completed_count') else '@22',f'[color] {color}',
                      'self_pair_tb.'+signal+(f'[{width-1}:0]' if width>1 else '')]
        (out/(name+'.gtkw')).write_text('\n'.join(gtk)+'\n',encoding='utf-8')
        zoom=f'gtkwave::setZoomRangeTimes {start_ps} {end_ps}\ngtkwave::/View/Scale_To_Time_Dimension/ns\n'
        (out/(name+'.tcl')).write_text(zoom,encoding='ascii')
        verify='set log [open [file join [file dirname [info script]] validation_'+name+'.log] w]\n'
        verify+='set failure [catch {\n'+zoom+'set shown [gtkwave::getDisplayedSignals]\n'
        verify+='puts $log "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"\n'
        verify+='if {[llength $shown] != 26 || [llength [lsort -unique $shown]] != 26} {error "expected 26 unique physical signals"}\n'
        verify+='puts $log "PASS '+name+'"\n} message]\nif {$failure} {puts $log "FAIL $message"}\nclose $log\ngtkwave::/File/Quit\n'
        (out/('verify_'+name+'.tcl')).write_text(verify,encoding='ascii')
        (out/('open_'+name+'.cmd')).write_text('@echo off\nstart "" "%~dp0..\\..\\tools\\gtkwave\\portable\\gtkwave64\\bin\\gtkwave.exe" -f "%~dp0dual\\control.vcd" -a "%~dp0'+name+'.gtkw" -S "%~dp0'+name+'.tcl"\n',encoding='ascii')
        manifest.append({'name':name,'title':title,'trace_cycles':[left,right],'vcd_range_ps':[start_ps,end_ps],'physical_signal_count':26})
    (out/'wave_windows.json').write_text(json.dumps({'trace_cycle_to_vcd_interval_ns_offset':origin,'trace_sampling':'pre-edge trace matched to corresponding previous VCD interval by first unit_start','windows':manifest},indent=2),encoding='utf-8')
    with (out/'signals.csv').open('w',newline='',encoding='utf-8') as handle:
        writer=csv.writer(handle);writer.writerow(['group','physical_signal','width','gtk_color','source','destination','meaning','valid_when'])
        for group,color,_,names in GROUPS:
            for name in names:writer.writerow([group,'self_pair_tb.'+name,vcd.signals['self_pair_tb.'+name].width,color,*CONTRACT[name]])
    architecture(out/'architecture.drawio')
    (out/'validate_gtkwave.ps1').write_text('''$ErrorActionPreference='Stop'
$artifactRoot=$PSScriptRoot
$gtkExe=(Resolve-Path -LiteralPath (Join-Path $artifactRoot '..\\..\\tools\\gtkwave\\portable\\gtkwave64\\bin\\gtkwave.exe')).Path
$views=@('overview','dual_mac','conv_write','post_write','result_ack')
$results=@()
foreach($view in $views){
  $logPath=Join-Path $artifactRoot ('validation_'+$view+'.log')
  if(Test-Path -LiteralPath $logPath){Remove-Item -LiteralPath $logPath}
  $arguments=@('-f','dual/control.vcd','-a',($view+'.gtkw'),'-S',('verify_'+$view+'.tcl'))
  $process=Start-Process -FilePath $gtkExe -ArgumentList $arguments -WorkingDirectory $artifactRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $artifactRoot ('gtk_'+$view+'_stdout.log')) -RedirectStandardError (Join-Path $artifactRoot ('gtk_'+$view+'_stderr.log'))
  $exited=$process.WaitForExit(20000)
  if(-not $exited){Stop-Process -Id $process.Id}
  $contents=if(Test-Path -LiteralPath $logPath){Get-Content -LiteralPath $logPath -Raw}else{''}
  $status=if($exited -and $process.ExitCode -eq 0 -and $contents.Contains('PASS '+$view) -and $contents.Contains('SIGNALS=26 UNIQUE=26')){'PASS'}else{'FAIL'}
  $results += [pscustomobject]@{view=$view;status=$status;exited=$exited;signals=26;unique_signals=26;session_sha256=(Get-FileHash -LiteralPath (Join-Path $artifactRoot ($view+'.gtkw')) -Algorithm SHA256).Hash.ToLower();log=$contents.Trim()}
  Write-Output ($view+' '+$status)
}
$allPass=(@($results | Where-Object {$_.status -ne 'PASS'}).Count -eq 0)
[pscustomobject]@{status=$(if($allPass){'PASS'}else{'FAIL'});tool='GTKWave 3.3.100 actual Tcl validation';vcd_sha256=(Get-FileHash -LiteralPath (Join-Path $artifactRoot 'dual\\control.vcd') -Algorithm SHA256).Hash.ToLower();views=$results} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $artifactRoot 'gtkwave_validation.json') -Encoding UTF8
if(-not $allPass){exit 1}
''',encoding='utf-8')
    provenance['packager_sha256']=sha(Path(__file__))
    for source in out.rglob('*'):
        if source.is_file() and source.name not in ('provenance.json','README.md','verification_report.md'):
            provenance['artifacts'][source.relative_to(out).as_posix()]=sha(source)
    (out/'provenance.json').write_text(json.dumps(provenance,indent=2,ensure_ascii=False),encoding='utf-8')
    print(out)


if __name__=='__main__': main()
