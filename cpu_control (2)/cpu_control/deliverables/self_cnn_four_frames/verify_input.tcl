set log [open [file join [file dirname [info script]] validation_input.log] w]
set failure [catch {
gtkwave::setZoomRangeTimes 166615000 306615000
gtkwave::/View/Scale_To_Time_Dimension/ns
set shown [gtkwave::getDisplayedSignals]
puts $log "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"
if {[llength $shown] != 25 || [llength [lsort -unique $shown]] != 25} {error "missing or duplicate signals"}
puts $log "PASS input"
} message]
if {$failure} {puts $log "FAIL $message"}
close $log
gtkwave::/File/Quit
