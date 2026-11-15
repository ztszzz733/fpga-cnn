"""Prepare a GTKWave session with exactly the 36 previously plotted SoC wires."""
from pathlib import Path
import json
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from plot_waveforms import read_vcd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'deliverables/gtkwave_soc_36'
OUT.mkdir(parents=True,exist_ok=True)
source=ROOT/'docs/figures/soc_autoload_flow'
audit=json.loads((source/'soc_all_36_signals_audit.json').read_text(encoding='utf-8'))
names=audit['signals']
assert len(names)==len(set(names))==36
shutil.copy2(source/'soc_wires_only.vcd',OUT/'soc_wires.vcd')
vcd=read_vcd(OUT/'soc_wires.vcd')
lines=['[*] SoC 36 documented signals; historical XSim waveform',
       '[dumpfile] "'+(OUT/'soc_wires.vcd').as_posix()+'"',
       '[savefile] "'+(OUT/'soc_all_36.gtkw').as_posix()+'"',
       '[timestart] 0','[size] 1600 1000','[pos] 0 0',
       '*-19.5 -1 '+' '.join(['-1']*26),
       '[sst_width] 180','[signals_width] 280','[sst_expanded] 0']
for n in names:
    signal=vcd.signals['soc_wires.'+n]
    lines.append('@28' if signal.width==1 else '@22')
    color=4 if n.startswith('mem_') else 3 if n.startswith('cnn_mmio_') else 6 if n.startswith('load_') else 0
    lines.append(f'[color] {color}')
    lines.append(signal.path+(f'[{signal.width-1}:0]' if signal.width>1 else ''))
(OUT/'soc_all_36.gtkw').write_text('\n'.join(lines)+'\n',encoding='ascii')
(OUT/'soc_view.rc').write_text('fontname_signals Monospace 9\nfontname_waves Monospace 9\nsst_expanded 0\ninitial_window_x 1600\ninitial_window_y 1000\nsplash_disable 1\n',encoding='ascii')
tcl='''set task_out [file dirname [file normalize [info script]]]
set log [open [file join $task_out gtkwave_validation.log] w]
puts $log "DUMP=[gtkwave::getDumpFileName]"
puts $log "UNIT=[gtkwave::getTimeDimension]"
set shown [gtkwave::getDisplayedSignals]
puts $log "COUNT=[llength $shown]"
foreach name $shown {puts $log "SIGNAL=$name"}
puts $log "TOTAL=[gtkwave::getTotalNumTraces]"
puts $log "VISIBLE=[gtkwave::getVisibleNumTraces]"
flush $log
if {[llength $shown] != 36} {puts $log "FAIL signal count";close $log;gtkwave::/File/Quit}
gtkwave::setZoomRangeTimes 0 315000000
gtkwave::setMarker -1
gtkwave::setNamedMarker A 235000 CPU_LOAD_REQUEST
gtkwave::setNamedMarker B 311965000 LOAD_COMPLETE
gtkwave::setNamedMarker C 312455000 CNN_START
gtkwave::setNamedMarker D 313805000 CPU_FINISH
gtkwave::/Edit/Set_Trace_Max_Hier 1
gtkwave::/View/Scale_To_Time_Dimension/ns
foreach {time label} {313280000 BYTE_PENDING 313300000 WORD_WRITE} {
    gtkwave::setMarker $time
    puts $log "$label DATA=[gtkwave::getTraceValueAtMarkerFromName {soc_wires.mem_wdata[31:0]}] WRITE=[gtkwave::getTraceValueAtMarkerFromName soc_wires.mem_write]"
}
gtkwave::setMarker -1
foreach {name start end} {soc_all_36 0 315000000 soc_cnn_detail 312800000 313850000 soc_write_detail 313260000 313510000} {
    gtkwave::setZoomRangeTimes $start $end
    gtkwave::setTraceScrollbarRowValue 0
    update
    after 500
    gtkwave::/File/Print_To_File PS {A4 (11.68\" x 8.26\")} Full [file join $task_out $name.ps]
    gtkwave::/File/Write_Save_File_As [file join $task_out $name.gtkw]
    set status [catch {gtkwave::/File/Grab_To_File [file join $task_out $name.png]} message]
    puts $log "GRAB_$name=$status $message"
    puts $log "VIEW_$name=[gtkwave::getWindowStartTime]..[gtkwave::getWindowEndTime]"
}
puts $log "PASS GTKWave loaded all 36 signals"
close $log
# Leave the native viewer open for interactive inspection.
'''
(OUT/'export_and_verify.tcl').write_text(tcl,encoding='ascii')
(OUT/'expected_signals.json').write_text(json.dumps(names,indent=2),encoding='ascii')
for name,session in [('open_gtkwave','soc_all_36'),('open_cnn_detail','soc_cnn_detail'),('open_write_detail','soc_write_detail')]:
    launcher='''@echo off
setlocal
set "GTK=%~dp0..\\..\\tools\\gtkwave\\portable\\gtkwave64\\bin\\gtkwave.exe"
if not exist "%GTK%" (
  echo GTKWave portable not found. Place this folder under D:\\cpu_control\\deliverables.
  pause
  exit /b 1
)
start "" "%GTK%" -f "%~dp0soc_wires.vcd" -a "%~dp0SESSION.gtkw" -r "%~dp0soc_view.rc"
'''.replace('SESSION',session)
    (OUT/(name+'.cmd')).write_text(launcher,encoding='ascii')
print(OUT)
