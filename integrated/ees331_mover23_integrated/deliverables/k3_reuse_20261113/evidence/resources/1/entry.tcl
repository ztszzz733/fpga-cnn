set_param general.maxThreads 1
create_project -in_memory -part xc7z020clg484-1
read_verilog -sv {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_k3_reuse_20261113_153959/compact_word_ram.sv}
read_verilog -sv {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_k3_reuse_20261113_153959/self_conv_spatial4_engine.sv}
read_verilog -sv {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_k3_reuse_20261113_153959/resource_k3.sv}
read_xdc {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_k3_reuse_20261113_153959/1/clock.xdc}
synth_design -top resource_k3 -part xc7z020clg484-1 -mode out_of_context -flatten_hierarchy rebuilt -generic READ_WORD_BUFFER=1
report_utilization -file {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_k3_reuse_20261113_153959/1/utilization.rpt}
report_utilization -hierarchical -file {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_k3_reuse_20261113_153959/1/hierarchical.rpt}
puts WORD_BUFFER_RESOURCE_PASS
exit 0
