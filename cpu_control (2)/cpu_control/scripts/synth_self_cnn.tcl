# Vivado OOC only. argv: project root, result directory, FPGA part, period ns,
# top module, self_conv_engine MAX_KERNEL (only for standalone convolution).
set root [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
set part [lindex $argv 2]
set period [lindex $argv 3]
set top [lindex $argv 4]
set max_kernel [lindex $argv 5]
set_param general.maxThreads 2
create_project -in_memory -part $part
set fp [open [file join $root rtl filelists cnn_self.f] r]
set sources {}
foreach line [split [read $fp] "\n"] {
 set line [string trim $line]
 if {$line eq "" || [string match {#*} $line] || [string match {//*} $line]} {continue}
 lappend sources [file join $root $line]
}
close $fp
read_verilog -sv $sources
set xdc [file join $out clock.xdc]
set fp [open $xdc w]
puts $fp "create_clock -name clk -period $period \[get_ports clk\]"
close $fp
read_xdc [list $xdc]
if {$top eq "self_network_top"} {
 set generics {MAX_TASKS=64}
} else {
 set generics [list MAX_CHANNELS=512 MAX_KERNEL=$max_kernel TILE=2]
}
synth_design -top $top -part $part -mode out_of_context -flatten_hierarchy rebuilt -generic $generics
report_utilization -file [file join $out utilization.rpt]
report_utilization -hierarchical -file [file join $out utilization_hierarchical.rpt]
report_timing_summary -delay_type max -max_paths 10 -report_unconstrained -file [file join $out timing_summary.rpt]
write_checkpoint -force [file join $out ${top}_synth.dcp]
set fp [open [file join $out primitive_counts.tsv] w]
foreach ref {LUT1 LUT2 LUT3 LUT4 LUT5 LUT6 LUT6_2 FDRE FDSE FDCE FDPE RAMB18E1 RAMB36E1 DSP48E1} {
 set count [llength [get_cells -hierarchical -filter [format {REF_NAME == %s} $ref]]]
 puts $fp "$ref\t$count"
}
set paths [get_timing_paths -delay_type max -max_paths 1]
if {[llength $paths]} {puts $fp "worst_setup_slack_ns\t[get_property SLACK [lindex $paths 0]]"}
close $fp
puts SELF_CNN_SYNTH_COMPLETE
exit 0
