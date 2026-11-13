set f [open validation_operator_names.log w]
set names [gtkwave::getDisplayedSignals]
puts $f "DISPLAYED=[llength $names]"
puts $f "TRACES=$names"
gtkwave::setMarker 120000000000
foreach n {K3_0_STATE K3_1_STATE K3_2_STATE K3_3_STATE K1_0_STATE PAD_STATE} {
 catch {puts $f "$n=[gtkwave::getTraceValueAtMarkerFromName $n]"} err
 if {$err ne ""} {puts $f "LOOKUP=$err"}
}
close $f
gtkwave::/File/Quit
