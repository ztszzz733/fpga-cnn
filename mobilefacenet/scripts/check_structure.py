"""Yosys RTL elaboration/process lowering and structural checks (not place/route)."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import json
from collections import Counter

root = Path(__file__).resolve().parents[1]
tool = shutil.which(os.environ.get("YOSYS", "yosys"))
fallback = Path(r"D:\ke\fpga\oss-cad-suite-windows-x64-20260811\oss-cad-suite\bin\yosys.exe")
if not tool and fallback.is_file():
    tool = str(fallback)
if not tool:
    sys.exit("Yosys not found. Set YOSYS or add it to PATH.")
env = dict(os.environ)
env["PATH"] = os.pathsep.join([str(Path(tool).parent), str(Path(tool).parent.parent / "lib"), env.get("PATH", "")])
build = root / "build"
build.mkdir(exist_ok=True)
script = build / "check_structure.ys"
script.write_text("read_verilog -sv " + " ".join(p.relative_to(root).as_posix() for p in sorted((root / "rtl").glob("*.sv"))) +
                  "\nhierarchy -check -top mobilefacenet_accelerator_top\nproc\nopt\ncheck -assert\nstat\nwrite_json build/array_only_hierarchy.json\n", encoding="ascii")
result = subprocess.run([tool, "-Q", "-T", "-s", str(script)], cwd=root, env=env, text=True, capture_output=True, timeout=180)
(build / "structure.log").write_text(result.stdout+result.stderr, encoding="utf-8")
print("\n".join((result.stdout+result.stderr).splitlines()[-45:]))
if result.returncode==0:
    modules=json.loads((build/'array_only_hierarchy.json').read_text(encoding='utf-8'))['modules']
    counts=Counter()
    def visit(name):
        counts[name]+=1
        for cell in modules[name]['cells'].values():
            if cell['type'] in modules:visit(cell['type'])
    visit('mobilefacenet_accelerator_top')
    forbidden=('conv_engine','depthwise_conv_engine','relu6_unit','add_unit','mobilefacenet_controller','mac_unit')
    if counts['systolic_pe']!=64 or counts['systolic_array8']!=1 or any(counts[name] for name in forbidden):
        raise SystemExit(f'Unexpected compute hierarchy: {counts}')
    queue_type=modules['mobilefacenet_accelerator_top']['cells']['task_queue']['type']
    queue=modules[queue_type]
    if any(name in queue['ports'] for name in ('output_addr','weight_addr','bias_addr','channels','layer_param')):
        raise SystemExit('Queue still has direct layer-configuration inputs')
    head=queue['netnames']['head_data']['bits']
    for name,lo,hi in (('task_op',0,4),('task_input',32,64),('task_output',64,96),
                       ('task_weight',96,128),('task_bias',128,160),('task_size',160,192),
                       ('task_channels',192,224),('task_param',224,256)):
        if queue['ports'][name]['bits']!=head[lo:hi]:
            raise SystemExit(f'{name} has a source other than the descriptor FIFO')
    (build/'array_only_structure.json').write_text(json.dumps(dict(status='passed',module_instances=dict(counts),
        queue_only=True, descriptor_is_only_config_source=True,
        forbidden_absent=list(forbidden)),indent=2),encoding='utf-8')
    print('PASS array-only hierarchy: one systolic_array8, 64 systolic_pe, no scalar/activation/add datapath')
    print('PASS queue-only structure: all layer parameters come directly from the descriptor FIFO')
sys.exit(result.returncode)
