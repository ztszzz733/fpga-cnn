# Synchronous RAM inference check; run from project root, argv output directory.
set root [pwd]
set out [file normalize [lindex $argv 0]]
file mkdir $out
set_param general.maxThreads 2
foreach top {quant_post_bram_engine dw7_bram_engine} {
 create_project -in_memory -part xc7z020clg484-1
 read_verilog -sv [list [file join $root rtl cnn_ddr ${top}.sv]]
 if {$top eq "dw7_bram_engine"} {set generics {MAX_WIDTH=7 MAX_CHANNELS=512 LANES=8}} else {set generics {MAX_CHANNELS=512}}
 synth_design -top $top -part xc7z020clg484-1 -mode out_of_context -flatten_hierarchy rebuilt -generic $generics
 report_utilization -file [file join $out ${top}_utilization.rpt]
 write_checkpoint -force [file join $out ${top}.dcp]
 close_project
}
puts EES331_OPERATORS_SYNTH_PASS
exit 0
