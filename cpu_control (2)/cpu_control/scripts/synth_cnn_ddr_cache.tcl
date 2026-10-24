set root [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
set part [lindex $argv 2]
set period [lindex $argv 3]
set_param general.maxThreads 2
create_project -in_memory -part $part
foreach name {cnn_cache.sv cnn_ddr_bridge.sv datasram_ddr_subsystem.sv} {
 read_verilog -sv [list [file join $root rtl cnn_ddr $name]]
}
set fp [open [file join $out clock.xdc] w]
puts $fp "create_clock -name clk -period $period \[get_ports clk\]"
close $fp
read_xdc [list [file join $out clock.xdc]]
synth_design -top datasram_ddr_subsystem -part $part -mode out_of_context -flatten_hierarchy rebuilt
report_utilization -file [file join $out utilization.rpt]
report_utilization -hierarchical -file [file join $out utilization_hierarchical.rpt]
report_timing_summary -delay_type max -max_paths 10 -report_unconstrained -file [file join $out timing_summary.rpt]
write_checkpoint -force [file join $out datasram_ddr_subsystem_synth.dcp]
set fp [open [file join $out primitive_counts.tsv] w]
foreach ref {LUT1 LUT2 LUT3 LUT4 LUT5 LUT6 LUT6_2 FDRE FDSE FDCE FDPE RAMB18E1 RAMB36E1 DSP48E1} {
 puts $fp "$ref\t[llength [get_cells -hierarchical -filter [format {REF_NAME == %s} $ref]]]"
}
set paths [get_timing_paths -delay_type max -max_paths 1]
if {[llength $paths]} {puts $fp "worst_setup_slack_ns\t[get_property SLACK [lindex $paths 0]]"}
close $fp
puts CNN_DDR_CACHE_SYNTH_COMPLETE
exit 0
