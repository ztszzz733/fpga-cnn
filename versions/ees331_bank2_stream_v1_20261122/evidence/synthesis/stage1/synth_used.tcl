set project_root [file normalize [lindex $argv 0]]
set output [file normalize [lindex $argv 1]]
file mkdir $output
set_param general.maxThreads 2
create_project -in_memory -part xc7z020clg484-1
set manifest [open [file join $project_root simple_cnn soc.f] r]
set sources {}
foreach line [split [read $manifest] \n] {
 set line [string trim $line]
 if {$line eq "" || [string match {#*} $line]} {continue}
 set path [file normalize [file join $project_root simple_cnn $line]]
 if {![file exists $path]} {error "Missing source: $path"}
 lappend sources $path
}
close $manifest
set_property verilog_define EES331_EXTERNAL_PS [current_fileset]
read_verilog -sv $sources
set constraints [file join $output clock.xdc]
set fd [open $constraints w]
puts $fd {create_clock -name FCLK_CLK0 -period 10.000 [get_ports FCLK_CLK0]}
close $fd
read_xdc $constraints
set rom [file join $project_root source firmware ees331_cpu program.mem]
set options [list LOCAL_BYTES=401408 POOL23=1 "IMEM_INIT_FILE=\"$rom\""]
set code [catch {
 synth_design -top face_soc_ees331_simple_top -part xc7z020clg484-1 -verilog_define EES331_EXTERNAL_PS \
  -generic $options -flatten_hierarchy rebuilt -no_iobuf -max_bram_cascade_height 1
 report_utilization -file [file join $output utilization.rpt]
 report_utilization -hierarchical -file [file join $output hierarchy.rpt]
 check_timing -verbose -file [file join $output check_timing.rpt]
 report_timing_summary -delay_type min_max -report_unconstrained -max_paths 10 -file [file join $output timing.rpt]
 report_timing -delay_type max -max_paths 10 -nworst 1 -input_pins -file [file join $output paths.rpt]
 write_checkpoint -force [file join $output soc_synth.dcp]
 set black_boxes [get_cells -hier -filter {IS_BLACKBOX == 1}]
 if {[llength $black_boxes]} {error "Unresolved black boxes: $black_boxes"}
} message]
set fd [open [file join $output status.txt] w]
puts $fd "variant=stage1_local_stream"
puts $fd "base_commit=b165edc176e14a51c57f4937a7681cd510974c68"
puts $fd "top=face_soc_ees331_simple_top"
puts $fd "part=xc7z020clg484-1"
puts $fd "LOCAL_BYTES=401408;POOL23=1;CNN_CLIENTS=4"
puts $fd "clock_period_ns=10.000;external_ps=1;no_iobuf=1;flatten_hierarchy=rebuilt"
puts $fd "result=[expr {$code ? {FAIL} : {PASS}}]"
puts $fd "message=$message"
close $fd
if {$code} {puts stderr "BANK2_SOC_SYNTH_FAIL $message";exit 1}
puts BANK2_SOC_SYNTH_COMPLETE
exit 0
