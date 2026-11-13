#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$project_dir/build/datapath"
tmp_dir="$project_dir/build/tmp"
rm -rf "$build_dir"
mkdir -p "$build_dir" "$tmp_dir"
export TMPDIR="$tmp_dir" TMP="$tmp_dir" TEMP="$tmp_dir"
printf '%s\n' '`verilator_config' 'lint_off -rule UNUSEDSIGNAL -file "*imm_gen.sv"' > "$build_dir/existing_imm_gen_waiver.vlt"
verilator --binary --timing --assert -Wall -Wno-UNUSEDPARAM \
  --Mdir "$build_dir" --top-module tb_cpu_datapath \
  "$project_dir/rtl/common/cpu_control_pkg.sv" \
  "$project_dir/rtl/cpu_datapath/pc.sv" \
  "$project_dir/rtl/cpu_datapath/fetch_adapter.sv" \
  "$project_dir/rtl/cpu_datapath/if_id_reg.sv" \
  "$project_dir/rtl/cpu_datapath/regfile.sv" \
  "$project_dir/rtl/cpu_datapath/imm_gen.sv" \
  "$project_dir/rtl/cpu_datapath/id_ex_reg.sv" \
  "$project_dir/rtl/cpu_datapath/alu.sv" \
  "$project_dir/rtl/cpu_datapath/ex_mem_reg.sv" \
  "$project_dir/rtl/cpu_datapath/address_decoder.sv" \
  "$project_dir/rtl/cpu_datapath/lsu.sv" \
  "$project_dir/rtl/cpu_datapath/mem_wb_reg.sv" \
  "$project_dir/rtl/cpu_datapath/cpu_datapath.sv" \
  "$build_dir/existing_imm_gen_waiver.vlt" \
  "$project_dir/tb/models/control_stub.sv" \
  "$project_dir/tb/models/imem_model.sv" \
  "$project_dir/tb/models/dmem_model.sv" \
  "$project_dir/tb/models/cnn_mmio_stub.sv" \
  "$project_dir/tb/integration/tb_cpu_datapath.sv"
"$build_dir/Vtb_cpu_datapath"
