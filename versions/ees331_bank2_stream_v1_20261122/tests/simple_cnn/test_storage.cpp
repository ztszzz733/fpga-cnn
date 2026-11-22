#include "Vcnn_storage_top.h"
#include "verilated.h"
#include "../arm_schedule/ees331_axi_mover_model.hpp"
#include <array>
#include <vector>
#include <utility>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <cstdint>
#include <algorithm>
#include <deque>
#include "software/cnn_simple.h"
static void need(bool b,const std::string&s){if(!b)throw std::runtime_error(s);}
struct Job{unsigned w,h,ci,co,s;bool dw,unaligned;unsigned ib,wb,ob,ow,oh;std::vector<uint32_t> expected;};
struct Bench{
 Vcnn_storage_top d;
 std::array<unsigned,4> ib{},ie{},wb{},we{},ob{},oe{};
 AxiDdr<Vcnn_storage_top> ram{d};
 std::vector<uint8_t>& mem=ram.data;
 std::array<bool,4> stalled{};
 std::array<uint32_t,4> held_addr{},held_data{};
 std::array<unsigned,4> held_control{};
 std::array<uint64_t,4> accepts{},returns{},writes{};
 uint64_t cycle=0,random=193,cases=0,overlap=0,overlap4=0;
 unsigned max_outstanding=0,delay_mode=1,forced_delay=0;
 std::ofstream events{"events.csv"},wave{"small_control.vcd"};
 bool capture=false;
 unsigned rnd(){random=(random*1664525+1013904223)&0xffffffff;return unsigned(random);}
 void tick(){
  need(cycle++<20000000,"simulation watchdog");d.clk=0;
  ram.drive();d.eval();
  if(d.rst_n){
   ram.capture();
   for(unsigned u=0;u<4;u++){
    if((d.mem_valid & d.mem_ready)&(1u<<u)){accepts[u]++;if(d.mem_write&(1u<<u))writes[u]++;}
    if(d.mem_response&(1u<<u))returns[u]++;
   }
  }
  unsigned outstanding=0;for(unsigned u=0;u<4;u++)outstanding+=accepts[u]-returns[u];
  max_outstanding=std::max(max_outstanding,outstanding);
  if(capture){
   unsigned n=__builtin_popcount(unsigned(d.unit_work));if(n>=2)++overlap;if(n==4)++overlap4;
   if(d.unit_work)events<<cycle<<","<<unsigned(d.unit_busy)<<","<<unsigned(d.unit_work)<<","<<unsigned(d.mem_valid)<<","<<unsigned(d.mem_response)<<"\n";
   if(cycle<25000){wave<<"#"<<cycle*10<<"\n";
    auto bv=[&](uint32_t v,unsigned bits,char id){wave<<'b';for(int i=int(bits)-1;i>=0;i--)wave<<((v>>i)&1);wave<<' '<<id<<"\n";};
    bv(d.unit_busy,4,'!');bv(d.unit_work,4,'"');bv(d.mem_valid,4,'#');bv(d.mem_ready,4,'$');bv(d.mem_response,4,'%');bv(d.mem_write,4,'&');bv(d.operator_phase,16,'\'');bv(d.memory_phase,12,'(');
   }
  }
  d.clk=1;d.eval();d.clk=0;d.eval();
 }
 Bench(){
  events<<"cycle,busy_mask,actual_mac_mask,request_mask,response_mask\n";
  wave<<"$timescale 1 ns $end\n$scope module cnn_simple $end\n$var wire 4 ! busy $end\n$var wire 4 \" actual_mac $end\n$var wire 4 # request $end\n$var wire 4 $ ready $end\n$var wire 4 % response $end\n$var wire 4 & write $end\n$var wire 16 ' operator_state $end\n$var wire 12 ( memory_state $end\n$upscope $end\n$enddefinitions $end\n";
  ram.stress=true;d.cache_csr_addr=0;d.cache_csr_wdata=0;d.cache_csr_we=0;d.cache_csr_re=0;d.mmio_addr=0;d.mmio_wdata=0;d.mmio_we=0;d.mmio_re=0;d.memory_fault=0;d.rst_n=0;tick();tick();d.rst_n=1;tick();
 }
 void wr(unsigned a,uint32_t v){d.mmio_addr=a;d.mmio_wdata=v;d.mmio_we=1;tick();d.mmio_we=0;d.eval();}
 uint32_t rd(unsigned a){d.mmio_addr=a;d.mmio_re=1;d.eval();auto v=d.mmio_rdata;d.mmio_re=0;d.eval();return v;}
 static unsigned page(unsigned u){return (u+1)*256;}
 Job job(unsigned u,unsigned w,unsigned h,unsigned ci,unsigned co,unsigned s,bool dw,bool unaligned,unsigned seed){
  unsigned k=u<2?3:1,base=u*1024*1024;
  Job j{w,h,ci,co,s,dw,unaligned,base+0x1000+unaligned,base+0x20000+unaligned,base+0x40000,(w-k)/s+1,(h-k)/s+1,{}};
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
 void config(unsigned u,const Job&j){
  ib[u]=j.ib;ie[u]=j.ib+j.w*j.h*j.ci;wb[u]=j.wb;
  const unsigned k=u<2?3:1;we[u]=j.wb+k*k*(j.dw?1:j.ci)*j.co;
  ob[u]=j.ob;oe[u]=j.ob+j.expected.size()*4;
  cnn_simple_descriptor desc;
  need(cnn_simple_make(&desc,u,j.ib,j.wb,j.ob,j.w,j.h,j.ci,j.co,j.s,j.dw,uint32_t(cases))==0,"software descriptor rejected valid task");
  wr(page(u),2);
  for(unsigned n=0;n<16;n++)wr(page(u)+0x20+n*4,desc.word[n]);
 }
 void check(unsigned u,const Job&j){
  need(!((d.unit_busy>>u)&1),"completion before bridge drain");
  need(accepts[u]==returns[u],"unfinished memory reply");
  for(unsigned i=0;i<j.expected.size();i++){
   uint32_t got=0;for(unsigned b=0;b<4;b++)got|=uint32_t(mem[j.ob+i*4+b])<<(b*8);
   need(got==j.expected[i],"golden mismatch unit="+std::to_string(u)+" case="+std::to_string(cases)+" element="+std::to_string(i));
  }
  need(mem[j.ob-1]==0xa5&&mem[j.ob+j.expected.size()*4]==0xa5,"output guard changed");
  need(!((d.unit_error>>u)&1),"unexpected sticky error code="+std::to_string(rd(page(u)+8)));
  unsigned k=u<2?3:1;
  uint64_t mac=j.ow*j.oh*j.co*k*k*(j.dw?1:j.ci);
  need(rd(page(u)+20)==mac,"MAC counter mismatch");++cases;
 }
 void wait(unsigned mask){
  for(unsigned t=0;(d.unit_done&mask)!=mask;t++){
   if(t>=1000000){
    std::cerr<<"timeout case="<<cases<<" cycle="<<cycle<<" busy="<<unsigned(d.unit_busy)<<" done="<<unsigned(d.unit_done)<<" op="<<d.operator_phase<<" bridge="<<d.memory_phase<<" rng="<<random<<"\n";
    for(unsigned u=0;u<4;u++)std::cerr<<"u="<<u<<" accepts="<<accepts[u]<<" returns="<<returns[u]<<" pending="<<0<<" due="<<0<<"\n";
    need(false,"job timeout");
   }
   need(!(d.unit_error&mask),"operator error");tick();
  }
 }
 void check_k1_ranges(){
  unsigned checks=0;
  for(unsigned u:{2u,3u}){
   const unsigned base=page(u);
   auto j=job(u,4,3,4,3,1,false,false,7);
   // Overrun 2^32 from each descriptor base, then overlap the output with
   // inputs or weights. A rejected job must never reach the memory port.
   for(auto [offset,value]:std::array<std::pair<unsigned,uint32_t>,5>{{
       {0x20,0xfffffffcU},{0x24,0xfffffffcU},{0x28,0xfffffffcU},
       {0x28,j.ib+4},{0x28,j.wb+4}}}){
    config(u,j);
    wr(base+offset,value);
    const auto before=accepts[u];
    wr(base,1);
    for(unsigned t=0;t<400 && !((d.unit_error>>u)&1);++t)tick();
    need(((d.unit_error>>u)&1) && rd(base+8)==1 && accepts[u]==before,
         "invalid interval reached memory or was not rejected");
    ++checks;
   }
   // A half-open input interval can end exactly where the output starts.
   j.ob=j.ib+j.w*j.h*j.ci;
   const uint8_t last_input=mem[j.ob-1];
   config(u,j);wr(base,1);wait(1u<<u);
   for(unsigned i=0;i<j.expected.size();i++){
    uint32_t got=0;
    for(unsigned k=0;k<4;k++)got|=uint32_t(mem[j.ob+i*4+k])<<(8*k);
    need(got==j.expected[i],"adjacent input/output value mismatch");
   }
   need(mem[j.ob-1]==last_input && !((d.unit_error>>u)&1),"adjacent intervals rejected or input overwritten");
   ++checks;
  }
  std::cout<<"PASS K1 range checks="<<checks<<"\n";
 }
 void cfg(unsigned a,unsigned value){d.cache_csr_addr=a;d.cache_csr_wdata=value;d.cache_csr_we=1;tick();d.cache_csr_we=0;tick();}
 void fence(bool invalidate){
  cfg(8,0);cfg(12,4*1024*1024);cfg(4,invalidate?2:1);
  for(unsigned n=0;;n++){d.cache_csr_addr=0;d.cache_csr_re=1;d.eval();
   bool active=d.cache_csr_rdata&2;d.cache_csr_re=0;if(!active)break;
   need(n<1000000,"cache fence timeout");need(!d.unit_error,"cache fault during fence");tick();}
 }
 void run(){
  uint64_t work_cycles=0,hash=1469598103934665603ULL;
  for(unsigned batch=0;batch<2;batch++){
   fence(true);
   std::array<Job,4> jobs={job(0,7,7,8,8,1,false,false,1+batch),
                          job(1,7,5,5,5,2,true,true,2+batch),
                          job(2,11,9,16,8,1,false,false,3+batch),
                          job(3,11,9,5,3,2,false,true,4+batch)};
   for(unsigned u=0;u<4;u++)config(u,jobs[u]);
   capture=true;auto start=cycle;for(unsigned u=0;u<4;u++)wr(page(u),1);
   wait(15);fence(false);work_cycles+=cycle-start;
   for(unsigned u=0;u<4;u++){check(u,jobs[u]);for(unsigned i=0;i<jobs[u].expected.size()*4;i++)hash=(hash^mem[jobs[u].ob+i])*1099511628211ULL;}
   capture=false;
  }
  need(max_outstanding>=2&&overlap>0,"integration concurrency not exercised");
  std::cout<<"PASS CNN+2bank+DMA+DDR jobs="<<cases<<" cycles="<<work_cycles<<" total_cycles="<<cycle
           <<" peak_outstanding="<<max_outstanding<<" output_fnv64="<<std::hex<<hash<<std::dec
           <<" ddr_read="<<ram.read_bytes<<" ddr_write="<<ram.write_bytes<<"\n";
 }

};
int main(int argc,char**argv){Verilated::commandArgs(argc,argv);try{Bench b;if(argc==2 && std::string(argv[1])=="--k1-ranges")b.check_k1_ranges();else b.run();return 0;}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<"\n";return 1;}}
