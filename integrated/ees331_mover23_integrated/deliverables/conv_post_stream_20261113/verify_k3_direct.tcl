set out [file dirname [file normalize [info script]]]
gtkwave::setZoomRangeTimes 0 80310000
gtkwave::/View/Scale_To_Time_Dimension/us
gtkwave::/File/Write_Save_File_As [file join $out k3_direct.gtkw]
set shown [gtkwave::getDisplayedSignals]
set f [open [file join $out validation_k3_direct.log] w]
puts $f "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"
foreach s $shown {puts $f $s}
if {[llength $shown]==16 && [llength [lsort -unique $shown]]==16} {puts $f PASS} else {puts $f FAIL}
close $f
gtkwave::/File/Quit
