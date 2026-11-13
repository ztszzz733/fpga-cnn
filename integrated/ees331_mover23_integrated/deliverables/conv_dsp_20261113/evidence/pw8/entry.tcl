set_param general.maxThreads 1
create_project -in_memory -part xc7z020clg484-1
read_verilog -sv {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_dsp_fixed_20261113_195332/pw8/compact_word_ram.sv}
read_verilog -sv {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_dsp_fixed_20261113_195332/pw8/self_pw8_engine.sv}
read_verilog -sv {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_dsp_fixed_20261113_195332/pw8/resource_pw8.sv}
read_xdc {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_dsp_fixed_20261113_195332/pw8/clock.xdc}
synth_design -top resource_pw8 -part xc7z020clg484-1 -mode out_of_context -flatten_hierarchy rebuilt
report_utilization -file {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_dsp_fixed_20261113_195332/pw8/utilization.rpt}
report_timing_summary -max_paths 5 -file {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_dsp_fixed_20261113_195332/pw8/timing.rpt}
write_verilog -force -mode funcsim {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_dsp_fixed_20261113_195332/pw8/netlist.v}
set fd [open {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_conv_dsp_fixed_20261113_195332/pw8/dsp_cells.tsv} w]
puts $fd "cell\tMREG\tPREG\tAREG\tBREG"
foreach c [get_cells -hier -filter {REF_NAME == DSP48E1}] {puts $fd "$c\t[get_property MREG $c]\t[get_property PREG $c]\t[get_property AREG $c]\t[get_property BREG $c]"}
close $fd
puts CONV_DSP_SYNTH_COMPLETE
exit 0
