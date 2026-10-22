gtkwave::/Edit/Set_Trace_Max_Hier 1
gtkwave::/View/Scale_To_Time_Dimension/us
gtkwave::setZoomRangeTimes 549925 553225
gtkwave::setMarker -1
set out [file dirname [file normalize [info script]]]
set shown [gtkwave::getDisplayedSignals]
if {[llength $shown] != 13} {error "signal count mismatch"}
set f [open [file join $out gtkwave_validation.log] a]
puts $f "PASS 03_layer_handoff COUNT=[llength $shown]"
close $f
gtkwave::/File/Quit
