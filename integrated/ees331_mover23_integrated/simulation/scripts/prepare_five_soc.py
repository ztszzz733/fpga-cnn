"""Extend the delivered compact SoC to five contexts, retaining four as default.

Run once on a fresh copy of the 20261111 integrated archive. Arithmetic engines,
tile RAM, paging policy, DATA MOVER and CPU datapath/control are unchanged.
"""
from pathlib import Path
import hashlib
import json
import shutil
import sys

SIM = Path(__file__).resolve().parents[1]
BASE = SIM.parent
OLD = Path('D:/code/FPGA1/cpu_control (2)/cpu_control/build')


def edit(relative, replacements):
    path = BASE / relative
    text = path.read_text(encoding='utf-8')
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    for old, new in replacements:
        if old not in text:
            raise RuntimeError('missing edit anchor in ' + relative + ': ' + old)
        text = text.replace(old, new)
    path.write_text(text, encoding='utf-8')
    return {'before': before, 'after': hashlib.sha256(path.read_bytes()).hexdigest()}


changes = {}
changes['fixed_schedule_compact'] = edit('rtl/cnn_ddr/fixed_schedule_compact.sv', [
    ('parameter integer STEPS=256,LW=$clog2(STEPS),IW=LW+2,',
     'parameter integer FRAME_CONTEXTS=4,FW=$clog2(FRAME_CONTEXTS),SLOTS=4*FRAME_CONTEXTS,SW=FW+2,\n parameter integer STEPS=256,LW=$clog2(STEPS),IW=LW+FW,'),
    ('input logic [1:0] address_slot', 'input logic [FW-1:0] address_slot'),
    ('input logic [1:0] frame_slot', 'input logic [FW-1:0] frame_slot'),
    ('output logic [3:0] frames_ready', 'output logic [FRAME_CONTEXTS-1:0] frames_ready'),
    ('output logic [15:0] external_hold', 'output logic [SLOTS-1:0] external_hold'),
    ('[16*IW-1:0] buffer_owners', '[SLOTS*IW-1:0] buffer_owners'),
    ('[4*STEPS-1:0] completed_mask', '[FRAME_CONTEXTS*STEPS-1:0] completed_mask'),
    ('inputs[4],workspaces[4],tags[4]', 'inputs[FRAME_CONTEXTS],workspaces[FRAME_CONTEXTS],tags[FRAME_CONTEXTS]'),
    ('pc[4]', 'pc[FRAME_CONTEXTS]'),
    ('logic [3:0] addresses_loaded,frame_active', 'logic [FRAME_CONTEXTS-1:0] addresses_loaded,frame_active'),
    ('logic [1:0] scan,selected_frame', 'logic [FW-1:0] scan,selected_frame'),
    ('[16]', '[SLOTS]'),
    ('logic [UNITS-1:0][1:0] unit_frame', 'logic [UNITS-1:0][FW-1:0] unit_frame'),
    ('logic [3:0] result_slot,result_turn', 'logic [SW-1:0] result_slot,result_turn'),
    ('wire [3:0] allocation', 'wire [SW-1:0] allocation'),
    ('s<16', 's<SLOTS'), ('q<16', 'q<SLOTS'), ('%16', '%SLOTS'),
    ('n<4*STEPS', 'n<FRAME_CONTEXTS*STEPS'),
    ('input [1:0] mode,input [1:0] f', 'input [1:0] mode,input [FW-1:0] f'),
    ("{30'b0,selected_frame}", "32'(selected_frame)"),
    ('f<4', 'f<FRAME_CONTEXTS'), ('image_count>4', 'image_count>FRAME_CONTEXTS'),
    ("5'b1", "(FRAME_CONTEXTS+1)'(1)"),
    ("result_slot<=4'(pick)", "result_slot<=SW'(pick)"),
    ('scan<=scan+1;', "scan<=scan==FW'(FRAME_CONTEXTS-1)?'0:scan+1;"),
])
changes['cnn_ees331'] = edit('rtl/cnn_ddr/cnn_ees331.sv', [
    ('parameter integer STEPS=256,LW=$clog2(STEPS),IW=LW+2,',
     'parameter integer FRAME_CONTEXTS=4,FW=$clog2(FRAME_CONTEXTS),\n parameter integer STEPS=256,LW=$clog2(STEPS),IW=LW+FW,'),
    ('logic [1:0] address_slot', 'logic [FW-1:0] address_slot'),
    ('wire [3:0] frames_ready', 'wire [FRAME_CONTEXTS-1:0] frames_ready'),
    ("{30'b0,address_slot}", "32'(address_slot)"),
    ("{28'b0,frames_ready}", "32'(frames_ready)"),
    ('cnn_mmio_wdata<=4', 'cnn_mmio_wdata<=FRAME_CONTEXTS'),
    ('cnn_mmio_wdata<4)address_slot<=cnn_mmio_wdata[1:0]', 'cnn_mmio_wdata<FRAME_CONTEXTS)address_slot<=cnn_mmio_wdata[FW-1:0]'),
    ('fixed_schedule_compact #(.STEPS(STEPS)', 'fixed_schedule_compact #(.FRAME_CONTEXTS(FRAME_CONTEXTS),.STEPS(STEPS)'),
])
changes['soc_top'] = edit('rtl/soc/ees331/face_soc_ees331_mover_top.sv', [
    ('parameter integer LOCAL_BYTES=32768,', 'parameter integer LOCAL_BYTES=32768,\n parameter integer CNN_FRAMES=4,'),
    ('cnn_ees331 #(.K3_UNITS(CNN_K3)', 'cnn_ees331 #(.FRAME_CONTEXTS(CNN_FRAMES),.K3_UNITS(CNN_K3)'),
])
changes['firmware_generator'] = edit('simulation/scripts/gen_ees331_cpu.py', [
    ('def generate():', 'def generate(max_frames=4):'),
    ("li(5,4);p.branch(7,6,5,'bad_command')", "li(5,max_frames);p.branch(7,6,5,'bad_command')"),
])
sys.path.insert(0, str(SIM/'scripts'))
from gen_ees331_cpu import generate
generate(max_frames=5)
import runpy
runpy.run_path(str(SIM/'scripts/make_ram_probe_firmware.py'))

