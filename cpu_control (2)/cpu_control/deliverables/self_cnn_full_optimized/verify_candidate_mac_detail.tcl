set log [open [file join [file dirname [info script]] validation_candidate_mac_detail.log] w]
set failure [catch {
# Window-relative samples: 0..2560 ns; global origin was not recorded.
gtkwave::setZoomRangeTimes 0 2560000
gtkwave::/View/Scale_To_Time_Dimension/ns
set shown [gtkwave::getDisplayedSignals]
puts $log "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"
if {[llength $shown] != 10 || [llength [lsort -unique $shown]] != 10} {error "missing or duplicate signals"}
puts $log "PASS candidate_mac_detail"
} message]
if {$failure} {puts $log "FAIL $message"}
close $log
gtkwave::/File/Quit
