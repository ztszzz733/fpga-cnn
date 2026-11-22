#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")"
export VERILATOR_ROOT=${VERILATOR_ROOT:-/mnt/d/code/FPGA1/tools/verilator-wsl}
"$VERILATOR_ROOT/bin/verilator" --lint-only --assert --no-timing -Wno-fatal \
 --top-module face_soc_ees331_simple_top -DEES331_EXTERNAL_PS -f soc.f

