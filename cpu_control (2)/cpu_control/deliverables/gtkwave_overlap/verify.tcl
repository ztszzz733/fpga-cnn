set out [file dirname [file normalize [info script]]]
set log [open [file join $out validation.log] w]
set names [gtkwave::getDisplayedSignals]
puts $log "COUNT=[llength $names]"
puts $log "DUMP=[gtkwave::getDumpFileName]"
if {[llength $names] != 31} {puts $log "FAIL signal count";close $log;gtkwave::/File/Quit}
gtkwave::setZoomRangeTimes 10000565000 10003565000
gtkwave::setNamedMarker A 10001065000 STORE_COMPUTE_OVERLAP
gtkwave::/Edit/Set_Trace_Max_Hier 1
gtkwave::/View/Scale_To_Time_Dimension/ns
update
after 500
gtkwave::/File/Write_Save_File_As [file join $out overlap.gtkw]
puts $log "PASS GTKWave overlap session"
close $log
gtkwave::/File/Quit
