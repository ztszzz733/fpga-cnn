gtkwave::setZoomRangeTimes 10 4326010
if {[llength [gtkwave::getDisplayedSignals]] != 14} {error "signal count"}
set f [open [file join [file dirname [info script]] validation.log] a]
puts $f "PASS skew_stall signals=14"
close $f
gtkwave::/File/Quit
