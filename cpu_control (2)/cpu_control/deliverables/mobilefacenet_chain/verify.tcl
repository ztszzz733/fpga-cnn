set out [file dirname [file normalize [info script]]]
set shown [gtkwave::getDisplayedSignals]
if {[llength $shown] != 16} {error "signal count mismatch"}
set f [open [file join $out gtkwave_validation.log] w]
puts $f "PASS COUNT=[llength $shown]"
close $f
gtkwave::/File/Quit
