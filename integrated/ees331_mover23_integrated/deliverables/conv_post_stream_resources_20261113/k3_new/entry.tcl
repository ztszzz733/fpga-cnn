set_param general.maxThreads 1
create_project -in_memory -part xc7z020clg484-1
read_verilog -sv {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_post_stream_20261113_214236/k3_new/compact_word_ram.sv}
read_verilog -sv {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_post_stream_20261113_214236/k3_new/self_conv_spatial4_engine.sv}
read_verilog -sv {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_post_stream_20261113_214236/k3_new/quant_post_pipe_engine.sv}
read_verilog -sv {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_post_stream_20261113_214236/k3_new/conv_post_pair_engine.sv}
read_verilog -sv {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_post_stream_20261113_214236/k3_new/resource_pair.sv}
read_xdc {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_post_stream_20261113_214236/k3_new/clock.xdc}
synth_design -top resource_pair -part xc7z020clg484-1 -mode out_of_context -flatten_hierarchy rebuilt
report_utilization -file {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_post_stream_20261113_214236/k3_new/utilization.rpt}
report_utilization -hierarchical -file {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_post_stream_20261113_214236/k3_new/hierarchical.rpt}
write_checkpoint -force {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_post_stream_20261113_214236/k3_new/synth.dcp}
puts STREAM_RESOURCE_PASS
exit 0
