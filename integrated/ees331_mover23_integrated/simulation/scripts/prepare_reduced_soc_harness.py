"""Make the observation harness match the actual 12-client production top."""
from pathlib import Path
SIM=Path(__file__).resolve().parents[1]
sv=(SIM/'tb/ees331_soc_mover23_sim_top.sv').read_text()
sv=sv.replace('23-client DATA MOVER top','12-client reduced DATA MOVER top').replace('ees331_soc_mover23_sim_top','ees331_soc_reduced_sim_top')
sv=sv.replace('[22:0]','[11:0]').replace('[252:0]','[119:0]').replace('[735:0]','[383:0]')
sv=sv.replace('output wire [11:0] debug_completed','output wire [10:0] debug_completed').replace('.CNN_FRAMES(5)','.CNN_FRAMES(4)')
sv=sv[:sv.index(' assign debug_operator_state[0]')]
for k in range(12):
 if k<2:path='engines[%d].latest_k3.convolution'%k
 elif k<8:path='engines[%d].latest_k1.convolution'%k
 elif k<11:path='postprocessing[%d].latest_post.post'%k
 else:path='padding'
 sv+=' assign debug_operator_state[%d]=dut.u_cnn.core.%s.state;\n'%(k,path)
sv+='endmodule\n'
(SIM/'tb/ees331_soc_reduced_sim_top.sv').write_text(sv)
c=(SIM/'tb/integration/ees331_soc_five_main.cpp').read_text()
c=c.replace('Vees331_soc_mover23_sim_top','Vees331_soc_reduced_sim_top').replace('23-CNN','12-CNN').replace('soc_five.fst','soc_reduced.fst')
c=c.replace('#include <chrono>','#include <chrono>\n#include <csignal>\nstatic volatile std::sig_atomic_t stopping=0;\nstatic void stop(int){stopping=1;}')
c=c.replace('std::array<U64,23>','std::array<U64,12>').replace('k<23','k<12').replace('if(k<17)','if(k<8)')
c=c.replace('unsigned bit=k*11','unsigned bit=k*10').replace('if(w<7)','if(w+1<4)').replace(')&2047;',')&1023;')
c=c.replace('info[0]<=5','info[0]<=4')
begin=c.index('  if(k1_bank){',c.index(' void run()'))
end=c.index('  U32 model_end=',begin);c=c[:begin]+c[end:]
begin=c.index('  if(k1_bank){',c.index('all jobs/output coverage'))
end=c.index('  need(cpu_ram_reads',begin);c=c[:begin]+c[end:]
c=c.replace('need(!d.debug_error&&!d.debug_fault,"CNN/MOVER error at cycle "+std::to_string(cycle));','''if(d.debug_error||d.debug_fault)need(false,"CNN/MOVER error at cycle "+std::to_string(cycle));
  if(!(d.debug_unit_start|d.debug_completion|d.debug_work|(d.debug_valid&d.debug_ready&d.debug_write)))return;''')
c=c.replace('  need(cycle<50000000000ULL,','  need(!stopping,"stopped by user");\n  need(cycle<50000000000ULL,')
c=c.replace(' explicit Bench(', ' ~Bench(){if(trace)trace->close();}\n explicit Bench(')
c=c.replace('int main(int argc,char**argv){try{','int main(int argc,char**argv){std::signal(SIGINT,stop);std::signal(SIGTERM,stop);try{')
c=c.replace('need(k1_bank<3,"K1 bank must be 0, 1, or 2");','need(k1_bank==0,"reduced pool has no K1 bank override");')
c=c.replace('"integer output mismatch node "+std::to_string(n)','"integer output mismatch node "+std::to_string(n)+" offset "+std::to_string(a-base+j)')
(SIM/'tb/integration/ees331_soc_reduced_main.cpp').write_text(c)
print('prepared 12-unit wrapper and full SoC numerical monitor')
