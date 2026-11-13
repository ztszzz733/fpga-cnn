#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$project_dir/build/fetch"
tmp_dir="$project_dir/build/tmp"
rm -rf "$build_dir"
mkdir -p "$build_dir" "$tmp_dir"
export TMPDIR="$tmp_dir" TMP="$tmp_dir" TEMP="$tmp_dir"
verilator --version
verilator --binary --timing --assert -Wall \
  --Mdir "$build_dir" --top-module tb_fetch_adapter \
  "$project_dir/rtl/cpu_datapath/fetch_adapter.sv" \
  "$project_dir/tb/unit/tb_fetch_adapter.sv"
"$build_dir/Vtb_fetch_adapter"
