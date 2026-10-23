set log [open [file join [file dirname [info script]] validation_overview.log] w]
set failure [catch {
gtkwave::setZoomRangeTimes 166615000 998625000
gtkwave::/View/Scale_To_Time_Dimension/ns
set shown [gtkwave::getDisplayedSignals]
puts $log "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"
if {[llength $shown] != 25 || [llength [lsort -unique $shown]] != 25} {error "missing or duplicate signals"}
puts $log "PASS overview"
} message]
if {$failure} {puts $log "FAIL $message"}
close $log
gtkwave::/File/Quit
