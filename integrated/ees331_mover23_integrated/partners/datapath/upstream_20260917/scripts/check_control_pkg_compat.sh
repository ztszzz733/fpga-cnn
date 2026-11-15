#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
control_dir="$(cd "$project_dir/../incoming/cpu_control" && pwd)"
build_dir="$project_dir/build/control_pkg_compat"
tmp_dir="$project_dir/build/tmp"
mkdir -p "$build_dir" "$tmp_dir"
export TMPDIR="$tmp_dir" TMP="$tmp_dir" TEMP="$tmp_dir"
verilator --version
# The M-side package is deliberately omitted. Only the Datapath candidate is compiled.
# These two narrowly scoped categories are expected here: C1 reserves clk and
# mul_busy, while a shared package necessarily has symbols used by only one side.
# Every other lint category remains enabled and fatal.
verilator --lint-only -Wall -Wno-UNUSEDSIGNAL -Wno-UNUSEDPARAM \
  --Mdir "$build_dir" --top-module cpu_control \
  "$project_dir/rtl/common/cpu_control_pkg.sv" \
  "$control_dir/rtl/cpu_control/main_decoder.sv" \
  "$control_dir/rtl/cpu_control/alu_decoder.sv" \
  "$control_dir/rtl/cpu_control/hazard_unit.sv" \
  "$control_dir/rtl/cpu_control/branch_control.sv" \
  "$control_dir/rtl/cpu_control/pipeline_control.sv" \
  "$control_dir/rtl/cpu_control/cpu_control.sv"
echo "PASS: M Control compiles with Datapath cpu_control_pkg"
