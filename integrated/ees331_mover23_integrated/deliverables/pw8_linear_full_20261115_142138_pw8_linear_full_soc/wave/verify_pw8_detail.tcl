set out [file dirname [file normalize [info script]]]
gtkwave::setZoomRangeTimes 901125360 901135600
gtkwave::/View/Scale_To_Time_Dimension/us
gtkwave::/Edit/Set_Trace_Max_Hier 1
gtkwave::/File/Write_Save_File_As [file join $out pw8_detail.gtkw]
set shown [gtkwave::getDisplayedSignals]
set log [open [file join $out validation_pw8_detail.log] w]
puts $log "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"
foreach s $shown {puts $log $s}
if {[llength $shown] == 10 && [llength [lsort -unique $shown]] == 10} {puts $log "PASS GTKWave unique controls"} else {puts $log "FAIL signal count"}
close $log
gtkwave::/File/Quit
