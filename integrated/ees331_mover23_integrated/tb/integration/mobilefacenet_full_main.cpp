// Cycle-driven RTL simulation. Host implements only SRAM/arbitration/checking;
// no host convolution, activation, padding, Add or intermediate tensor injection.
#include "Vquant_network_sequential.h"
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
  if(argc<5)throw std::runtime_error("expected descriptor_base command_count final_addr final_bytes [stall]");
  auto context=std::make_unique<VerilatedContext>();context->commandArgs(argc,argv);
  auto top=std::make_unique<Vquant_network_sequential>(context.get());
  auto mem=load("memory.bin"),gold=load("golden.bin"),jobs=load("jobs.bin"),regions=load("mutable.bin");
  const auto original=mem;std::vector<bool> writable(mem.size(),false);
  for(size_t r=0;r<regions.size();r+=8){auto a=word(regions,r),n=word(regions,r+4);if(size_t(a)+n>mem.size())throw std::runtime_error("bad mutable range");for(size_t i=a;i<size_t(a)+n;i++)writable[i]=true;}
  unsigned total=std::stoul(argv[2]);bool stall=argc>5 && std::stoi(argv[5]);
  if(gold.size()!=mem.size() || jobs.size()!=total*64)throw std::runtime_error("data sizes");
  top->descriptor_base=std::stoul(argv[1]);top->command_count=total;
  std::array<Request,14> pending{};std::array<unsigned,4> rr{};
  uint64_t cycles=0,reads=0,writes=0,checked=0,completed=0,last_done=0;
  std::ofstream events("events.csv"),wave("control.vcd");
  events<<"cycle,command,layer,kind,checked_bytes,reads,writes,wall_seconds\n";
  const char* names[]={"command_index","layer_index","command_kind","operator_start","command_done","conv_busy","post_busy","dw7_busy","pad_busy","done","error","phase"};
  wave<<"$timescale 1ns $end\n$scope module network $end\n";
  for(int i=0;i<12;i++)wave<<"$var wire 32 s"<<i<<" "<<names[i]<<" $end\n";
  wave<<"$upscope $end\n$enddefinitions $end\n";
  std::array<uint32_t,12> previous{};bool first=true,prev_done=false;
  auto started=std::chrono::steady_clock::now();
  while(!top->done){
   top->clk=0;top->rst_n=cycles>=5;top->clear=0;top->start=cycles==8;top->memory_fault=0;
   top->mem_ready=0;top->mem_response=0;
   for(int i=0;i<14;i++){
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
   std::array<Request,14> next{};
   if(top->rst_n && !top->cancel && (!stall || cycles%7!=3)){
    for(unsigned bank=0;bank<4;bank++)for(unsigned k=0;k<14;k++){
     unsigned i=(rr[bank]+k)%14;
     if((top->mem_valid&(1<<i)) && ((top->mem_addr[i]/4)%4==bank)){
      top->mem_ready|=1<<i;rr[bank]=(i+1)%14;
      next[i]={true,bool(top->mem_write&(1<<i)),bool(top->mem_byte&(1<<i)),top->mem_addr[i],top->mem_wdata[i]};break;
     }
    }
   }
   top->eval();top->clk=1;top->eval();pending=next;cycles++;context->timeInc(10);
   if(top->error)throw std::runtime_error("RTL error command "+std::to_string(top->command_index));
   if(top->command_done && !prev_done){
    auto j=top->command_index;auto a=word(jobs,j*64+40),n=word(jobs,j*64+44);
    if(j!=completed)throw std::runtime_error("duplicate/out-of-order completion");
    for(size_t b=0;b<n;b++)if(mem.at(a+b)!=gold.at(a+b))throw std::runtime_error("mismatch command="+std::to_string(j)+" layer="+std::to_string(top->layer_index)+" addr="+std::to_string(a+b)+" got="+std::to_string(mem[a+b])+" expected="+std::to_string(gold[a+b]));
    checked+=n;completed++;last_done=cycles;
    double wall=std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count();
    events<<cycles<<","<<j<<","<<top->layer_index<<","<<top->command_kind<<","<<n<<","<<reads<<","<<writes<<","<<wall<<"\n";events.flush();
    std::cout<<"DONE "<<j+1<<"/"<<total<<" layer="<<top->layer_index<<" kind="<<top->command_kind<<" cycle="<<cycles<<" seconds="<<wall<<std::endl;
   }
   prev_done=top->command_done;
   std::array<uint32_t,12> now{top->command_index,top->layer_index,top->command_kind,top->operator_start,top->command_done,top->conv_busy,top->post_busy,top->dw7_busy,top->pad_busy,top->done,top->error,top->phase};
   if(first || now!=previous){wave<<"#"<<cycles*10<<"\n";for(int i=0;i<12;i++)if(first || now[i]!=previous[i]){wave<<"b";for(int b=31;b>=0;b--)wave<<((now[i]>>b)&1);wave<<" s"<<i<<"\n";}previous=now;first=false;}
   if(cycles-last_done>10000000 || cycles>200000000)throw std::runtime_error("cycle watchdog at command "+std::to_string(top->command_index));
  }
  if(completed!=total)throw std::runtime_error("incomplete command list");
  for(auto r:pending)if(r.active)throw std::runtime_error("early done with outstanding memory");
  for(size_t i=0;i<mem.size();i++)if(!writable[i] && mem[i]!=original[i])throw std::runtime_error("guard corruption");
  auto a=std::stoul(argv[3]),n=std::stoul(argv[4]);std::ofstream output("embedding.bin",std::ios::binary);output.write(reinterpret_cast<char*>(mem.data()+a),n);output.close();
  std::ofstream metrics("metrics.json");metrics<<"{\"cycles\":"<<cycles<<",\"commands\":"<<completed<<",\"checked_bytes\":"<<checked<<",\"reads\":"<<reads<<",\"writes\":"<<writes<<",\"stall\":"<<stall<<"}\n";
  top->final();std::cout<<"PASS full network RTL checked="<<checked<<" cycles="<<cycles<<std::endl;return 0;
 }catch(const std::exception& e){std::cerr<<"FAIL "<<e.what()<<std::endl;return 1;}
}
