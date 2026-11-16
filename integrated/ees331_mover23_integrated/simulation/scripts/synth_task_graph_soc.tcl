set script_root [file dirname [file normalize [info script]]]
set variant [lindex $argv 0]
if {$variant ni {plan legacy}} {error "variant must be plan or legacy"}
set rtl_root [file normalize [file join $script_root ../..]]
set output [file join $rtl_root simulation build task_graph_synth_$variant]
file mkdir $output
set rom [file join $output firmware ees331_cpu program.mem]
file mkdir [file dirname $rom]
file copy -force [file join $rtl_root simulation firmware ees331_cpu program_ram_probe.mem] $rom
set fd [open [file join $rtl_root rtl filelists system_ees331_reduced.f] r]
set manifest [read $fd]
close $fd
set sources {}
foreach line [split $manifest "\n"] {
 set line [string trim $line]
 if {$line eq "" || [string index $line 0] eq "#"} {continue}
 lappend sources [file join $rtl_root $line]
}
cd $output
set_param general.maxThreads 2
read_verilog -sv $sources
set defines {EES331_EXTERNAL_PS}
set generics {POOL23=1}
if {$variant eq "plan"} {
 lappend defines EES331_PLAN_EXTERNAL
 lappend generics TASK_GRAPH_STORAGE=1
}
synth_design -top face_soc_ees331_mover_top -part xc7z020clg484-1 \
 -verilog_define $defines -generic $generics \
 -flatten_hierarchy rebuilt -no_iobuf
create_clock -period 10.000 -name FCLK_CLK0 [get_ports FCLK_CLK0]
report_utilization -file [file join $output utilization.rpt]
report_utilization -hierarchical -file [file join $output utilization_hierarchical.rpt]
report_timing_summary -file [file join $output timing_synth.rpt]
