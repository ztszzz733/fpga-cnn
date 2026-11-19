set_param general.maxThreads 2
set output [file dirname [file normalize [info script]]]
set checkpoint [file join $output .. synthesis synth.dcp]
if {[llength $argv]==1} {set checkpoint [lindex $argv 0]}
open_checkpoint $checkpoint
# The parent design supplies the clock. This OOC run assumes a concrete BUFG.
set_property HD.CLK_SRC BUFGCTRL_X0Y0 [get_ports clk]
opt_design
place_design
phys_opt_design
route_design
report_route_status -file [file join $output route_status.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -file [file join $output timing.rpt]
report_timing -delay_type max -max_paths 10 -file [file join $output paths.rpt]
report_utilization -file [file join $output utilization.rpt]
puts "CNN_OOC_ROUTE_DONE"
exit 0

