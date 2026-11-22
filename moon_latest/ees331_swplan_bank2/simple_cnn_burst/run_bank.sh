#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")"
export VERILATOR_ROOT=${VERILATOR_ROOT:-/mnt/d/code/FPGA1/tools/verilator-wsl}
project=${PROJECT_DIR:-$(cd .. && pwd)}
mode="${1:-1}"
out="build_bank_$mode"
mkdir -p "$out"
src="$project/source"
"$VERILATOR_ROOT/bin/verilator" --cc --exe --build --assert --no-timing --threads 1 -j 2 -O1 -Wno-fatal --top-module burst_bank_test "-GBURST_READ=$mode" --Mdir "$out" --output-split-cfuncs 500 -CFLAGS "-std=c++20 -O2 -I$project/arm_schedule" -MAKEFLAGS 'CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2' -f cnn.f "$src/storage_v2/rtl/tile_local_ram.sv" "$src/storage_v2/rtl/tile_local_ram_bank2.sv" "$src/storage_v2/rtl/data_mover.sv" "$src/rtl/cnn_ddr/cnn_paged_mover.sv" burst_bank_test.sv bank_bench.cpp >"$out/compile.log" 2>&1
"$out/Vburst_bank_test" >"$out/result.csv" 2>"$out/status.log"
cat "$out/status.log" "$out/result.csv"

