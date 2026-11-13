set_param general.maxThreads 1
create_project -in_memory -part xc7z020clg484-1
read_verilog -sv {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_dsp_20261113_194810/k3/compact_word_ram.sv}
read_verilog -sv {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_dsp_20261113_194810/k3/self_conv_spatial4_engine.sv}
read_verilog -sv {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_dsp_20261113_194810/k3/resource_k3.sv}
read_xdc {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_dsp_20261113_194810/k3/clock.xdc}
synth_design -top resource_k3 -part xc7z020clg484-1 -mode out_of_context -flatten_hierarchy rebuilt -generic READ_WORD_BUFFER=1
report_utilization -file {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_dsp_20261113_194810/k3/utilization.rpt}
report_timing_summary -max_paths 5 -file {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_dsp_20261113_194810/k3/timing.rpt}
write_verilog -force -mode funcsim {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_dsp_20261113_194810/k3/netlist.v}
set fd [open {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_dsp_20261113_194810/k3/dsp_cells.tsv} w]
puts $fd "cell\tMREG\tPREG\tAREG\tBREG"
foreach c [get_cells -hier -filter {REF_NAME == DSP48E1}] {puts $fd "$c\t[get_property MREG $c]\t[get_property PREG $c]\t[get_property AREG $c]\t[get_property BREG $c]"}
close $fd
puts CONV_DSP_SYNTH_COMPLETE
exit 0
