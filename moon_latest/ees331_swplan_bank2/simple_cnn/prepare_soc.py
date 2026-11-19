from pathlib import Path
import json
BASE=Path(__file__).resolve().parent
MOON=Path('D:/code/FPGA1/moon_latest/ees331_swplan_bank2')
source=MOON/'source'
text=(source/'rtl/soc/ees331/face_soc_ees331_mover_top.sv').read_text(encoding='utf-8')
text=text.replace('// Reduced 12-client DATA MOVER variant of the EES331 six-peer/PS7 top.',
                  '// Four-client DATA MOVER variant with a manually commanded simple CNN.')
text=text.replace('module face_soc_ees331_mover_top #(','module face_soc_ees331_simple_top #(',1)
for line in [' parameter integer K3_UNITS=2,K1_UNITS=6,POST_UNITS=2,\n',' parameter bit ENABLE_DW7=0,\n',' parameter integer CNN_FRAMES=4,\n']:
 assert line in text
 text=text.replace(line,'',1)
start=text.index(' localparam integer CNN_K3=')
end=text.index('\n',text.index(' localparam integer CNN_CLIENTS=',start))
text=text[:start]+' localparam integer CNN_CLIENTS=4;'+text[end:]
start=text.index(' cnn_ees331 #(')
end=text.index(' datasram_mover_subsystem #(',start)
text=text[:start]+''' // Manual four-unit CNN. Existing ROM/PLAN scheduling protocol must be
 // replaced by the software MMIO API in simple_cnn/software/cnn_simple.h.
 cnn_simple_top u_cnn(
  .clk,.rst_n,.memory_fault(cnn_mem_fault),
  .mmio_addr(cnn_mmio_addr),.mmio_wdata(cnn_mmio_wdata),
  .mmio_re(cnn_mmio_re),.mmio_we(cnn_mmio_we),
  .mmio_rdata(cnn_mmio_rdata),.mmio_ready(cnn_mmio_ready),
  .mem_valid(cnn_valid),.mem_write(cnn_write),.mem_byte(cnn_byte),
  .mem_addr(cnn_addr),.mem_wdata(cnn_wdata),.mem_ready(cnn_ready),
  .mem_response(cnn_response),.mem_rdata(cnn_rdata),
  .unit_busy(),.unit_done(),.unit_error(),.unit_work(),.busy(),.done(),.error(),
  .operator_phase(),.memory_phase(),.mac_counts());
 // Manual abort drains each captured transaction rather than invalidating
 // the shared memory controller while other units still have requests.
 assign cnn_cancel=1'b0;
'''+text[end:]
text='// Integration wiring only: no claim of old ROM/PLAN compatibility.\n'+text
(BASE/'rtl/face_soc_ees331_simple_top.sv').write_text(text,encoding='utf-8')
paths=[]
for line in (source/'rtl/filelists/system_ees331_reduced.f').read_text().splitlines():
 line=line.strip()
 if not line or line.startswith('#'):continue
 if line.startswith(('rtl/cnn_self/','rtl/cnn_quant/')):continue
 if line in ['rtl/cnn_ddr/quant_post_bram_engine.sv','rtl/cnn_ddr/fixed_schedule_compact.sv','rtl/cnn_ddr/cnn_ees331.sv','rtl/soc/ees331/face_soc_ees331_mover_top.sv']:continue
 paths.append('../source/'+line)
local=['compact_word_ram.sv','simple_k3_engine.sv','simple_k1_engine.sv','simple_mem_bridge.sv','cnn_simple_top.sv','face_soc_ees331_simple_top.sv']
paths+=['rtl/'+name for name in local]
(BASE/'soc.f').write_text('\n'.join(paths)+'\n')
(BASE/'cnn.f').write_text('\n'.join('rtl/'+n for n in local[:-1])+'\n')
def linux(p):
 s=p.as_posix();return '/mnt/'+s[0].lower()+s[2:]
absolute=[source/p.removeprefix('../source/') if p.startswith('../source/') else BASE/p for p in paths]
cmd=['#!/usr/bin/env bash','set -eu','export VERILATOR_ROOT=/mnt/d/code/FPGA1/tools/verilator-wsl',
     'cd '+linux(BASE), '"$VERILATOR_ROOT/bin/verilator" --lint-only --assert --no-timing -Wno-fatal --top-module face_soc_ees331_simple_top -DEES331_EXTERNAL_PS '+
     "'-GIMEM_INIT_FILE=\""+linux(source/'firmware/ees331_cpu/program.mem')+"\"' "+' '.join(linux(p) for p in absolute)+' >soc_lint.log 2>&1']
(BASE/'lint_soc.sh').write_text('\n'.join(cmd)+'\n',newline='\n')
print('Generated four-client SoC wiring/filelists; original ROM and PLAN are not compatible with new MMIO.')
