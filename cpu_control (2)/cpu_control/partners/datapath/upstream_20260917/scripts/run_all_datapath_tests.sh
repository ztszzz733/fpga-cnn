#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$project_dir/build/acceptance"
tmp_dir="$project_dir/build/tmp"
mkdir -p "$build_dir" "$tmp_dir"
export TMPDIR="$tmp_dir" TMP="$tmp_dir" TEMP="$tmp_dir"
cd "$project_dir"

run_step() {
  local name="$1"
  shift
  echo "START: $name"
  "$@"
  local code=$?
  echo "PASS STEP: $name (exit $code)"
}

run_step run_pkg_tests.sh "$project_dir/scripts/run_pkg_tests.sh"
run_step run_base_tests.sh "$project_dir/scripts/run_base_tests.sh"
run_step run_lsu_tests.sh "$project_dir/scripts/run_lsu_tests.sh"
run_step run_fetch_tests.sh "$project_dir/scripts/run_fetch_tests.sh"
run_step run_dmem_timing_tests.sh "$project_dir/scripts/run_dmem_timing_tests.sh"
run_step run_datapath_tests.sh "$project_dir/scripts/run_datapath_tests.sh"
run_step check_control_pkg_compat.sh "$project_dir/scripts/check_control_pkg_compat.sh"
run_step check_c1_interface.sh "$project_dir/scripts/check_c1_interface.sh"
run_step check_cnn_mmio_interface.sh "$project_dir/scripts/check_cnn_mmio_interface.sh"

printf '%s\n' '`verilator_config' \
  'lint_off -rule UNUSEDSIGNAL -file "*imm_gen.sv"' > "$build_dir/existing_imm_gen_waiver.vlt"
run_step cpu_datapath_filelist_lint verilator --lint-only -Wall -Wno-UNUSEDPARAM \
  --Mdir "$build_dir/lint" --top-module cpu_datapath \
  "$build_dir/existing_imm_gen_waiver.vlt" -f "$project_dir/rtl/filelists/cpu_datapath.f"
echo "PASS: all CPU datapath acceptance checks"
