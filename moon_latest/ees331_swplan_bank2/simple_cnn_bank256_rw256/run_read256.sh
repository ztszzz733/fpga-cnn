#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export VERILATOR_ROOT="${VERILATOR_ROOT:-/mnt/d/code/FPGA1/tools/verilator-wsl}"
project="${PROJECT_DIR:-/mnt/d/code/FPGA1/moon_latest/ees331_swplan_bank2}"
wide="$1"
case "$wide" in 0|1) ;; *) exit 2;; esac
out="run_read256_$wide"
args=(+ci_quad)
if [ "$wide" = 1 ]; then args+=(+read256); fi
mkdir -p "$out"
"$VERILATOR_ROOT/bin/verilator" --cc --exe --build --assert --no-timing \
 --threads 1 -j 2 -O1 -Wno-fatal --top-module burst_bank_test "-GREAD256=$wide" \
 --Mdir "$out/model" --output-split-cfuncs 500 -CFLAGS "-std=c++20 -O2 -I$project/arm_schedule" \
 -MAKEFLAGS 'CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2' -f cnn.f \
 rtl/tile_local_ram.sv rtl/tile_read_width.sv rtl/tile_local_ram_bank2.sv \
 rtl/data_mover.sv rtl/cnn_paged_mover.sv burst_bank_test.sv bank_bench.cpp >"$out/compile.log" 2>&1
cd "$out"
cases=(aligned edge limits abort abort-k3 abort-k3-mac abort-k3-read mixed-k3 pair-edges pair-limits quad-boundary wide-edges spill weight-boundary large large-aligned32)
for test in "${cases[@]}"; do
 if [ "$test" = large ]; then
  CNN_WAVE=1 ./model/Vburst_bank_test "${args[@]}" "--$test" >"$test.csv" 2>"$test.log"
 else
  ./model/Vburst_bank_test "${args[@]}" "--$test" >"$test.csv" 2>"$test.log"
 fi
 printf '%s ' "$test"
 awk '/^PASS batch_cycles=/{print}' "$test.log"
done
./model/Vburst_bank_test "${args[@]}" --large 12 >k1_only.csv 2>k1_only.log
printf '%s ' k1_only
awk '/^PASS batch_cycles=/{print}' k1_only.log