for size in ('small', 'full'):
    source = OLD / ('self_five_'+size)
    manifest = json.loads((source/'manifest.json').read_text())
    for name, digest in manifest['files_sha256'].items():
        assert hashlib.sha256((source/name).read_bytes()).hexdigest() == digest, name
    assert manifest['frames'] == 5 and manifest['total_tasks'] == 5*manifest['template_steps']
    destination = SIM / ('build/fixtures/five_'+size)
    shutil.copytree(source, destination, dirs_exist_ok=True)
    # The old fixture already has 18-word compact metadata and 20 slot ranges.
    meta = [int(v,16) for v in (destination/'template_meta.hex').read_text().split()]
    assert len(meta) == manifest['template_steps']*18
    assert max(sum(1 for t in range(256) if t != s and (meta[s*18+5+t//32] >> (t%32)) & 1)
               for s in range(manifest['template_steps'])) <= 2
    print(size, manifest['total_tasks'], manifest['expected_bytes'], destination)

wrapper = SIM/'tb/ees331_soc_mover23_sim_top.sv'
text = wrapper.read_text().replace('[229:0] debug_node','[252:0] debug_node').replace('[10:0] debug_completed','[11:0] debug_completed')
text = text.replace('face_soc_ees331_mover_top #(.POOL23(1),', 'face_soc_ees331_mover_top #(.POOL23(1),.CNN_FRAMES(5),')
text = text.replace('output wire [31:0] debug_page_misses,debug_mover_read_bytes,debug_mover_write_bytes',
 '''output wire [31:0] debug_page_misses,debug_mover_read_bytes,debug_mover_write_bytes,
 output wire [2:0] debug_memory_state,
 output wire [3:0] debug_mover_state,
 output wire [22:0][3:0] debug_operator_state,
 output wire [22:0] debug_operator_busy,
 output wire debug_cnn_running,debug_cnn_finished,debug_mmio_we,
 output wire [31:0] debug_mmio_addr,debug_mmio_data''')
extra = '''
 assign debug_memory_state=dut.u_datasram.cache.state;
 assign debug_mover_state=dut.u_datasram.cache.mover.state;
 assign debug_operator_busy=dut.u_cnn.operator_busy;
 assign debug_cnn_running=dut.u_cnn.core.running;
 assign debug_cnn_finished=dut.u_cnn.core.finished;
 assign debug_mmio_we=dut.cnn_mmio_we;
 assign debug_mmio_addr=dut.cnn_mmio_addr;
 assign debug_mmio_data=dut.cnn_mmio_wdata;
'''
for k in range(23):
    if k < 4: path='engines[%d].latest_k3.convolution'%k
    elif k < 16: path='engines[%d].latest_k1.convolution'%k
    elif k == 16: path='dw7'
    elif k < 22: path='postprocessing[%d].latest_post.post'%k
    else: path='padding'
    extra += ' assign debug_operator_state[%d]=dut.u_cnn.core.%s.state;\n'%(k,path)
text = text.replace('endmodule', extra+'endmodule')
wrapper.write_text(text)
(SIM/'build/five_soc_adaptation.json').write_text(json.dumps(changes,indent=2)+'\n')
print('Five-context adaptation ready; default production parameter remains four.')
