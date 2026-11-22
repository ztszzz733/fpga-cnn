#include "Vburst_bank_test.h"
#include "verilated.h"
#include "ees331_axi_mover_model.hpp"
#include "software/cnn_simple.h"
#include <array>
#include <algorithm>
#include <iostream>
#include <stdexcept>
#include <vector>
static void need(bool b,const char*s){if(!b)throw std::runtime_error(s);}
struct Job{unsigned w,h,ci,co,s;bool dw,unaligned;unsigned ib,wb,ob,ow,oh;std::vector<uint32_t> expected;};
struct Bench{
 Vburst_bank_test d;
 AxiDdr<Vburst_bank_test> ram{d};
 std::vector<uint8_t>& mem=ram.data;
 unsigned cycle=0,overlap=0;
 struct Counts{unsigned reads=0,bytes=0,writes=0,inputs=0,weights=0,max_input=0,max_weight=0,retire=0,start=0;};
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
   need(!d.cnn_mem_fault&&!d.unit_error,"hardware fault");
   ram.capture();
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
     if(d.cnn_write>>u&1)++c.writes;else {++c.reads;c.bytes+=(d.cnn_byte>>u&1)?1:4;}
    }
   }
  }
  d.clk=1;d.eval();d.clk=0;d.eval();
 }
 void wr(unsigned a,unsigned v){d.mmio_addr=a;d.mmio_wdata=v;d.mmio_we=1;tick();d.mmio_we=0;}
 void cfg(unsigned a,unsigned v){d.cache_csr_addr=a;d.cache_csr_wdata=v;d.cache_csr_we=1;tick();d.cache_csr_we=0;tick();}
 unsigned csr(unsigned a){d.cache_csr_addr=a;d.cache_csr_re=1;d.eval();auto v=d.cache_csr_rdata;d.cache_csr_re=0;return v;}
  Job job(unsigned u,unsigned w,unsigned h,unsigned ci,unsigned co,unsigned s,bool dw,bool unaligned,unsigned seed){
  unsigned k=u<2?3:1,base=u*1024*1024;
  Job j{w,h,ci,co,s,dw,unaligned,base+0x13f4+unaligned,base+0x203f4+unaligned,base+0x40000,(w-k)/s+1,(h-k)/s+1,{}};
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

 void run(){
  std::array<Job,4> jobs={job(0,24,12,3,8,1,false,false,11),job(1,9,6,64,8,1,false,false,13),
                          job(2,16,8,16,128,1,false,false,17),job(3,16,8,64,16,1,false,false,19)};
  for(unsigned u=0;u<4;u++){
   auto &j=jobs[u];cnn_simple_descriptor desc;
   need(!cnn_simple_make(&desc,u,j.ib,j.wb,j.ob,j.w,j.h,j.ci,j.co,j.s,j.dw,u),"descriptor");
   for(unsigned i=0;i<16;i++)wr((u+1)*256+0x20+4*i,desc.word[i]);
  }
  const auto start=cycle;
  for(unsigned u=0;u<4;u++){counts[u].start=cycle;wr((u+1)*256,1);}
  while(d.unit_done!=15)tick();
  tick();
  const auto batch=cycle-start;
  const auto fetched=ram.read_bytes;
  unsigned values=0;
  for(auto &j:jobs){
   cfg(8,j.ob);cfg(12,j.expected.size()*4);cfg(4,1);
   while(csr(0)&2)tick();
   for(unsigned i=0;i<j.expected.size();i++){
    uint32_t actual=0;for(unsigned b=0;b<4;b++)actual|=uint32_t(mem[j.ob+i*4+b])<<(8*b);
    need(actual==j.expected[i],"output mismatch after page writeback");++values;
   }
   need(mem[j.ob-1]==0xa5 && mem[j.ob+j.expected.size()*4]==0xa5,"output boundary");
  }
  std::cout<<"unit,cycles,bank_reads,bank_read_bytes,writes,input_commands,weight_commands,max_input_bytes,max_weight_bytes\n";
  for(unsigned u=0;u<4;u++){const auto&c=counts[u];std::cout<<u<<","<<c.retire-c.start<<","<<c.reads<<","<<c.bytes<<","<<c.writes<<","<<c.inputs<<","<<c.weights<<","<<c.max_input<<","<<c.max_weight<<"\n";}
  std::cerr<<"PASS batch_cycles="<<batch<<" ddr_fill_bytes="<<fetched<<" verified_int32="<<values<<" four_mac_cycles="<<overlap<<"\n";
 }
};
int main(int argc,char**argv){Verilated::commandArgs(argc,argv);try{Bench b;b.run();return 0;}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<"\n";return 1;}}

