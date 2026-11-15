# Full PL synthesis with external PS7 AXI ports. This counts CPU, 23 CNN
# operators, scheduler, 16 KiB CPU RAM, and the DDR-facing cache together.
# Usage: vivado -mode batch -source synth_ees331_pool23_pl.tcl -tclargs ROOT OUT
set root [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
file mkdir $out
# Vivado's Windows parallel worker fails when its current directory contains
# parentheses. Run from a simple directory and stage the relative ROM there.
set rom_stage [file join [pwd] firmware ees331_cpu program.mem]
file mkdir [file dirname $rom_stage]
file copy -force [file join $root firmware ees331_cpu program.mem] $rom_stage
set_param general.maxThreads 2
set part xc7z020clg484-1
set fp [open [file join $root rtl filelists system_ees331.f] r]
set sources {}
foreach line [split [read $fp] \n] {
 set line [string trim $line]
 if {$line eq "" || [string match {#*} $line]} {continue}
 lappend sources [file join $root $line]
}
close $fp
read_verilog -sv $sources
set rc [catch {
 synth_design -top face_soc_ees331_top -part $part -verilog_define EES331_EXTERNAL_PS -generic POOL23=1 -flatten_hierarchy rebuilt -no_iobuf
} message options]
set log [open [file join $out synth_status.txt] w]
puts $log "part=$part"
puts $log "top=face_soc_ees331_top"
puts $log "POOL23=1"
puts $log "result=[expr {$rc ? {FAIL} : {PASS}}]"
puts $log "message=$message"
close $log
if {$rc} {
 puts stderr "POOL23_SYNTH_FAIL $message"
 exit 1
}
report_utilization -file [file join $out utilization.rpt]
report_utilization -hierarchical -file [file join $out utilization_hierarchical.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -file [file join $out timing_summary.rpt]
write_checkpoint -force [file join $out ees331_pool23_pl.dcp]
puts "POOL23_SYNTH_COMPLETE"
exit 0
