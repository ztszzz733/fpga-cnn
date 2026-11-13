set root [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
set local_bytes [lindex $argv 2]
file mkdir $out
set_param general.maxThreads 1
set fp [open [file join $root rtl filelists system_ees331_reduced.f] r]
set sources {}
foreach line [split [read $fp] \n] {
 set line [string trim $line]
 if {$line ne "" && ![string match {#*} $line]} {lappend sources [file join $root $line]}
}
close $fp
file mkdir [file join [pwd] firmware ees331_cpu]
file copy -force [file join $root firmware ees331_cpu program.mem] [file join [pwd] firmware ees331_cpu program.mem]
read_verilog -sv $sources
synth_design -top face_soc_ees331_mover_top -part xc7z020clg484-1 -mode out_of_context -verilog_define EES331_EXTERNAL_PS -generic LOCAL_BYTES=$local_bytes -flatten_hierarchy rebuilt
report_utilization -file [file join $out utilization.rpt]
report_utilization -hierarchical -file [file join $out hierarchy.rpt]
puts REDUCED_BRAM_SYNTH_COMPLETE
exit 0
