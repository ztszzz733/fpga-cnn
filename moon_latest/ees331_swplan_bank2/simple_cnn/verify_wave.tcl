set out [file dirname [file normalize [info script]]]
gtkwave::setZoomRangeTimes 0 150000
gtkwave::/View/Scale_To_Time_Dimension/us
set shown [gtkwave::getDisplayedSignals]
set log [open [file join $out wave_validation.log] w]
puts $log "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"
foreach s $shown {puts $log $s}
if {[llength $shown] == 8 && [llength [lsort -unique $shown]] == 8} {puts $log "PASS GTKWave unique controls"} else {puts $log "FAIL signal count"}
close $log
gtkwave::/File/Quit
