"""Prepare the isolated 23-client EES331 system test fixtures and wrapper.

No production RTL or original test program is edited. The delivered tile
fixture's 512-bit dependency mask is reduced only after its high half is zero.
"""
from pathlib import Path
import shutil
import runpy

ROOT = Path(__file__).resolve().parents[1]
runpy.run_path(str(ROOT/'scripts/make_ram_probe_firmware.py'))
PORTS = (ROOT/'rtl/soc/ees331/face_soc_ees331_top.sv').read_text(encoding='utf-8').split('`ifdef EES331_EXTERNAL_PS',1)[1].split('`else',1)[0].strip()
TB = ROOT/'tb/ees331_soc_pool23_sim_top.sv'
TB.write_text('''// Test-only observation wrapper. The production EES331 top is unchanged.
module ees331_soc_pool23_sim_top (
''' + PORTS + ''',
 output wire [22:0] debug_unit_start,debug_unit_active,debug_completion,debug_work,
 output wire [229:0] debug_node,
 output wire [22:0] debug_valid,debug_write,debug_byte,debug_ready,debug_response,
 output wire [735:0] debug_addr,debug_wdata,debug_rdata,
 output wire [10:0] debug_completed,
 output wire debug_error,debug_fault,
 output wire debug_cpu_re,debug_cpu_we,
 output wire [31:0] debug_cpu_addr
);
 face_soc_ees331_top #(.POOL23(1),
  .IMEM_INIT_FILE("firmware/ees331_cpu/program_ram_probe.mem")) dut(.*);
 assign debug_unit_start=dut.u_cnn.unit_start;
 assign debug_unit_active=dut.u_cnn.unit_active;
 assign debug_completion=dut.u_cnn.completion_pulse;
 assign debug_work=dut.u_cnn.operator_work;
 assign debug_node=dut.u_cnn.unit_node;
 assign debug_completed=dut.u_cnn.completed_count;
 assign debug_error=dut.u_cnn.error;
 assign debug_fault=dut.cnn_mem_fault;
 assign debug_cpu_re=dut.dmem_re;
 assign debug_cpu_we=dut.dmem_we;
 assign debug_cpu_addr=dut.dmem_addr;
 assign debug_valid=dut.cnn_valid;assign debug_write=dut.cnn_write;
 assign debug_byte=dut.cnn_byte;assign debug_ready=dut.cnn_ready;
 assign debug_response=dut.cnn_response;assign debug_addr=dut.cnn_addr;
 assign debug_wdata=dut.cnn_wdata;assign debug_rdata=dut.cnn_rdata;
endmodule
''')

DEST=ROOT/'tb/integration/ees331_soc_pool23_main.cpp'
if not DEST.exists() or 'cpu_ram_reads' not in DEST.read_text(encoding='utf-8'):
    raise RuntimeError(f'Missing checked 23-client C++ system harness: {DEST}')

for name in ('short_row_2x2x2','tile_8x8x32'):
    original=ROOT/'incoming/cases'/name/'native_fixture'
    fixture=ROOT/'build/fixtures'/name
    shutil.copytree(original,fixture,dirs_exist_ok=True)
    words=[int(w,16) for w in (fixture/'template_meta.hex').read_text().split()]
    if len(words)!=3*26:raise RuntimeError(f'Unexpected fixture meta size: {name}')
    compact=[]
    for i in range(3):
        row=words[i*26:(i+1)*26]
        if any(row[13:21]):raise RuntimeError(f'Nonzero high dependency bits: {name}')
        compact.extend(row[:13]+row[21:])
    (fixture/'template_meta.hex').write_text(''.join(f'{v:08x}\n' for v in compact))
    print(name,'prepared',fixture)
runpy.run_path(str(ROOT/'scripts/make_four_frame_tile.py'))
runpy.run_path(str(ROOT/'scripts/convert_four_frame_all_ops.py'))
print('prepared',TB,DEST)
