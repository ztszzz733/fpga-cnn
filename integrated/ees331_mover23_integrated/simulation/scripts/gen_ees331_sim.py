"""Generate test-only wrapper: real compact CNN + real cache, PS DDR at AXI pins."""
from pathlib import Path
import json
import re
ROOT=Path(__file__).resolve().parents[1]
def main():
    core=(ROOT/'rtl/cnn_ddr/fixed_schedule_compact.sv').read_text()
    head=core[core.index('module fixed_schedule_compact'):core.index(' localparam integer DW=')]
    head=head.replace('module fixed_schedule_compact','module ees331_cnn_ddr_sim_top')
    head=head.replace('parameter integer STEPS=256','parameter integer CACHE_BYTES=131072,STEPS=256')
    head=head.replace('input logic [UNITS-1:0] mem_ready,mem_response','output wire [UNITS-1:0] mem_ready,mem_response')
    head=head.replace('input logic [UNITS*32-1:0] mem_rdata,input logic memory_fault','output wire [UNITS*32-1:0] mem_rdata,output wire memory_fault')
    head=re.sub(r' output wire \[4\*STEPS-1:0\] completed_mask,\n','',head)
    links=json.loads((ROOT/'deliverables/ees331_ddr_io/io_manifest.json').read_text(encoding='utf-8'))['after']
    hp=next(e for e in links if e['id']=='H')
    ports=[];names=[]
    for g in ['address','data','control']:
        for s in hp[g]:
            n=s['name'];w=s['width'];names.append(n)
            direction='output wire' if s['direction']=='fwd' else 'input wire'
            ports.append(f" {direction} {'['+str(w-1)+':0] ' if w>1 else ''}{n}")
    extras=[' input logic [31:0] cache_csr_addr,cache_csr_wdata',' input logic cache_csr_re,cache_csr_we',' output wire [31:0] cache_csr_rdata',' output wire cache_csr_ready']+ports
    head=head.rstrip().removesuffix(');').rstrip()+',\n'+',\n'.join(extras)+'\n);\n'
    body=' fixed_schedule_compact #(.STEPS(STEPS),.LW(LW),.IW(IW),.K3_UNITS(K3_UNITS),.K1_UNITS(K1_UNITS),.POST_UNITS(POST_UNITS)) core(.*,.completed_mask());\n'
    body+=' datasram_ddr_subsystem #(.CACHE_BYTES(CACHE_BYTES)) storage(\n  .clk(clk),.rst_n(rst_n),\n'
    body+="  .dmem_addr(32'b0),.dmem_wdata(32'b0),.dmem_wstrb(4'b0),.dmem_re(1'b0),.dmem_we(1'b0),.dmem_rdata(),\n"
    pairs=[('cnn_'+n,'mem_'+n) for n in ['valid','write','byte','addr','wdata','ready','response','rdata']]+[('cnn_cancel','cancel'),('cnn_mem_fault','memory_fault')]
    pairs += [(n,n) for n in ['cache_csr_addr','cache_csr_wdata','cache_csr_re','cache_csr_we','cache_csr_rdata','cache_csr_ready']+names]
    body+=',\n'.join('  .'+a+'('+b+')' for a,b in pairs)+'\n );\nendmodule\n'
    out=ROOT/'tb/ees331_cnn_ddr_sim_top.sv';out.write_text(head+body)
    print(out)
if __name__=='__main__':main()
