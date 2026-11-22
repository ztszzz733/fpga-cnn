#include "Vburst_bank_test.h"
#include "verilated.h"
#include "ees331_axi_mover_model.hpp"
#include "software/cnn_simple.h"
#include <array>
#include <string_view>
#include <algorithm>
#include <iostream>
#include <stdexcept>
#include <vector>
static void need(bool b,const char*s){if(!b)throw std::runtime_error(s);}
struct Job{unsigned w,h,ci,co,s;bool dw,unaligned;unsigned ib,wb,ob,ow,oh;std::vector<uint32_t> expected;};
struct Bench{
 bool aligned=false,restarted=false;
 unsigned expected_abort=0;
 Vburst_bank_test d;
 AxiDdr<Vburst_bank_test> ram{d};
 std::vector<uint8_t>& mem=ram.data;
 unsigned cycle=0,overlap=0, used_banks=0, moved_banks=0;
 unsigned issue_cycles[2]{};
 struct Counts{unsigned reads=0,bytes=0,writes=0,write_bursts=0,write_bytes=0,doubles=0,inputs=0,weights=0,max_input=0,max_weight=0,retire=0,start=0;};
 std::array<Counts,4> counts{};
 Bench(){
  d.rst_n=0;d.mmio_re=0;d.mmio_we=0;d.cache_csr_we=0;d.cache_csr_re=0;
  ram.stress=false;
  for(int i=0;i<5;i++)tick();
  d.rst_n=1;tick();
 }
 void tick(){
  need(++cycle<4000000,"timeout");d.clk=0;ram.drive();d.eval();
  if(d.rst_n){
   need(!d.cnn_mem_fault && !(d.unit_error&~expected_abort),"hardware fault");
   ram.capture();
   used_banks|=d.used_bank;
   moved_banks|=d.dma_banks;
   for(unsigned b=0;b<2;b++)if(d.used_bank>>b&1)++issue_cycles[b];
   if(d.unit_work==15)++overlap;
   for(unsigned u=0;u<4;u++){
    auto &c=counts[u];
    if(!c.retire && (d.unit_done>>u&1))c.retire=cycle;
    if((d.span_accept>>u)&1){
     unsigned bytes=(d.span_bytes>>(13*u))&8191;
     bool wt=(d.span_weight>>u)&1;
     ++(wt?c.weights:c.inputs);
     auto &m=wt?c.max_weight:c.max_input;m=std::max(m,bytes);
    }
    if((d.cnn_valid&d.cnn_ready)>>u&1){
     if(d.cnn_write>>u&1){
      ++c.writes;
      const bool wide=(d.cnn_quad>>u)&1;
      c.write_bytes+=wide?16:4;
      if(wide)++c.write_bursts;
     }else {++c.reads;
      const bool wide=(d.cnn_double>>u)&1;
      c.bytes+=(d.cnn_byte>>u&1)?1:(wide?8:4);
      if(wide)++c.doubles;}
    }
   }
  }
  d.clk=1;d.eval();d.clk=0;d.eval();
 }
 void wr(unsigned a,unsigned v){d.mmio_addr=a;d.mmio_wdata=v;d.mmio_we=1;tick();d.mmio_we=0;}
 void cfg(unsigned a,unsigned v){d.cache_csr_addr=a;d.cache_csr_wdata=v;d.cache_csr_we=1;tick();d.cache_csr_we=0;tick();}
 unsigned csr(unsigned a){d.cache_csr_addr=a;d.cache_csr_re=1;d.eval();auto v=d.cache_csr_rdata;d.cache_csr_re=0;return v;}
  Job job(unsigned u,unsigned w,unsigned h,unsigned ci,unsigned co,unsigned s,bool dw,bool unaligned,unsigned seed){
  unsigned k=u<2?3:1,base=(u+(restarted?4:0))*1024*1024;
  Job j{w,h,ci,co,s,dw,unaligned,base+(aligned?0x13f0:0x13f4)+unaligned,base+(aligned?0x203f0:0x203f4)+unaligned,base+0x40000,(w-k)/s+1,(h-k)/s+1,{}};
  unsigned in=w*h*ci,weights=k*k*(dw?1:ci)*co,out=j.ow*j.oh*co;
  std::fill(mem.begin()+base,mem.begin()+base+1024*1024,0xa5);
  for(unsigned i=0;i<in;i++)mem[j.ib+i]=uint8_t(i*17+seed*31);
  for(unsigned i=0;i<weights;i++)mem[j.wb+i]=uint8_t(i*29+seed*13);
  for(unsigned y=0;y<j.oh;y++)for(unsigned x=0;x<j.ow;x++)for(unsigned oc=0;oc<co;oc++){
   int64_t sum=0;
   for(unsigned ky=0;ky<k;ky++)for(unsigned kx=0;kx<k;kx++)for(unsigned ic=0;ic<(dw?1:ci);ic++){
    unsigned ia=j.ib+((y*s+ky)*w+x*s+kx)*ci+(dw?oc:ic);
    unsigned wa=j.wb+(dw?oc*k*k+ky*k+kx:((oc*k+ky)*k+kx)*ci+ic);
    sum+=int32_t(mem[ia])*int32_t(int8_t(mem[wa]));
   }
   j.expected.push_back(uint32_t(sum));
  }
  need(j.expected.size()==out,"reference shape");return j;
 }

