// Cycle-driven RTL simulation. Host implements only SRAM/arbitration/checking;
// no host convolution, activation, padding, Add or intermediate tensor injection.
#include "Vquant_network_parallel.h"
#include "verilated.h"
#include <array>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <vector>
#include <string>

using Bytes=std::vector<uint8_t>;
Bytes load(const std::string& p){std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("missing "+p);return Bytes(std::istreambuf_iterator<char>(f),{});}
uint32_t word(const Bytes& v,size_t a){if(a+4>v.size())throw std::runtime_error("word outside SRAM");return uint32_t(v[a])|(uint32_t(v[a+1])<<8)|(uint32_t(v[a+2])<<16)|(uint32_t(v[a+3])<<24);}
struct Request{bool active=false,write=false,byte=false;uint32_t addr=0,data=0;};

int main(int argc,char** argv){
 try{
  if(argc<3)throw std::runtime_error("expected command_count mode");
  auto context=std::make_unique<VerilatedContext>();context->commandArgs(argc,argv);
  auto top=std::make_unique<Vquant_network_parallel>(context.get());
  auto mem=load("memory.bin"),gold=load("golden.bin"),jobs=load("jobs.bin"),regions=load("mutable.bin");
  const auto original=mem;std::vector<bool> writable(mem.size(),false);
  for(size_t r=0;r<regions.size();r+=8){auto a=word(regions,r),n=word(regions,r+4);if(size_t(a)+n>mem.size())throw std::runtime_error("bad mutable range");for(size_t i=a;i<size_t(a)+n;i++)writable[i]=true;}
  unsigned total=std::stoul(argv[1]);unsigned mode=std::stoul(argv[2]);bool stall=mode==2;bool restart=mode==3;bool restarted=false;uint64_t epoch=0;
  if(gold.size()!=mem.size() || jobs.size()!=total*64)throw std::runtime_error("data sizes");
  top->task_count=total;top->engine_enable=mode==1 ? 2:3;
  std::array<Request,23> pending{};std::array<unsigned,4> rr{};
  uint64_t cycles=0,reads=0,writes=0,checked=0,completed=0,last_done=0;
  std::ofstream events("events.csv"),wave("control.vcd");
  events<<"cycle,command,layer,kind,checked_bytes,reads,writes,wall_seconds\n";
  const char* names[]={"active","operator_busy","unit_start","completion_pulse","completed_count","conv0_node","conv1_node","post_node","dw7_node","pad_node","done","error"};
  wave<<"$timescale 1ns $end\n$scope module network $end\n";
  for(int i=0;i<12;i++)wave<<"$var wire 32 s"<<i<<" "<<names[i]<<" $end\n";
  wave<<"$upscope $end\n$enddefinitions $end\n";
  std::array<uint32_t,12> previous{};bool first=true;
  std::vector<bool> seen(total,false),launched(total,false);
  uint64_t dual=0,convpost=0;std::array<unsigned,5> assignments{};
  std::ofstream launches("launches.csv");launches<<"cycle,unit,command,frame\n";
  auto started=std::chrono::steady_clock::now();
  while(!top->done){
   uint64_t local=cycles-epoch;
   top->clk=0;top->rst_n=local>=5;top->clear=0;top->start=local==total+12;top->memory_fault=0;
   top->program_valid=local>=10 && local<total+10;
   if(top->program_valid){unsigned j=local-10;top->program_index=j;
    for(unsigned k=0;k<16;k++)top->program_command[k]=word(jobs,j*64+k*4);
    auto a=word(jobs,j*64+56),b=word(jobs,j*64+60);
    top->program_dep_valid=(a!=0xffffffff ? 1:0)|(b!=0xffffffff ? 2:0);
    top->program_dep0=a&1023;top->program_dep1=b&1023;
   }
   top->mem_ready=0;top->mem_response=0;
   for(int i=0;i<23;i++){
    top->mem_rdata[i]=0;auto r=pending[i];
    if(r.active){
     const unsigned n=r.byte?1:4;
     if(size_t(r.addr)+n>mem.size() || (!r.byte && (r.addr&3)))throw std::runtime_error("bad SRAM access at "+std::to_string(r.addr));
     if(r.write){for(unsigned b=0;b<n;b++){if(!writable[r.addr+b])throw std::runtime_error("immutable write at "+std::to_string(r.addr+b));mem[r.addr+b]=r.data>>(8*b);}writes++;}
     else{top->mem_rdata[i]=r.byte ? mem[r.addr]:word(mem,r.addr);reads++;}
     top->mem_response|=1<<i;
    }
   }
   top->eval();
   std::array<Request,23> next{};
   if(top->rst_n && !top->cancel && (!stall || cycles%7!=3)){
    for(unsigned bank=0;bank<4;bank++)for(unsigned k=0;k<23;k++){
     unsigned i=(rr[bank]+k)%23;
     if((!stall || i>=10 || cycles%5==0) && (top->mem_valid&(1<<i)) && ((top->mem_addr[i]/4)%4==bank)){
      top->mem_ready|=1<<i;rr[bank]=(i+1)%23;
      next[i]={true,bool(top->mem_write&(1<<i)),bool(top->mem_byte&(1<<i)),top->mem_addr[i],top->mem_wdata[i]};break;
     }
    }
   }
   top->eval();top->clk=1;top->eval();pending=next;cycles++;context->timeInc(10);
   if(top->error)throw std::runtime_error("RTL error");
   if((top->operator_busy&3)==3)dual++;
   if((top->operator_busy&3) && (top->operator_busy&4))convpost++;
   for(unsigned u=0;u<5;u++){
    unsigned j=(top->unit_node>>(u*10))&1023;
    if(top->unit_start&(1<<u)){
     if(j>=total || launched[j])throw std::runtime_error("duplicate launch");
     auto a=word(jobs,j*64+56),b=word(jobs,j*64+60);
     if((a!=0xffffffff && !seen.at(a)) || (b!=0xffffffff && !seen.at(b)))throw std::runtime_error("early dependency");
     auto kind=word(jobs,j*64);unsigned expected=kind==0 ? u:(kind<=2 ? 2:kind);
     if((kind==0 && u>1) || u!=expected)throw std::runtime_error("wrong engine kind");
     launched[j]=true;assignments[u]++;launches<<cycles<<","<<u<<","<<j<<","<<word(jobs,j*64+52)<<"\n";
    }
    if(top->completion_pulse&(1<<u)){
     if(j>=total || !launched[j] || seen[j])throw std::runtime_error("duplicate/unlaunched completion");
     auto a=word(jobs,j*64+40),n=word(jobs,j*64+44);
     for(size_t b=0;b<n;b++)if(mem.at(a+b)!=gold.at(a+b))throw std::runtime_error("mismatch command="+std::to_string(j)+" addr="+std::to_string(a+b));
     seen[j]=true;checked+=n;completed++;last_done=cycles;
     double wall=std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count();
     events<<cycles<<","<<j<<","<<word(jobs,j*64+48)<<","<<word(jobs,j*64)<<","<<n<<","<<reads<<","<<writes<<","<<wall<<"\n";events.flush();
    }
   }
   std::array<uint32_t,12> now{top->unit_active,top->operator_busy,top->unit_start,top->completion_pulse,top->completed_count,
     uint32_t(top->unit_node&1023),uint32_t((top->unit_node>>10)&1023),uint32_t((top->unit_node>>20)&1023),
     uint32_t((top->unit_node>>30)&1023),uint32_t((top->unit_node>>40)&1023),top->done,top->error};
   if(first || now!=previous){wave<<"#"<<cycles*10<<"\n";for(int i=0;i<12;i++)if(first || now[i]!=previous[i]){wave<<"b";for(int b=31;b>=0;b--)wave<<((now[i]>>b)&1);wave<<" s"<<i<<"\n";}previous=now;first=false;}
   if(restart && !restarted && completed>=4 && top->unit_active){
    top->clk=0;top->clear=1;top->mem_ready=0;top->mem_response=0;top->eval();top->clk=1;top->eval();
    if(!top->cancel)throw std::runtime_error("clear did not cancel");
    pending={};mem=original;rr={};seen.assign(total,false);launched.assign(total,false);
    completed=0;checked=0;reads=0;writes=0;dual=0;convpost=0;assignments={};last_done=cycles;epoch=cycles;restarted=true;
    events<<"# restart\n";
   }
   if(cycles-last_done>10000000 || cycles>200000000)throw std::runtime_error("cycle watchdog at command "+std::to_string(completed));
  }
  if(completed!=total)throw std::runtime_error("incomplete command list");
  for(auto r:pending)if(r.active)throw std::runtime_error("early done with outstanding memory");
  for(size_t i=0;i<mem.size();i++)if(!writable[i] && mem[i]!=original[i])throw std::runtime_error("guard corruption");
  if(restart && !restarted)throw std::runtime_error("restart not exercised");
  if(mode!=1 && (assignments[0]==0 || assignments[1]==0 || dual==0 || convpost==0))throw std::runtime_error("missing overlap");
  if(mode==1 && assignments[0])throw std::runtime_error("disabled engine launched");
  std::ofstream output("outputs.bin",std::ios::binary);
  for(size_t r=0;r<regions.size();r+=8){auto a=word(regions,r),n=word(regions,r+4);output.write(reinterpret_cast<char*>(mem.data()+a),n);}output.close();
  std::ofstream metrics("metrics.json");metrics<<"{\"cycles\":"<<cycles<<",\"commands\":"<<completed<<",\"checked_bytes\":"<<checked<<",\"dual_busy_cycles\":"<<dual<<",\"conv_post_busy_cycles\":"<<convpost<<",\"restart\":"<<restarted<<",\"assignments\":[";
  for(int u=0;u<5;u++)metrics<<(u ? ",":"")<<assignments[u];metrics<<"]}\n";
  top->final();std::cout<<"PASS parallel small RTL checked="<<checked<<" cycles="<<cycles<<std::endl;return 0;
 }catch(const std::exception& e){std::cerr<<"FAIL "<<e.what()<<std::endl;return 1;}
}
