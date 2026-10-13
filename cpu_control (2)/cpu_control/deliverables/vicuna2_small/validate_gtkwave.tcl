set out [file dirname [file normalize [info script]]]
set log [open [file join $out gtkwave_validation.log] w]
set shown [gtkwave::getDisplayedSignals]
puts $log "COUNT=[llength $shown]"
foreach signal $shown {puts $log $signal}
if {[llength $shown] == 19} {puts $log "PASS"} else {puts $log "FAIL"}
close $log
gtkwave::/File/Quit
