#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$project_dir/build/lsu"
tmp_dir="$project_dir/build/tmp"
rm -rf "$build_dir"
mkdir -p "$build_dir" "$tmp_dir"
export TMPDIR="$tmp_dir" TMP="$tmp_dir" TEMP="$tmp_dir"
verilator --version
# The shared C1 package intentionally contains symbols used by non-LSU units.
verilator --binary --timing --assert -Wall -Wno-UNUSEDPARAM \
  --Mdir "$build_dir" --top-module tb_lsu_address_decoder \
  "$project_dir/rtl/common/cpu_control_pkg.sv" \
  "$project_dir/rtl/cpu_datapath/address_decoder.sv" \
  "$project_dir/rtl/cpu_datapath/lsu.sv" \
  "$project_dir/tb/unit/tb_lsu_address_decoder.sv"
"$build_dir/Vtb_lsu_address_decoder"
