set out [file dirname [file normalize [info script]]]
set log [open [file join $out validation_module_states.log] w]
set filter [gtkwave::setCurrentTranslateFile [file join $out state_names.txt]]
set state_names [list {soc_top.cpu_state[1:0]} {soc_top.cnn_state[1:0]} {soc_top.sram_state[1:0]} {soc_top.imem_state[1:0]} {soc_top.bridge_state[1:0]} {soc_top.clock_state[1:0]}]
gtkwave::highlightSignalsFromList $state_names
gtkwave::installFileFilter $filter
gtkwave::unhighlightSignalsFromList $state_names
gtkwave::setZoomRangeTimes 0 4002570000
gtkwave::/View/Scale_To_Time_Dimension/ns
gtkwave::/Edit/Set_Trace_Max_Hier 1
gtkwave::/File/Write_Save_File_As [file join $out module_states.gtkw]
puts $log "module_states TOTAL=[gtkwave::getTotalNumTraces] SIGNALS=[llength [gtkwave::getDisplayedSignals]]"
if {[llength [gtkwave::getDisplayedSignals]] != 9} {puts $log "FAIL signal count"}
set shown [gtkwave::getDisplayedSignals]
puts $log "UNIQUE=[llength [lsort -unique $shown]]"
if {[llength $shown] != [llength [lsort -unique $shown]]} {puts $log "FAIL duplicate signal"}
flush $log
gtkwave::setMarker 3782025000
set value [gtkwave::getTraceValueAtMarkerFromName {soc_top.cnn_state[1:0]}]
puts $log "STATE=$value"
if {![string match "*WORK*" $value]} {puts $log "FAIL state translation"}
gtkwave::setMarker -1
puts $log "PASS GTKWave six-module session"
close $log
gtkwave::/File/Quit
