#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
zip_file="$project_dir/../incoming/fpga-cnn-main.zip"
python3 - "$project_dir" "$zip_file" <<'PY'
import re, sys, zipfile
root, zip_path = sys.argv[1:]
dp = open(root+"/rtl/cpu_datapath/cpu_datapath.sv",encoding="utf-8").read()
dec = open(root+"/rtl/cpu_datapath/address_decoder.sv",encoding="utf-8").read()
with zipfile.ZipFile(zip_path) as z:
    names=[n for n in z.namelist() if n.endswith("mobilefacenet/rtl/mobilefacenet_accelerator_top.sv")]
    if len(names)!=1: raise SystemExit(f"expected one Z top, found {len(names)}")
    cnn=z.read(names[0]).decode("utf-8")

ports={"mmio_addr":("output",32),"mmio_wdata":("output",32),
       "mmio_we":("output",1),"mmio_re":("output",1),
       "mmio_rdata":("input",32),"mmio_ready":("input",1)}
def find(text,name):
    for line in text.splitlines():
        if re.search(rf"\b{name}\b",line):
            prefix=line[:re.search(rf"\b{name}\b",line).start()]
            matches=list(re.finditer(r"\b(input|output)\s+(?:logic|wire)\s*(\[[^]]+\])?",prefix))
            if matches:
                m=matches[-1]
                width=1
                if m.group(2):
                    a,b=map(int,re.findall(r"\d+",m.group(2))); width=abs(a-b)+1
                return m.group(1),width
    raise SystemExit(f"missing {name}")
for name,expect in ports.items():
    got_dp=find(dp,name)
    if got_dp!=expect: raise SystemExit(f"Datapath {name} mismatch: {got_dp} != {expect}")
    cnn_expect=("input" if expect[0]=="output" else "output",expect[1])
    got_cnn=find(cnn,name)
    if got_cnn!=cnn_expect: raise SystemExit(f"CNN {name} mismatch: {got_cnn} != {cnn_expect}")
if "32'h4000_0000" not in dp or "32'h0000_1000" not in dp:
    raise SystemExit("Datapath MMIO default base/window mismatch")
for off in range(0,0x24,4):
    if f"33'h0000_{off:04x}" not in dec: raise SystemExit(f"missing MMIO offset {off:#x}")
header=dp[dp.index("module cpu_datapath"):dp.index(");",dp.index("module cpu_datapath"))]
for forbidden in ("mem_addr","mem_wdata","mem_read","mem_write","mem_rdata","mem_ready"):
    if re.search(rf"(?<!d)(?<!i)\b{forbidden}\b",header):
        raise SystemExit(f"CNN SRAM Master port leaked into Datapath: {forbidden}")
print("PASS: CNN MMIO CPU-side interface match")
PY
