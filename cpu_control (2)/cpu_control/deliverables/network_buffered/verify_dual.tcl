gtkwave::setZoomRangeTimes 10 2972640
if {[llength [gtkwave::getDisplayedSignals]] != 14} {error "signal count"}
set f [open [file join [file dirname [info script]] validation.log] a]
puts $f "PASS dual signals=14"
close $f
gtkwave::/File/Quit
