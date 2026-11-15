#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$project_dir/build/pkg"
tmp_dir="$project_dir/build/tmp"
mkdir -p "$build_dir" "$tmp_dir"
export TMPDIR="$tmp_dir" TMP="$tmp_dir" TEMP="$tmp_dir"
verilator --version
verilator --binary --timing --assert -Wall \
  --Mdir "$build_dir" --top-module tb_cpu_control_pkg \
  "$project_dir/rtl/common/cpu_control_pkg.sv" \
  "$project_dir/tb/unit/tb_cpu_control_pkg.sv"
"$build_dir/Vtb_cpu_control_pkg"
