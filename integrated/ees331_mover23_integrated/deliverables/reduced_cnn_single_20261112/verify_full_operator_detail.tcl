set out [file dirname [file normalize [info script]]]
gtkwave::setZoomRangeTimes 354126760000 354128040000
gtkwave::/View/Scale_To_Time_Dimension/us
gtkwave::/Edit/Set_Trace_Max_Hier 1
gtkwave::/File/Write_Save_File_As [file join $out full_operator_detail.gtkw]
set shown [gtkwave::getDisplayedSignals]
set log [open [file join $out validation_full_operator_detail.log] w]
puts $log "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"
foreach s $shown {puts $log $s}
if {[llength $shown] == 32} {puts $log "PASS GTKWave 12-operator view"} else {puts $log "FAIL signal count"}
close $log
gtkwave::/File/Quit
