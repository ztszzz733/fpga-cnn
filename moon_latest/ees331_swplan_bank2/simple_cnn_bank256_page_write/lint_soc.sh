#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")"
export VERILATOR_ROOT=${VERILATOR_ROOT:-/mnt/d/code/FPGA1/tools/verilator-wsl}
manifest=soc.f
if [ ! -d ../source ]; then
 project=${PROJECT_DIR:-/mnt/d/code/FPGA1/moon_latest/ees331_swplan_bank2}
 manifest=$(mktemp)
 trap 'rm -f "$manifest"' EXIT
 sed "s#^../source/#$project/source/#" soc.f > "$manifest"
fi
"$VERILATOR_ROOT/bin/verilator" --lint-only --assert --no-timing -Wno-fatal \
 --top-module face_soc_ees331_simple_top -DEES331_EXTERNAL_PS -f "$manifest"

