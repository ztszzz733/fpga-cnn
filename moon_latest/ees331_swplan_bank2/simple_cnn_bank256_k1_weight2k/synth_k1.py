import hashlib
import json
import subprocess
import time
from pathlib import Path

root=Path(__file__).resolve().parent
vivado=Path("D:/vivado/2025.2/Vivado/bin/vivado.bat")
sources=[root/"rtl"/name for name in
         ("compact_word_ram.sv","k1_bulk_pixels.sv","k1_write_buffer.sv","simple_k1_engine.sv")]
assert vivado.is_file()

def tcl(path):
    return "{"+path.as_posix()+"}"

for size in (1024,2048):
    out=root/f"synth_{size}"
    out.mkdir(exist_ok=True)
    report=out/"utilization.rpt"
    hierarchical=out/"hierarchy.rpt"
    xdc=out/"clock.xdc"
    xdc.write_text("create_clock -name cnn_clk -period 10.000 [get_ports clk]\n")
    flags="BURST_READ=1 READ64=1 BULK=1 PACKED_WRITE=1 WRITE_BITS=256 EXTRA_RESULTS=1 MAX_CHANNELS=512 INPUT_PREFETCH=0 OUTPUT_PAR=1 READ_AHEAD=0"
    script=out/"synth.tcl"
    script.write_text("\n".join([
        "set_param general.maxThreads 2",
        "create_project -in_memory -part xc7z020clg484-1",
        *(f"read_verilog -sv {tcl(f)}" for f in sources),
        f"read_xdc {tcl(xdc)}",
        "synth_design -top simple_k1_engine -mode out_of_context -part xc7z020clg484-1 "
        f"-flatten_hierarchy rebuilt -max_bram_cascade_height 1 -generic {{{flags} WEIGHT_CACHE_BYTES={size}}}",
        f"report_utilization -file {tcl(report)}",
        f"report_utilization -hierarchical -file {tcl(hierarchical)}",
        "puts K1_CACHE_SYNTH_DONE",
        "exit 0",
    ])+"\n")
    start=time.perf_counter()
    log=out/"synth.log"
    with (out/"launcher.log").open("w") as output:
        proc=subprocess.run([str(vivado),"-mode","batch","-source",str(script),"-log",str(log),
                             "-journal",str(out/"synth.jou")],
                             stdout=output,stderr=subprocess.STDOUT,cwd=out,
                             creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
    assert proc.returncode==0 and "K1_CACHE_SYNTH_DONE" in log.read_text(errors="replace"),log
    result={"weight_cache_bytes":size,"part":"xc7z020clg484-1","top":"simple_k1_engine","seconds":round(time.perf_counter()-start,2),
            "source_sha256":{f.relative_to(root).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in sources}}
    (out/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k!="source_sha256"}),flush=True)

