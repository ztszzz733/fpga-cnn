gtkwave::setZoomRangeTimes 2086650 2086890
if {[llength [gtkwave::getDisplayedSignals]] != 16} {error "signal count"}
set f [open [file join [file dirname [info script]] validation.log] a]
puts $f "PASS first_ack signals=16"
close $f
gtkwave::/File/Quit
