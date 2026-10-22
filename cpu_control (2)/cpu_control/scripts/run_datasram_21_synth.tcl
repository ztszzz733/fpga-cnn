# Out-of-context synthesis check for the CNN storage contract configuration.
# Usage from the project root:
#   vivado -mode batch -source scripts/run_datasram_21_synth.tcl \
#     -tclargs build/datasram_21_synth_50mhz 20.000

set script_dir [file dirname [file normalize [info script]]]
set root_dir [file normalize [file join $script_dir ..]]
set out_dir [file normalize [expr {$argc > 0 ? [lindex $argv 0] : [file join $root_dir build datasram_21_synth]}]]
set clock_period_ns [expr {$argc > 1 ? [lindex $argv 1] : 20.000}]
file mkdir $out_dir

read_verilog -sv [list [file join $root_dir rtl overlap datasram_banked.sv]]
synth_design -mode out_of_context -top datasram_banked -part xc7z020clg400-1 \
    -generic {SRAM_BASE=0 SRAM_SIZE=262144 BANKS=4 CLIENTS=21}
create_clock -name datasram_clk -period $clock_period_ns [get_ports clk]
set_property HD.CLK_SRC BUFGCTRL_X0Y0 [get_ports clk]

opt_design
place_design
phys_opt_design
route_design

report_utilization -file [file join $out_dir utilization.rpt]
report_timing_summary -delay_type max -max_paths 10 -file [file join $out_dir timing_summary.rpt]
report_clock_utilization -file [file join $out_dir clock_utilization.rpt]
report_route_status -file [file join $out_dir route_status.rpt]
write_checkpoint -force [file join $out_dir datasram_banked_21_xc7z020.dcp]

set worst_path [lindex [get_timing_paths -delay_type max -max_paths 1] 0]
set wns [get_property SLACK $worst_path]
set timing_pass [expr {$wns >= 0.0}]

set summary [open [file join $out_dir summary.txt] w]
puts $summary "part=xc7z020clg400-1"
puts $summary "clients=21"
puts $summary "banks=4"
puts $summary "sram_bytes=262144"
puts $summary "clock_period_ns=$clock_period_ns"
puts $summary "wns_ns=$wns"
puts $summary "status=[expr {$timing_pass ? {PASS} : {FAIL_TIMING}}]"
close $summary

if {!$timing_pass} {
    error "timing failed at period $clock_period_ns ns with WNS $wns ns"
}
