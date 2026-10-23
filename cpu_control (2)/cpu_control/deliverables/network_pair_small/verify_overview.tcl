gtkwave::setZoomRangeTimes 10 2988320
if {[llength [gtkwave::getDisplayedSignals]] != 16} {error "signal count"}
set f [open [file join [file dirname [info script]] validation.log] a]
puts $f "PASS overview signals=16"
close $f
gtkwave::/File/Quit
