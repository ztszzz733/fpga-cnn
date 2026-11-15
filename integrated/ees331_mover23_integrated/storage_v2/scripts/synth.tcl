set root [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
set selected [lindex $argv 2]
file mkdir $out
set_param general.maxThreads 2
foreach config {{ram8 8192 1} {ram16 16384 1} {ram64 65536 1} {data16 16384 0} {mover 0 0} {tile_ram 0 0} {tile_system 0 0} {loader_system 0 0}} {
 lassign $config name bytes rom
 if {$selected ne "" && $selected ne $name} {continue}
 create_project -in_memory -part xc7z020clg484-1
 set dir [file join $out $name];file mkdir $dir
 if {$name eq "mover"} {
  read_verilog -sv [file join $root rtl data_mover.sv]
  synth_design -top data_mover -mode out_of_context -part xc7z020clg484-1
 } elseif {$name eq "tile_ram"} {
  read_verilog -sv [file join $root rtl tile_local_ram.sv]
  synth_design -top tile_local_ram -mode out_of_context -part xc7z020clg484-1
 } elseif {$name eq "tile_system"} {
  foreach source {tile_row_dma.sv data_mover.sv tile_local_ram.sv tile_dma_system.sv} {
   read_verilog -sv [file join $root rtl $source]
  }
  synth_design -top tile_dma_system -mode out_of_context -part xc7z020clg484-1
 } elseif {$name eq "loader_system"} {
  read_verilog -sv [file join $root rtl download_ram.sv]
  read_verilog -sv [file join $root rtl program_loader_csr.sv]
  read_verilog -sv [file join $root tb program_loader_top.sv]
  synth_design -top program_loader_top -mode out_of_context -part xc7z020clg484-1
 } else {
  read_verilog -sv [file join $root rtl download_ram.sv]
  set base [expr {$rom ? 0 : 65536}]
  synth_design -top download_ram -mode out_of_context -part xc7z020clg484-1 -generic BYTES=$bytes -generic BASE=$base -generic READ_ONLY_CPU=$rom
 }
 create_clock -name clk -period 20 [get_ports clk]
 report_utilization -file [file join $dir utilization.rpt]
 report_timing_summary -file [file join $dir timing.rpt]
 set fp [open [file join $dir counts.tsv] w]
 foreach ref {RAMB36E1 RAMB18E1 LUT1 LUT2 LUT3 LUT4 LUT5 LUT6 FDRE FDCE} {
  puts $fp "$ref\t[llength [get_cells -hier -filter [format {REF_NAME == %s} $ref]]]"
 }
 close $fp
 puts "PASS_SYNTH $name"
 close_project
}
