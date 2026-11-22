#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")"
export VERILATOR_ROOT=${VERILATOR_ROOT:-/mnt/d/code/FPGA1/tools/verilator-wsl}
mode="${1:-1}"
out="build_burst_$mode"
mkdir -p "$out/ranges" "$out/comparison"
"$VERILATOR_ROOT/bin/verilator" --cc --exe --build --assert --no-timing --threads 1 -j 2 -O1 -Wno-fatal --top-module cnn_simple_top "-GBURST_READ=$mode" --Mdir "$out" --output-split-cfuncs 500 -CFLAGS '-std=c++20 -O2' -MAKEFLAGS 'CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2' -f cnn.f test.cpp >"$out/compile.log" 2>&1
(cd "$out" && ./Vcnn_simple_top >regression.log 2>&1)
(cd "$out/ranges" && ../Vcnn_simple_top --k1-ranges >result.log 2>&1)
(cd "$out/comparison" && ../Vcnn_simple_top --compare >cases.csv 2>stderr.log)
cat "$out/regression.log" "$out/ranges/result.log" "$out/comparison/cases.csv"


if [ "$mode" = 1 ]; then
 (cd "$out/ranges" && ../Vcnn_simple_top --abort-full >abort.log 2>&1)
 cat "$out/ranges/abort.log"
fi
