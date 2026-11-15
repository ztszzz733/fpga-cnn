set out [file dirname [file normalize [info script]]]
gtkwave::setZoomRangeTimes 0 6094400000
gtkwave::/View/Scale_To_Time_Dimension/ms
gtkwave::/Edit/Set_Trace_Max_Hier 1
gtkwave::/File/Write_Save_File_As [file join $out full_cpu_config.gtkw]
set shown [gtkwave::getDisplayedSignals]
set log [open [file join $out validation_full_cpu_config.log] w]
puts $log "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"
foreach s $shown {puts $log $s}
if {[llength $shown] == 32} {puts $log "PASS GTKWave 12-operator view"} else {puts $log "FAIL signal count"}
close $log
gtkwave::/File/Quit
