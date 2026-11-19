set_param general.maxThreads 1
create_project -in_memory -part xc7z020clg484-1
read_verilog -sv {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/cnn_k1_bounds_timing/rtl/cnn_simple_top.sv}
read_verilog -sv {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/cnn_k1_bounds_timing/rtl/compact_word_ram.sv}
read_verilog -sv {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/cnn_k1_bounds_timing/rtl/simple_k1_engine.sv}
read_verilog -sv {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/cnn_k1_bounds_timing/rtl/simple_k3_engine.sv}
read_verilog -sv {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/cnn_k1_bounds_timing/rtl/simple_mem_bridge.sv}
read_xdc {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/cnn_k1_bounds_timing/synthesis/clock.xdc}
synth_design -top cnn_simple_top -part xc7z020clg484-1 -mode out_of_context -flatten_hierarchy rebuilt
write_checkpoint -force {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/cnn_k1_bounds_timing/synthesis/synth.dcp}
report_utilization -file {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/cnn_k1_bounds_timing/synthesis/utilization.rpt}
report_utilization -hierarchical -file {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/cnn_k1_bounds_timing/synthesis/hierarchy.rpt}
check_timing -verbose -file {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/cnn_k1_bounds_timing/synthesis/check_timing.rpt}
report_timing_summary -delay_type min_max -report_unconstrained -max_paths 10 -file {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/cnn_k1_bounds_timing/synthesis/timing.rpt}
report_timing -delay_type max -max_paths 20 -nworst 1 -input_pins -file {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/cnn_k1_bounds_timing/synthesis/paths.rpt}
puts SIMPLE_CNN_SYNTH_COMPLETE
exit 0
