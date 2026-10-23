gtkwave::setZoomRangeTimes 10 1927670
if {[llength [gtkwave::getDisplayedSignals]] != 15} {error "signal count"}
set f [open [file join [file dirname [info script]] validation.log] a]
puts $f "PASS skew_stall signals=15"
close $f
gtkwave::/File/Quit