 void abort_probe(){
  const unsigned unit=2,mask=1u<<unit,page=(unit+1)*256;
  const auto j=job(unit,16,8,16,128,1,false,false,11);
  cnn_simple_descriptor desc;
  need(!cnn_simple_make(&desc,unit,j.ib,j.wb,j.ob,j.w,j.h,j.ci,j.co,j.s,j.dw,unit),"abort descriptor");
  for(unsigned i=0;i<16;i++)wr(page+0x20+4*i,desc.word[i]);
  wr(page,1);
  // Interrupt while the bank owns a 128-bit write and buffered results remain.
  while(!counts[unit].write_bursts)tick();
  expected_abort=mask;
  wr(page,4);
  while(d.unit_busy&mask)tick();
  need((d.unit_error&mask) && !(d.unit_done&mask),"abort status");
  wr(page,2);
  tick();
  need(!(d.unit_error&mask),"clear abort state");
  expected_abort=0;
  restarted=true;
  counts={};
  run(false,false,mask);
 }
 void run(bool edge,bool limits,unsigned mask){
  std::array<Job,4> jobs={job(0,24,12,3,8,1,false,false,11),job(1,9,6,64,8,1,false,false,13),
                          job(2,16,8,16,128,1,false,false,17),job(3,16,8,64,16,1,false,false,19)};
  if(edge) {
   ram.stress=true;
   jobs={job(0,9,7,3,3,2,true,true,1),job(1,9,5,5,3,1,false,true,2),
         job(2,17,9,7,5,1,false,true,3),job(3,13,9,16,3,2,false,false,4)};
   jobs[2].ob+=4; jobs[3].ob+=12;
  }
  if(limits){
   jobs[2]=job(2,17,7,8,512,1,false,false,5);
   jobs[3]=job(3,16,8,16,128,1,false,false,6);
   jobs[2].ob+=8; jobs[3].ob+=4;
   ram.stress=true;
  }
  for(unsigned u=0;u<4;u++)if(mask>>u&1){
   auto &j=jobs[u];cnn_simple_descriptor desc;
   need(!cnn_simple_make(&desc,u,j.ib,j.wb,j.ob,j.w,j.h,j.ci,j.co,j.s,j.dw,u),"descriptor");
   for(unsigned i=0;i<16;i++)wr((u+1)*256+0x20+4*i,desc.word[i]);
  }
  const auto start=cycle;
  for(unsigned u=0;u<4;u++)if(mask>>u&1){counts[u].start=cycle;wr((u+1)*256,1);}
  while(d.unit_done!=mask)tick();
  tick();
  const auto batch=cycle-start;
  const auto fetched=ram.read_bytes;
  const auto capacity=csr(0x3c);
  const auto fills=csr(0x2c);
  const auto writebacks=csr(0x28);
  need(capacity==192u*1024 || capacity==392u*1024,"unexpected capacity");
  need(used_banks==3 && moved_banks==3,"both banks should accept compute and DMA");
  std::cerr<<"cache_bytes="<<capacity<<" fills="<<fills<<" writebacks_before_verify="<<writebacks
           <<" bank0_issue_cycles="<<issue_cycles[0]<<" bank1_issue_cycles="<<issue_cycles[1]<<"\n";
  unsigned values=0;
  for(unsigned u=0;u<4;u++)if(mask>>u&1){
   auto &j=jobs[u];
   cfg(8,j.ob);cfg(12,j.expected.size()*4);cfg(4,1);
   while(csr(0)&2)tick();
   for(unsigned i=0;i<j.expected.size();i++){
    uint32_t actual=0;for(unsigned b=0;b<4;b++)actual|=uint32_t(mem[j.ob+i*4+b])<<(8*b);
    need(actual==j.expected[i],"output mismatch after page writeback");++values;
   }
   need(mem[j.ob-1]==0xa5 && mem[j.ob+j.expected.size()*4]==0xa5,"output boundary");
  }
  std::cout<<"unit,cycles,bank_reads,bank_read_bytes,writes,input_commands,weight_commands,max_input_bytes,max_weight_bytes,bank_reads_64,writes_128,write_bytes\n";
  for(unsigned u=0;u<4;u++)if(mask>>u&1){const auto&c=counts[u];need(c.write_bytes==jobs[u].expected.size()*4,"output byte count");std::cout<<u<<","<<c.retire-c.start<<","<<c.reads<<","<<c.bytes<<","<<c.writes<<","<<c.inputs<<","<<c.weights<<","<<c.max_input<<","<<c.max_weight<<","<<c.doubles<<","<<c.write_bursts<<","<<c.write_bytes<<"\n";}
  std::cerr<<"PASS batch_cycles="<<batch<<" ddr_fill_bytes="<<fetched<<" verified_int32="<<values<<" four_mac_cycles="<<overlap<<"\n";
 }
};
int main(int argc,char**argv){Verilated::commandArgs(argc,argv);try{Bench b; bool edge=false,limits=false,abort=false; unsigned mask=15;
 for(int i=1;i<argc;i++){
  const std::string_view arg(argv[i]);
  if(arg=="--edge")edge=true;
  else if(arg=="--limits")limits=true;
  else if(arg=="--abort")abort=true;
  else if(arg=="--aligned")b.aligned=true;
  else mask=unsigned(std::stoul(argv[i]));
 }
 need(mask>0 && mask<=15,"invalid mask"); if(abort)b.abort_probe();else b.run(edge,limits,mask);return 0;}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<"\n";return 1;}}

