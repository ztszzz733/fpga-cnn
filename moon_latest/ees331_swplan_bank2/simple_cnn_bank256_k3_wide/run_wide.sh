#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export VERILATOR_ROOT=/mnt/d/code/FPGA1/tools/verilator-wsl
project=/mnt/d/code/FPGA1/moon_latest/ees331_swplan_bank2
mode="$1"
case "$mode" in 0|1) ;; *) exit 2;; esac
out="run_wide_$mode"
mkdir -p "$out"
"$VERILATOR_ROOT/bin/verilator" --cc --exe --build --assert --no-timing \
 --threads 1 -j 2 -O1 -Wno-fatal --top-module burst_bank_test "-GK3_WIDE=$mode" \
 --Mdir "$out/model" --output-split-cfuncs 500 -CFLAGS "-std=c++20 -O2 -I$project/arm_schedule" \
 -MAKEFLAGS 'CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2' -f cnn.f \
 rtl/tile_local_ram.sv rtl/tile_read_width.sv rtl/tile_local_ram_bank2.sv \
 rtl/data_mover.sv rtl/cnn_paged_mover.sv burst_bank_test.sv bank_bench.cpp >"$out/compile.log" 2>&1
out="$(realpath "$out")"
cd "$out"
for case in aligned edge limits abort abort-k3 mixed-k3 spill; do
 ./model/Vburst_bank_test "--$case" >"$case.csv" 2>"$case.log"
 cat "$case.log"
done
if [ "$mode" = 1 ]; then
 CNN_WAVE=1 ./model/Vburst_bank_test --large >large.csv 2>large.log
else
 ./model/Vburst_bank_test --large >large.csv 2>large.log
fi
cat large.log

