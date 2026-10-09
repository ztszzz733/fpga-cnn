#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
control_file="$project_dir/../incoming/cpu_control/rtl/cpu_control/cpu_control.sv"
datapath_file="$project_dir/rtl/cpu_datapath/cpu_datapath.sv"
python3 - "$datapath_file" "$control_file" <<'PY'
import re, sys
dp_path, ctl_path = sys.argv[1:]
dp = open(dp_path, encoding="utf-8").read()
ctl = open(ctl_path, encoding="utf-8").read()

schema = {
"clk":("input",1), "rst_n":("input",1),
"instr_d":("output",32), "rs1_d":("output",5), "rs2_d":("output",5),
"rd_e":("output",5), "rd_m":("output",5), "rd_w":("output",5),
"regwrite_m":("output",1), "regwrite_w":("output",1), "memread_e":("output",1),
"cmp_eq_e":("output",1), "cmp_lt_e":("output",1), "cmp_ltu_e":("output",1),
"mul_busy":("output",1), "valid_d":("output",1), "valid_e":("output",1),
"valid_m":("output",1), "valid_w":("output",1), "rs1_e":("output",5),
"rs2_e":("output",5), "uses_rs1_e":("output",1), "uses_rs2_e":("output",1),
"branch_type_e":("output",3), "jump_e":("output",2), "memread_m":("output",1),
"pc_sel":("input",2), "pc_en":("input",1), "if_id_en":("input",1),
"if_id_flush":("input",1), "id_ex_flush":("input",1), "alu_ctrl":("input",4),
"alu_src_a_sel":("input",2), "alu_src_b_sel":("input",2), "fwd_a":("input",2),
"fwd_b":("input",2), "fwd_store":("input",2), "regwrite_d":("input",1),
"memread_d":("input",1), "memwrite_d":("input",1), "load_type_d":("input",3),
"store_type_d":("input",2), "wb_sel_d":("input",2), "branch_type_d":("input",3),
"jump_d":("input",2), "imm_type_d":("input",3), "uses_rs1_d":("input",1),
"uses_rs2_d":("input",1)}

def declaration(text, name):
    for line in text.splitlines():
        line = re.sub(r"//.*", "", line)
        if not re.search(rf"\b{re.escape(name)}\b", line): continue
        m = re.search(r"\b(input|output)\s+(?:logic|wire)\s*(\[[^]]+\])?", line)
        if m:
            width = 1
            if m.group(2):
                nums = [int(x) for x in re.findall(r"\d+", m.group(2))]
                width = abs(nums[0]-nums[1])+1
            return m.group(1), width
    raise SystemExit(f"missing port {name}")

for name,(dp_dir,width) in schema.items():
    got_dp = declaration(dp,name)
    if got_dp != (dp_dir,width): raise SystemExit(f"Datapath {name}: {got_dp}, expected {(dp_dir,width)}")
    ctl_dir = dp_dir if name in ("clk","rst_n") else ("input" if dp_dir=="output" else "output")
    got_ctl = declaration(ctl,name)
    if got_ctl != (ctl_dir,width): raise SystemExit(f"Control {name}: {got_ctl}, expected {(ctl_dir,width)}")
if len(schema) != 48: raise SystemExit("internal schema is not 48 ports")
print("PASS: C1 Control-Datapath interface match")
PY
