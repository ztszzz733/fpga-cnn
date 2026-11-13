#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$project_dir/build/base_modules"
mkdir -p "$build_dir"
verilator --binary --timing --assert -Wall -Wno-fatal \
  --Mdir "$build_dir" --top-module tb_base_modules \
  "$project_dir/rtl/common/cpu_control_pkg.sv" \
  "$project_dir/rtl/cpu_datapath/alu.sv" \
  "$project_dir/rtl/cpu_datapath/imm_gen.sv" \
  "$project_dir/rtl/cpu_datapath/pc.sv" \
  "$project_dir/rtl/cpu_datapath/regfile.sv" \
  "$project_dir/rtl/cpu_datapath/if_id_reg.sv" \
  "$project_dir/rtl/cpu_datapath/id_ex_reg.sv" \
  "$project_dir/rtl/cpu_datapath/ex_mem_reg.sv" \
  "$project_dir/rtl/cpu_datapath/mem_wb_reg.sv" \
  "$project_dir/tb/unit/tb_base_modules.sv"
"$build_dir/Vtb_base_modules"
