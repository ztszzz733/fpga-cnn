set out [file dirname [file normalize [info script]]]
gtkwave::setZoomRangeTimes 9956955000 9963565000
gtkwave::/View/Scale_To_Time_Dimension/us
gtkwave::/Edit/Set_Trace_Max_Hier 1
set shown [gtkwave::getDisplayedSignals]
set log [open [file join $out gtk_validation.log] w]
puts $log "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"
foreach s $shown {puts $log $s}
if {[llength $shown]==43 && [llength [lsort -unique $shown]]==43} {puts $log PASS} else {puts $log FAIL}
close $log
gtkwave::/File/Write_Save_File_As [file join $out actual_read_wait.gtkw]
gtkwave::/File/Quit
