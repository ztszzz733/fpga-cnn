#!/usr/bin/env bash
set -eu
export VERILATOR_ROOT=${VERILATOR_ROOT:-/mnt/d/code/FPGA1/tools/verilator-wsl}
cd "$(dirname "$0")"
"$VERILATOR_ROOT/bin/verilator" --cc --exe --build --assert --no-timing --threads 1 -j 1 -O1 -Wno-fatal --top-module cnn_simple_top --Mdir build_final --output-split-cfuncs 500 -CFLAGS '-std=c++20 -O2' -MAKEFLAGS 'CFG_CXXFLAGS_PCH_I=-include PYTHON3=python3 OPT_FAST=-O2' rtl/compact_word_ram.sv rtl/simple_k3_engine.sv rtl/simple_k1_engine.sv rtl/simple_mem_bridge.sv rtl/cnn_simple_top.sv test.cpp >compile.log 2>&1
./build_final/Vcnn_simple_top >simulation.log 2>&1
cat simulation.log
mkdir -p build_final/k1_ranges
(cd build_final/k1_ranges && ../Vcnn_simple_top --k1-ranges) >bounds_test.log 2>&1
cat bounds_test.log
