set out [file dirname [file normalize [info script]]]
gtkwave::setZoomRangeTimes 9962565000 9964855000
gtkwave::/View/Scale_To_Time_Dimension/us
gtkwave::/Edit/Set_Trace_Max_Hier 2
set shown [gtkwave::getDisplayedSignals]
set log [open [file join $out validation_gtk.log] w]
puts $log "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"
foreach s $shown {puts $log $s}
if {[llength $shown]==40 && [llength [lsort -unique $shown]]==40} {puts $log PASS} else {puts $log FAIL}
close $log
gtkwave::/File/Write_Save_File_As [file join $out mac_activity.gtkw]
gtkwave::/File/Quit
