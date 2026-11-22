#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export VERILATOR_ROOT=/mnt/d/code/FPGA1/tools/verilator-wsl
project=/mnt/d/code/FPGA1/moon_latest/ees331_swplan_bank2
out=run_fifo_adaptive
mkdir -p "$out"
"$VERILATOR_ROOT/bin/verilator" --cc --exe --build --assert --no-timing \
 --threads 1 -j 2 -O1 -Wno-fatal --top-module burst_bank_test \
 --Mdir "$out/model" --output-split-cfuncs 500 -CFLAGS "-std=c++20 -O2 -I$project/arm_schedule" \
 -MAKEFLAGS 'CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2' -f cnn.f \
 rtl/tile_local_ram.sv rtl/tile_read_width.sv rtl/tile_local_ram_bank2.sv \
 rtl/data_mover.sv rtl/cnn_paged_mover.sv burst_bank_test.sv bank_bench.cpp >"$out/compile.log" 2>&1
bench="$out/model/Vburst_bank_test"
for case in aligned edge limits abort abort-k3 large spill; do
 "$bench" "--$case" >"$out/$case.csv" 2>"$out/$case.log"
 cat "$out/$case.log"
done

