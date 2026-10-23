gtkwave::/View/Scale_To_Time_Dimension/us
gtkwave::setZoomRangeTimes 0 884655
set shown [gtkwave::getDisplayedSignals]
if {[llength $shown] != 11} {error "signal count mismatch"}
set f [open [file join [file dirname [info script]] gtkwave_validation.log] a]
puts $f "PASS real512 COUNT=[llength $shown]"
close $f
gtkwave::/File/Quit
