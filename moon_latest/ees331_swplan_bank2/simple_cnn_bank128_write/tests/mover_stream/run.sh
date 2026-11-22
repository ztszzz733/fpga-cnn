#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")"
export VERILATOR_ROOT=${VERILATOR_ROOT:-/mnt/d/code/FPGA1/tools/verilator-wsl}
variant=${1:-stream}
case "$variant" in
 baseline) source_file=reference/data_mover.sv ;;
 stream) source_file=../../rtl/data_mover.sv ;;
 *) echo 'Expected baseline or stream' >&2; exit 2 ;;
esac
out="build_$variant"
mkdir -p "$out"
"$VERILATOR_ROOT/bin/verilator" --cc --exe --build --assert --no-timing \
 --threads 1 -j 2 -O1 -Wno-fatal --top-module data_mover -GTIMEOUT_CYCLES=32 \
 --Mdir "$out" --output-split-cfuncs 500 -CFLAGS "-std=c++20 -O2 -I$PWD" \
 -MAKEFLAGS 'CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2' \
 "$source_file" dma_stream.cpp >"$out/compile.log" 2>&1
"$out/Vdata_mover" >"$out/result.json"
cat "$out/result.json"

