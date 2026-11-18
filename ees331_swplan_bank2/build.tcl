set stage [lindex $argv 0]
set out [file normalize [lindex $argv 1]]
set src [file join $out source]
set reports [file join $out $stage]
file mkdir $reports
set_param general.maxThreads 2
open_project [file join $out project ees331_ddr.xpr]

proc require_completed {name {allow_failed_routed_timing 0}} {
 set run [get_runs $name]
 set status [get_property STATUS $run]
 set routed [expr {$allow_failed_routed_timing && $status eq "route_design Complete, Failed Timing!"}]
 if {!$routed && ([get_property PROGRESS $run] ne "100%" || ![string match {*Complete!} $status])} {
  error "$name did not complete: $status"
 }
}

if {$stage eq "synth"} {
 if {[lindex $argv 2] eq "reset_failed"} {
  set previous_status [get_property STATUS [get_runs synth_1]]
  if {![string match -nocase {*error*} $previous_status]} {
   error "Refusing to reset a run that has not failed: $previous_status"
  }
  reset_run synth_1
 }
 set manifest [open [file join $src rtl filelists system_ees331_reduced.f] r]
 set sources {}
 foreach line [split [read $manifest] \n] {
  set line [string trim $line]
  if {$line eq "" || [string match {#*} $line]} {continue}
  lappend sources [file join $src $line]
 }
 close $manifest
 add_files -norecurse $sources
 set rom [file join $src firmware ees331_cpu program.mem]
 add_files -norecurse $rom
 set_property file_type {Memory Initialization Files} [get_files $rom]
 set_property top face_soc_ees331_mover_top [get_filesets sources_1]
 set generics [list "IMEM_INIT_FILE=\"$rom\""]
 set local_config [file join $out local_kib.txt]
 if {[file exists $local_config]} {
  set f [open $local_config r]
  set local_kib [string trim [read $f]]
  close $f
  if {![string is integer -strict $local_kib] || $local_kib < 8 ||
      ($local_kib & ($local_kib-1)) != 0} {
   error "Expected a power-of-two LOCAL_BYTES configuration in KiB"
  }
  lappend generics "LOCAL_BYTES=[expr {$local_kib * 1024}]"
  puts "EES331_LOCAL_KIB=$local_kib"
 }
 set k1_config [file join $out k1_units.txt]
 if {[file exists $k1_config]} {
  set f [open $k1_config r]
  set k1_units [string trim [read $f]]
  close $f
  if {![string is integer -strict $k1_units] || $k1_units < 1 || $k1_units > 6} {
   error "Invalid K1_UNITS: $k1_units"
  }
  lappend generics "K1_UNITS=$k1_units"
  puts "EES331_K1_UNITS=$k1_units"
 }
 set_property generic $generics [get_filesets sources_1]
 # Avoid incompatible RAMB36E1 address cascade wiring on this 7-series part.
 set synth_run [get_runs synth_1]
 set args {-max_bram_cascade_height 1}
 if {[file exists [file join $out no_timing_driven_synthesis]]} {
  append args { -no_timing_driven}
 }
 if {[file exists [file join $out area_synthesis]]} {
  set_property STEPS.SYNTH_DESIGN.ARGS.DIRECTIVE AreaOptimized_high $synth_run
  append args { -control_set_opt_threshold 16 -resource_sharing on}
 }
 set_property -dict [list {STEPS.SYNTH_DESIGN.ARGS.MORE OPTIONS} $args] $synth_run
 update_compile_order -fileset sources_1
 launch_runs synth_1 -jobs 2
 wait_on_run synth_1
 require_completed synth_1
 open_run synth_1
} elseif {$stage in {impl impl_area impl_timing}} {
 require_completed synth_1
 set impl_name impl_1
 if {$stage eq "impl_area"} {
  set impl_name impl_area
  if {![llength [get_runs -quiet $impl_name]]} {
   create_run $impl_name -parent_run synth_1 -flow [get_property FLOW [get_runs impl_1]]
  }
  set_property STEPS.OPT_DESIGN.ARGS.DIRECTIVE ExploreSequentialArea [get_runs $impl_name]
 }
 if {[file exists [file join $out area_synthesis]]} {
  set_property STEPS.OPT_DESIGN.ARGS.DIRECTIVE ExploreArea [get_runs $impl_name]
 }
 if {$stage ne "impl_timing"} {
  if {[file exists [file join $out timing_closure]]} {
   set_property -dict {
    STEPS.PLACE_DESIGN.ARGS.DIRECTIVE Explore
    STEPS.PHYS_OPT_DESIGN.IS_ENABLED true
    STEPS.PHYS_OPT_DESIGN.ARGS.DIRECTIVE AggressiveExplore
    STEPS.ROUTE_DESIGN.ARGS.DIRECTIVE Explore
   } [get_runs $impl_name]
  }
  set_property STEPS.OPT_DESIGN.TCL.POST [file join $out logic_opt_post.tcl] [get_runs $impl_name]
  launch_runs $impl_name -to_step route_design -jobs 2
  wait_on_run $impl_name
 }
 require_completed $impl_name 1
 open_run $impl_name
 if {$stage eq "impl_timing"} {
  phys_opt_design -directive AggressiveExplore
  write_checkpoint -force [file join $reports optimized_routed.dcp]
 }
 report_route_status -file [file join $reports route_status.rpt]
 report_methodology -file [file join $reports methodology.rpt]
} else {
 error "Unknown stage $stage"
}

report_clocks -file [file join $reports clocks.rpt]
report_utilization -file [file join $reports utilization.rpt]
report_utilization -hierarchical -file [file join $reports utilization_hierarchical.rpt]
report_timing_summary -delay_type min_max -max_paths 10 -report_unconstrained -file [file join $reports timing_summary.rpt]
report_drc -file [file join $reports drc.rpt]

if {$stage eq "synth"} {
 if {[catch {write_hw_platform -fixed -force -file [file join $reports ees331_nobit.xsa]} reason]} {
  puts "EES331_XSA_PENDING: $reason"
 }
} else {
 set setup [get_timing_paths -delay_type max -max_paths 1]
 set hold [get_timing_paths -delay_type min -max_paths 1]
 if {![llength $setup] || ![llength $hold]} {error "No timed paths in routed design"}
 set wns [get_property SLACK $setup]
 set whs [get_property SLACK $hold]
 puts "EES331_ROUTED_SLACK WNS=$wns WHS=$whs"
 if {$wns < 0 || $whs < 0} {error "Routed timing failed; see timing_summary.rpt"}
 set pw [report_pulse_width -return_string]
 set f [open [file join $reports pulse_width.rpt] w]
 puts $f $pw
 close $f
 if {[regexp {\(VIOLATED\)|Slack\s+\(VIOLATED\)} $pw]} {error "Routed pulse width failed"}
 # Use the project run's standard filename so the XSA exporter can locate it.
 set bit [file join [get_property DIRECTORY [get_runs $impl_name]] face_soc_ees331_mover_top.bit]
 write_bitstream -force $bit
 file copy -force $bit [file join $reports ees331_mover.bit]
 write_hw_platform -fixed -include_bit -force -file [file join $reports ees331.xsa]
}
puts "EES331_STAGE_COMPLETE $stage"
exit 0
