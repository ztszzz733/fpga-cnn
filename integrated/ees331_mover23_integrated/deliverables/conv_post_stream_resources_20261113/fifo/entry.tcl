set_param general.maxThreads 1
create_project -in_memory -part xc7z020clg484-1
read_verilog -sv {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_post_stream_20261113_214236/fifo/resource_fifo.sv}
read_xdc {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_post_stream_20261113_214236/fifo/clock.xdc}
synth_design -top resource_fifo -part xc7z020clg484-1 -mode out_of_context -flatten_hierarchy rebuilt
report_utilization -file {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_post_stream_20261113_214236/fifo/utilization.rpt}
report_utilization -hierarchical -file {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_post_stream_20261113_214236/fifo/hierarchical.rpt}
write_checkpoint -force {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_post_stream_20261113_214236/fifo/synth.dcp}
puts STREAM_RESOURCE_PASS
exit 0
