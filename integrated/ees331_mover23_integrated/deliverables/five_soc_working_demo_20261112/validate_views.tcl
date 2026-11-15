set f [open validation_current.log w]
set traces [gtkwave::getDisplayedSignals]
puts $f "DISPLAYED=[llength $traces]"
puts $f "DUPLICATES=[expr {[llength $traces]-[llength [lsort -unique $traces]]}]"
set dump ""; catch {set dump [gtkwave::getDumpFileName]}; if {[string match *small_complete* $dump]} {gtkwave::setMarker 600000000} elseif {[string match *full_start* $dump]} {gtkwave::setMarker 120000000000} else {gtkwave::setMarker 7001000000000}
foreach name {SOC.MEMORY_STATE_TEXT SOC.MOVER_STATE_TEXT SOC.K1_4.STATE_TEXT SOC.K1_5.STATE_TEXT SOC.POST_2.STATE_TEXT SOC.PAD.STATE_TEXT} {
 catch {puts $f "$name=[gtkwave::getTraceValueAtMarkerFromName $name]"} err
 if {$err ne ""} {puts $f "LOOKUP=$err"}
}
close $f
gtkwave::/File/Quit

