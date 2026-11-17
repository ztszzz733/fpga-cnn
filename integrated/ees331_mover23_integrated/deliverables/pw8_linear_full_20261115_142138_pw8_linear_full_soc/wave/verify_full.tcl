set out [file dirname [file normalize [info script]]]
gtkwave::setZoomRangeTimes 0 941218560
gtkwave::/View/Scale_To_Time_Dimension/ms
gtkwave::/Edit/Set_Trace_Max_Hier 1
gtkwave::/File/Write_Save_File_As [file join $out full.gtkw]
set shown [gtkwave::getDisplayedSignals]
set log [open [file join $out validation_full.log] w]
puts $log "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"
foreach s $shown {puts $log $s}
if {[llength $shown] == 24 && [llength [lsort -unique $shown]] == 24} {puts $log "PASS GTKWave unique controls"} else {puts $log "FAIL signal count"}
close $log
gtkwave::/File/Quit
