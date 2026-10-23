set log [open [file join [file dirname [info script]] validation_pipeline_detail.log] w]
set failure [catch {
gtkwave::setZoomRangeTimes 0 2560000
gtkwave::/View/Scale_To_Time_Dimension/ns
set shown [gtkwave::getDisplayedSignals]
puts $log "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"
if {[llength $shown] != 10 || [llength [lsort -unique $shown]] != 10} {error "missing or duplicate signals"}
puts $log "PASS pipeline_detail"
} message]
if {$failure} {puts $log "FAIL $message"}
close $log
gtkwave::/File/Quit
