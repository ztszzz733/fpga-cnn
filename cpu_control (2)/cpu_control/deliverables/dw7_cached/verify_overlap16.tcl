gtkwave::/View/Scale_To_Time_Dimension/us
gtkwave::setZoomRangeTimes 10065 14565
set shown [gtkwave::getDisplayedSignals]
if {[llength $shown] != 11} {error "signal count mismatch"}
set f [open [file join [file dirname [info script]] gtkwave_validation.log] a]
puts $f "PASS overlap16 COUNT=[llength $shown]"
close $f
gtkwave::/File/Quit
