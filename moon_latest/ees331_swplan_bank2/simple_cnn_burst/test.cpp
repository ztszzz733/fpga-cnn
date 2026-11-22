#include "Vcnn_simple_top.h"
#include "verilated.h"
#include <array>
#include <vector>
#include <deque>
#include <map>
#include <utility>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <cstdint>
#include <algorithm>
#include "software/cnn_simple.h"
static void need(bool b,const std::string&s){if(!b)throw std::runtime_error(s);}
struct Job{unsigned w,h,ci,co,s;bool dw,unaligned;unsigned ib,wb,ob,ow,oh;std::vector<uint32_t> expected;};
struct Bench{
 Vcnn_simple_top d;
 struct Pending{bool valid=false;uint64_t due=0;uint32_t data=0;};
 std::array<std::deque<Pending>,4> q;
 std::array<uint64_t,4> reads{},read_bytes{},cmds{},largest{};
 std::array<uint64_t,4> input_cmds{},weight_cmds{},max_input{},max_weight{};
 bool fair_bus=false,force_stall=false;
 std::vector<uint8_t> mem=std::vector<uint8_t>(4*1024*1024,0xa5);
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
  need(cycle++<20000000,"simulation watchdog");d.clk=0;d.mem_ready=0;d.mem_response=0;
  for(int u=0;u<4;u++)d.mem_rdata[u]=0;
  d.eval();
  for(unsigned u=0;u<4;u++){
   bool v=(d.mem_valid>>u)&1;
   unsigned ctl=((d.mem_write>>u)&1)|(((d.mem_byte>>u)&1)<<1);
   if(stalled[u])need(v&&held_addr[u]==d.mem_addr[u]&&held_data[u]==d.mem_wdata[u]&&held_control[u]==ctl,"request changed under backpressure");
   bool replied=false;
   if(!q[u].empty() && q[u].front().due<=cycle){
    d.mem_response|=1u<<u;d.mem_rdata[u]=q[u].front().data;q[u].pop_front();++returns[u];replied=true;
   }
   bool ready=!force_stall && q[u].size()<4 && (fair_bus || delay_mode==0 || (rnd()>>16)%4!=0);
   if(ready)d.mem_ready|=1u<<u;
   stalled[u]=v&&!ready;held_addr[u]=d.mem_addr[u];held_data[u]=d.mem_wdata[u];held_control[u]=ctl;
   if(v&&ready){
    need(q[u].size()<4,"credit overflow");++accepts[u];
    uint32_t a=d.mem_addr[u],data=0;unsigned bytes=ctl&2?1:4;
    need(uint64_t(a)+bytes<=mem.size(),"request outside memory");
    if(ctl&1){for(unsigned b=0;b<bytes;b++)mem[a+b]=uint8_t(d.mem_wdata[u]>>(8*b));++writes[u];}
    else if(bytes==1)data=uint32_t(int32_t(int8_t(mem[a])));
    else for(unsigned b=0;b<4;b++)data|=uint32_t(mem[a+b])<<(8*b);
    if(!(ctl&1)){++reads[u];read_bytes[u]+=bytes;}
    bool immediate=!fair_bus&&!forced_delay&&!replied&&q[u].empty()&&(delay_mode==0||(delay_mode==2&&((rnd()>>16)%2)));
    if(immediate){d.mem_response|=1u<<u;d.mem_rdata[u]=data;++returns[u];}
    else q[u].push_back({true,cycle+(forced_delay?forced_delay:(fair_bus?4:1+rnd()%7)),data});
   }
  }
  d.eval();
  unsigned outstanding=0;for(auto&p:q)outstanding+=p.size();
  for(unsigned u=0;u<4;u++)if((d.span_accept>>u)&1){
   bool weight=(d.span_weight>>u)&1;uint64_t n=(d.span_bytes>>(u*13))&8191;
   ++cmds[u];largest[u]=std::max(largest[u],n);
   ++(weight?weight_cmds[u]:input_cmds[u]);auto &peak=weight?max_weight[u]:max_input[u];peak=std::max(peak,n);
  }
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
  d.mmio_addr=0;d.mmio_wdata=0;d.mmio_we=0;d.mmio_re=0;d.memory_fault=0;d.rst_n=0;tick();tick();d.rst_n=1;tick();
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
  cnn_simple_descriptor desc;
  need(cnn_simple_make(&desc,u,j.ib,j.wb,j.ob,j.w,j.h,j.ci,j.co,j.s,j.dw,uint32_t(cases))==0,"software descriptor rejected valid task");
  wr(page(u),2);
  for(unsigned n=0;n<16;n++)wr(page(u)+0x20+n*4,desc.word[n]);
 }
 void check(unsigned u,const Job&j){
  need(!((d.unit_busy>>u)&1),"completion before bridge drain");
  need(q[u].empty()&&accepts[u]==returns[u],"unfinished memory reply");
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
    for(unsigned u=0;u<4;u++)std::cerr<<"u="<<u<<" accepts="<<accepts[u]<<" returns="<<returns[u]<<" pending="<<(!q[u].empty())<<" due="<<(q[u].empty()?0:q[u].front().due)<<"\n";
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
 void abort_full(){
  // Force an offered fourth beat to stall while three earlier beats are in flight.
  fair_bus=true;
  for(unsigned u=0;u<4;u++){
   auto j=job(u,9,7,16,8,1,false,false,u);
   config(u,j);forced_delay=40;wr(page(u),1);
   for(unsigned n=0;q[u].size()!=3;n++){need(n<500,"no three outstanding beats");tick();}
   force_stall=true;tick();need(stalled[u],"fourth beat did not stall");
   wr(page(u),4);for(int i=0;i<10;i++)tick();
   need((d.unit_busy>>u)&1,"aborted port released before drain");
   force_stall=false;
   for(unsigned n=0;(d.unit_busy>>u)&1;n++){need(n<200,"stalled abort did not drain");tick();}
   need(q[u].empty() && accepts[u]==returns[u],"late responses lost");
   forced_delay=0;config(u,j);wr(page(u),1);wait(1u<<u);check(u,j);
  }
  std::cout<<"PASS cancel under backpressure and restart on four ports\n";
 }
 void compare(){
  // A fixed four-cycle, ordered resident-port model makes A/B independent of RNG.
  fair_bus=true;
  std::cout<<"case,unit,cycles,bank_reads,read_bytes,writes,span_commands,input_commands,weight_commands,max_input_bytes,max_weight_bytes\n";
  for(unsigned n=0;n<4;n++){
   unsigned u=n<2?n:2+(n-2);
   auto j=n==0?job(u,24,12,3,8,1,false,false,11):
          n==1?job(u,17,11,5,5,2,true,true,13):
          n==2?job(u,16,8,16,128,1,false,false,17):
               job(u,16,8,64,16,1,false,false,19);
   // Keep tensors separate while crossing a 1 KiB pager boundary.
   config(u,j);const auto start=cycle;wr(page(u),1);wait(1u<<u);
   check(u,j);
   std::cout<<n<<","<<u<<","<<cycle-start<<","<<reads[u]<<","<<read_bytes[u]<<","<<writes[u]<<","<<cmds[u]<<","<<input_cmds[u]<<","<<weight_cmds[u]<<","<<max_input[u]<<","<<max_weight[u]<<"\n";
  }
 }
 void run(){
  need(rd(0)==0x53434e31&&rd(8)==0x202,"MMIO version/config");
  std::array<Job,4> parallel={job(0,7,7,8,8,1,false,false,1),job(1,7,7,8,8,1,false,false,2),job(2,11,9,16,8,1,false,false,3),job(3,11,9,16,8,1,false,false,4)};
  for(unsigned u=0;u<4;u++)config(u,parallel[u]);
  capture=true;for(unsigned u=0;u<4;u++)wr(page(u),1);
  // Busy-start and descriptor edits must be rejected without changing the job.
  uint32_t before=rd(page(0)+0x20);wr(page(0)+0x20,0);need(rd(page(0)+8)==2&&rd(page(0)+0x20)==before,"busy descriptor mutation");
  wr(page(0),1);need(rd(page(0)+8)==2,"busy start accepted");wr(page(0),2);
  wait(15);for(unsigned u=0;u<4;u++)check(u,parallel[u]);capture=false;
  need(overlap>0&&max_outstanding>=4,"parallel execution not demonstrated");
  for(unsigned mode=0;mode<3;mode++)for(unsigned ci:{1u,3u,4u,5u,8u,16u})for(unsigned stride:{1u,2u})for(unsigned u=0;u<4;u++){
   delay_mode=mode;bool dw=u<2&&ci%2;bool unaligned=(ci+mode+u)%2;
   auto j=job(u,u<2?5:7,u<2?4:5,ci,dw?ci:3,stride,dw,unaligned,unsigned(cases));
   config(u,j);wr(page(u),1);wait(1u<<u);check(u,j);
  }
  for(unsigned u=0;u<4;u++)for(unsigned ci:{64u,512u}){
   auto j=job(u,3,3,ci,1,1,false,false,unsigned(cases));config(u,j);wr(page(u),1);wait(1u<<u);check(u,j);
  }
  // Invalid descriptor must stop without issuing memory requests.
  for(unsigned u=0;u<4;u++){
   auto j=job(u,5,5,4,3,1,false,false,unsigned(cases));config(u,j);auto old=accepts[u];
   wr(page(u)+0x34,0);wr(page(u),1);for(unsigned n=0;n<250;n++)tick();
   need(((d.unit_error>>u)&1)&&accepts[u]==old,"invalid descriptor escaped to memory");wr(page(u),2);
  }
  // Cancel a stalled/accepted request, drain the late response, then reuse.
  for(unsigned u=0;u<4;u++){
   auto j=job(u,5,5,4,3,1,false,false,unsigned(cases));config(u,j);forced_delay=40;wr(page(u),1);
   for(unsigned t=0;q[u].empty();t++){need(t<1000,"no abort target");tick();}
   wr(page(u),4);for(unsigned t=0;(d.unit_busy>>u)&1;t++){need(t<200,"abort did not drain");tick();}
   need(q[u].empty(),"abort lost response");forced_delay=0;
   auto replacement=job(u,5,5,4,3,1,false,false,unsigned(cases+31));config(u,replacement);wr(page(u),1);wait(1u<<u);check(u,replacement);
  }
  d.memory_fault=1;tick();tick();need(d.unit_error==15,"memory fault not propagated");d.memory_fault=0;
  for(unsigned n=0;n<5;n++)tick();
  for(unsigned u=0;u<4;u++){need(rd(page(u)+8)==5,"memory fault code");wr(page(u),2);}
  std::ofstream result("metrics.json");
  result<<"{\"status\":\"PASS\",\"numerical_jobs\":"<<cases<<",\"invalid_jobs\":4,\"abort_restart_jobs\":4,\"cycles\":"<<cycle<<",\"actual_mac_overlap_cycles\":"<<overlap<<",\"all_four_mac_cycles\":"<<overlap4<<",\"max_outstanding_total\":"<<max_outstanding<<"}\n";
  std::cout<<"PASS jobs="<<cases<<" overlap="<<overlap<<" four_mac="<<overlap4<<" outstanding="<<max_outstanding<<" cycles="<<cycle<<"\n";
 }
};
int main(int argc,char**argv){Verilated::commandArgs(argc,argv);try{Bench b;if(argc==2 && std::string(argv[1])=="--abort-full")b.abort_full();else if(argc==2 && std::string(argv[1])=="--compare")b.compare();else if(argc==2 && std::string(argv[1])=="--k1-ranges")b.check_k1_ranges();else b.run();return 0;}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<"\n";return 1;}}
