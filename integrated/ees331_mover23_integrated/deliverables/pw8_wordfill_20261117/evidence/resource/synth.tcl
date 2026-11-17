set_param general.maxThreads 1
create_project -in_memory -part xc7z020clg484-1
read_verilog -sv {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/pw8_wordfill_20261117/resource_runs/20261117_155457/compact_word_ram.sv}
read_verilog -sv {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/pw8_wordfill_20261117/resource_runs/20261117_155457/self_pw8_engine.sv}
read_verilog -sv {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/pw8_wordfill_20261117/resource_runs/20261117_155457/resource_pw8.sv}
read_xdc {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/pw8_wordfill_20261117/resource_runs/20261117_155457/clock.xdc}
synth_design -top resource_pw8 -part xc7z020clg484-1 -mode out_of_context -flatten_hierarchy rebuilt
report_utilization -file {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/pw8_wordfill_20261117/resource_runs/20261117_155457/utilization.rpt}
report_utilization -hierarchical -file {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/pw8_wordfill_20261117/resource_runs/20261117_155457/hierarchical.rpt}
report_timing_summary -max_paths 5 -file {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/pw8_wordfill_20261117/resource_runs/20261117_155457/timing.rpt}
write_checkpoint -force {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/pw8_wordfill_20261117/resource_runs/20261117_155457/synth.dcp}
puts WORD_FILL_RESOURCE_COMPLETE
exit 0
