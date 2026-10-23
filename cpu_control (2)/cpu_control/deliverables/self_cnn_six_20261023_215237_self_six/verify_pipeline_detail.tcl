set log [open validation_pipeline_detail.log w]
set failure [catch {
gtkwave::setZoomRangeTimes 0 2560000
set shown [gtkwave::getDisplayedSignals]
puts $log "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"
if {[llength $shown] != 10 || [llength [lsort -unique $shown]] != 10} {error "missing/duplicate signals"}
puts $log "PASS"
} message]
if {$failure} {puts $log "FAIL $message"}
close $log
gtkwave::/File/Quit
