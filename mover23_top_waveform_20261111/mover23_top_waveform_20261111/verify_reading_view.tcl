source top_milestones.tcl
set log [open reading_view_validation.log w]
set signals [gtkwave::getDisplayedSignals]
puts $log "DISPLAYED=[llength $signals]"
if {[llength $signals] == 36} {puts $log "PASS local CNN/storage reading view"} else {puts $log "FAIL signal count"}
close $log
gtkwave::/File/Quit
