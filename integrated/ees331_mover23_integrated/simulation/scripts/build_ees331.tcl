# ROOT PROJECT_DIR synth|impl REPORT_DIR. Continue an actual PS7 BD project.
set root [file normalize [lindex $argv 0]]
set project [file normalize [lindex $argv 1]]
set stage [lindex $argv 2]
set out [file normalize [lindex $argv 3]]
set_param general.maxThreads 2
open_project [file join $project ees331_ddr.xpr]
set fp [open [file join $root rtl filelists system_ees331.f] r]
set sources {}
foreach line [split [read $fp] \n] {
 set line [string trim $line]
 if {$line eq "" || [string match {#*} $line]} {continue}
 lappend sources [file join $root $line]
}
close $fp
add_files -norecurse $sources
set rom [file join $root firmware ees331_cpu program.mem]
add_files -norecurse $rom
set_property file_type {Memory Initialization Files} [get_files $rom]
set_property top face_soc_ees331_top [get_filesets sources_1]
set_property generic [list "IMEM_INIT_FILE=\"[string map {\\ /} $rom]\""] [get_filesets sources_1]
set_property STEPS.SYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY rebuilt [get_runs synth_1]
update_compile_order -fileset sources_1
if {$stage eq "synth"} {
 reset_run synth_1
 launch_runs synth_1 -jobs 2
 wait_on_run synth_1
 if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "Synthesis incomplete: [get_property STATUS [get_runs synth_1]]"}
 open_run synth_1
} else {
 launch_runs impl_1 -to_step write_bitstream -jobs 2
 wait_on_run impl_1
 if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "Implementation incomplete: [get_property STATUS [get_runs impl_1]]"}
 open_run impl_1
}
report_utilization -file [file join $out utilization.rpt]
report_utilization -hierarchical -file [file join $out utilization_hierarchical.rpt]
report_timing_summary -delay_type min_max -max_paths 10 -report_unconstrained -file [file join $out timing_summary.rpt]
report_drc -file [file join $out drc.rpt]
write_checkpoint -force [file join $out ees331_$stage.dcp]
if {$stage eq "impl"} {
 write_hw_platform -fixed -include_bit -force -file [file join $out ees331_ddr.xsa]
}
puts "EES331_BUILD_COMPLETE $stage"
exit 0
