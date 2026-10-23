gtkwave::setZoomRangeTimes 1748060 1748300
if {[llength [gtkwave::getDisplayedSignals]] != 16} {error "signal count"}
set f [open [file join [file dirname [info script]] validation.log] a]
puts $f "PASS first_ack signals=16"
close $f
gtkwave::/File/Quit
