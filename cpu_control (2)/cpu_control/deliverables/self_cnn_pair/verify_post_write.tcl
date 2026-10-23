set log [open [file join [file dirname [info script]] validation_post_write.log] w]
set failure [catch {
gtkwave::setZoomRangeTimes 365055000 367205000
gtkwave::/View/Scale_To_Time_Dimension/ns
set shown [gtkwave::getDisplayedSignals]
puts $log "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"
if {[llength $shown] != 26 || [llength [lsort -unique $shown]] != 26} {error "expected 26 unique physical signals"}
puts $log "PASS post_write"
} message]
if {$failure} {puts $log "FAIL $message"}
close $log
gtkwave::/File/Quit
