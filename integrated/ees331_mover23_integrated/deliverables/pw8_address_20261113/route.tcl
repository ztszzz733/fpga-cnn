set_param general.maxThreads 1
open_checkpoint {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_pw8_addr_retry_20261113_203458/1/synth.dcp}
opt_design
place_design
phys_opt_design
route_design
report_timing_summary -max_paths 10 -file {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_pw8_addr_retry_20261113_203458/1/implemented_timing.rpt}
report_utilization -file {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_pw8_addr_retry_20261113_203458/1/implemented_utilization.rpt}
write_checkpoint -force {C:/Users/windows/.codex/visualizations/2026/10/09/01a11f57-abad-73d3-bace-ffb2cb9844cd/resource_pw8_addr_retry_20261113_203458/1/routed.dcp}
puts ADDR_ROUTE_COMPLETE
exit 0
