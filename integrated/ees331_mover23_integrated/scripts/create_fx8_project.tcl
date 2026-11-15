# Run in the Vivado Tcl console: source {<project-root>/scripts/create_fx8_project.tcl}
# Creates a separate project without overwriting existing projects or launching runs.
set fx8_root [file normalize [file join [file dirname [info script]] ..]]
set fx8_project_dir [file join $fx8_root build vivado_fx8]
if {[file exists $fx8_project_dir]} {error "Project directory already exists: $fx8_project_dir"}
set fx8_list [open [file join $fx8_root rtl filelists system_neureka_fx8.f] r]
set fx8_lines [split [read $fx8_list] \n]
close $fx8_list
set fx8_sources {};set fx8_includes {};set fx8_defines {}
foreach line $fx8_lines {
    set line [string trim $line]
    if {$line eq "" || [string match {#*} $line]} {continue}
    if {[string first "+define+" $line]==0} {
        lappend fx8_defines [string range $line 8 end]
    } elseif {[string first "+incdir+" $line]==0} {
        lappend fx8_includes [file join $fx8_root [string range $line 8 end]]
    } else {
        set path [file join $fx8_root $line]
        if {![file isfile $path]} {error "Missing production dependency: $path"}
        lappend fx8_sources $path
    }
}
create_project neureka_fx8 $fx8_project_dir -part xc7z020clg484-1
set_property target_language Verilog [current_project]
set_property include_dirs $fx8_includes [current_fileset]
set_property verilog_define $fx8_defines [current_fileset]
add_files -norecurse $fx8_sources
set_property file_type SystemVerilog [get_files -of_objects [current_fileset]]
set_property top face_soc_neureka_fx8_top [current_fileset]
foreach name {ees331_board.xdc ees331_fx8_pins.xdc ees331_fx8_timing.xdc} {
    add_files -fileset constrs_1 -norecurse [list [file join $fx8_root constraints $name]]
}
# This file targets synthesized divider/synchronizer cells; apply after synthesis.
set_property USED_IN_SYNTHESIS false [get_files ees331_fx8_timing.xdc]
set_property PROCESSING_ORDER LATE [get_files ees331_fx8_timing.xdc]
update_compile_order -fileset sources_1
puts "Created FX8 project: $fx8_project_dir"
puts "Set IMEM_INIT_FILE and provide application SRAM initialization before board use."
