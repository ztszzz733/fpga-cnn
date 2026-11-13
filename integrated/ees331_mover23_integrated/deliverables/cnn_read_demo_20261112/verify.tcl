set out [file dirname [file normalize [info script]]]
gtkwave::setZoomRangeTimes 160507815000 160508715000
gtkwave::/View/Scale_To_Time_Dimension/us
gtkwave::/Edit/Set_Trace_Max_Hier 1
gtkwave::setMarker 160507915000
gtkwave::/File/Write_Save_File_As [file join $out cnn_reads.gtkw]
set log [open [file join $out validation.log] w]
set shown [gtkwave::getDisplayedSignals]
puts $log "SIGNALS=[llength $shown]"
if {[llength $shown] == 16} {puts $log "PASS CNN read view"} else {puts $log "FAIL"}
puts $log "DATA_VALID=[gtkwave::getTraceValueAtMarkerFromName {CNN_READ.K1_0_READ_DATA_VALID}]"
puts $log "READ_ADDR=[gtkwave::getTraceValueAtMarkerFromName {CNN_READ.K1_0_READ_ADDR[31:0]}]"
puts $log "READ_DATA=[gtkwave::getTraceValueAtMarkerFromName {CNN_READ.K1_0_READ_DATA[31:0]}]"
close $log
gtkwave::/File/Quit
