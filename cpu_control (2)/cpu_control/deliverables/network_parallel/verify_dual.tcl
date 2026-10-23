gtkwave::setZoomRangeTimes 10 1563320
if {[llength [gtkwave::getDisplayedSignals]] != 15} {error "signal count"}
set f [open [file join [file dirname [info script]] validation.log] a]
puts $f "PASS dual signals=15"
close $f
gtkwave::/File/Quit
