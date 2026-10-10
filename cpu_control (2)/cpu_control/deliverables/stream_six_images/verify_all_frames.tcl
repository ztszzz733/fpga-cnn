set out [file dirname [file normalize [info script]]]
set log [open [file join $out validation_all_frames.log] w]
set filter [gtkwave::setCurrentTranslateFile [file join $out state_names.txt]]
set states [list {stream_top.cpu_state[1:0]} {stream_top.cnn_state[1:0]} {stream_top.sram_state[1:0]} {stream_top.imem_state[1:0]} {stream_top.bridge_state[1:0]} {stream_top.clock_state[1:0]}]
gtkwave::highlightSignalsFromList $states
gtkwave::installFileFilter $filter
gtkwave::unhighlightSignalsFromList $states
gtkwave::setZoomRangeTimes 0 717108830000
gtkwave::/View/Scale_To_Time_Dimension/us
gtkwave::/Edit/Set_Trace_Max_Hier 1
gtkwave::/File/Write_Save_File_As [file join $out all_frames.gtkw]
set shown [gtkwave::getDisplayedSignals]
puts $log "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"
if {[llength $shown]!=12 || [llength [lsort -unique $shown]]!=12} {puts $log "FAIL signal count"}
gtkwave::setMarker 846210000
set value [gtkwave::getTraceValueAtMarkerFromName {stream_top.cnn_state[1:0]}]
puts $log "CNN_STATE=$value"
if {![string match "*WORK*" $value]} {puts $log "FAIL state translation"}
puts $log "PASS GTKWave stream session"
close $log
gtkwave::/File/Quit
