gtkwave::setZoomRangeTimes 114244650000 114244750000
gtkwave::/View/Scale_To_Time_Dimension/us
gtkwave::/Edit/Set_Trace_Max_Hier 1
set out [file dirname [file normalize [info script]]]
gtkwave::/File/Write_Save_File_As [file join $out frame_2_write.gtkw]
set shown [gtkwave::getDisplayedSignals]
set log [open [file join $out validation_frame_2_write.log] w]
puts $log "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"
close $log
gtkwave::/File/Quit
