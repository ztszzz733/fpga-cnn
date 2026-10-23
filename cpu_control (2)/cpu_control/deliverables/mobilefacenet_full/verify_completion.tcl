gtkwave::/View/Scale_To_Time_Dimension/ms
gtkwave::setZoomRangeTimes 348352590 348354590
set shown [gtkwave::getDisplayedSignals]
if {[llength $shown] != 10} {error "signal count"}
set f [open [file join [file dirname [info script]] gtkwave_validation.log] a]
puts $f "PASS completion COUNT=[llength $shown]"
close $f
gtkwave::/File/Quit
