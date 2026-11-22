#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")"
export VERILATOR_ROOT=${VERILATOR_ROOT:-/mnt/d/code/FPGA1/tools/verilator-wsl}
project=${PROJECT_DIR:-/mnt/d/code/FPGA1/moon_latest/ees331_swplan_bank2}
mode="${1:-1}"
total_kib=192
if [ "$#" -ge 2 ]; then total_kib="$2"; fi
case "$total_kib" in
 192|392) ;;
 *) echo "Expected total bank capacity of 192 or 392 KiB" >&2; exit 2 ;;
esac
out="build_write_$mode"_"$total_kib"k
mkdir -p "$out"
"$VERILATOR_ROOT/bin/verilator" --cc --exe --build --assert --no-timing \
 --threads 1 -j 2 -O1 -Wno-fatal --top-module burst_bank_test "-GWRITE128=$mode" "-GLOCAL_BYTES=$((total_kib*1024))" \
 --Mdir "$out" --output-split-cfuncs 500 -CFLAGS "-std=c++20 -O2 -I$project/arm_schedule" \
 -MAKEFLAGS 'CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2' -f cnn.f \
 rtl/tile_local_ram.sv rtl/tile_read_width.sv rtl/tile_local_ram_bank2.sv \
 rtl/data_mover.sv rtl/cnn_paged_mover.sv burst_bank_test.sv bank_bench.cpp >"$out/compile.log" 2>&1
bench="$out/Vburst_bank_test"
"$bench" --aligned >"$out/aligned.csv" 2>"$out/aligned.log"
"$bench" >"$out/original.csv" 2>"$out/original.log"
"$bench" --edge >"$out/edge.csv" 2>"$out/edge.log"
"$bench" --limits >"$out/limits.csv" 2>"$out/limits.log"
cat "$out/aligned.log" "$out/aligned.csv" "$out/original.log" "$out/edge.log" "$out/limits.log"

if [ "$mode" = 1 ]; then
 "$bench" --aligned --abort >"$out/abort.csv" 2>"$out/abort.log"
 cat "$out/abort.log"
fi