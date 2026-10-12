set out [file dirname [file normalize [info script]]]
set shown [gtkwave::getDisplayedSignals]
set log [open [file join $out gtkwave_validation.log] w]
if {[llength $shown] == 23} {puts $log "PASS COUNT=[llength $shown]"} else {puts $log "FAIL COUNT=[llength $shown]"}
puts $log $shown
close $log
gtkwave::/File/Quit
