gtkwave::setZoomRangeTimes 0 226777100000
gtkwave::/View/Scale_To_Time_Dimension/ms
gtkwave::/Edit/Set_Trace_Max_Hier 1
set out [file dirname [file normalize [info script]]]
gtkwave::/File/Write_Save_File_As [file join $out first_two.gtkw]
set shown [gtkwave::getDisplayedSignals]
set log [open [file join $out validation_first_two.log] w]
puts $log "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"
close $log
gtkwave::/File/Quit
