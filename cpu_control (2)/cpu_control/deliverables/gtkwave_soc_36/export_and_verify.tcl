set task_out [file dirname [file normalize [info script]]]
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
    gtkwave::/File/Print_To_File PS {A4 (11.68" x 8.26")} Full [file join $task_out $name.ps]
    gtkwave::/File/Write_Save_File_As [file join $task_out $name.gtkw]
    set status [catch {gtkwave::/File/Grab_To_File [file join $task_out $name.png]} message]
    puts $log "GRAB_$name=$status $message"
    puts $log "VIEW_$name=[gtkwave::getWindowStartTime]..[gtkwave::getWindowEndTime]"
}
puts $log "PASS GTKWave loaded all 36 signals"
close $log
# Leave the native viewer open for interactive inspection.
