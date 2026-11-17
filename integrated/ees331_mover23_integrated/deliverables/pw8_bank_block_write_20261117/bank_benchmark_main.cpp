#include "Vbank_benchmark_top.h"
#include "verilated.h"
#include <algorithm>
#include <array>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <random>
#include <stdexcept>
#include <vector>
using U=uint32_t;using Q=uint64_t;
static void need(bool v,const char* why){if(!v)throw std::runtime_error(why);}
struct Spec{U w,h,ci,co,stride,offset;bool stress=false;};
struct Sample{bool dma_ready,dma_rsp;U dma_data;};
struct Result{Q cycles=0,mac_cycles=0,queue_stall=0,drain_cycles=0;U writes=0,acks=0,service=0,reads=0,words=0,bytes=0;};
struct Bench{
 Vbank_benchmark_top d;Q cycle=0;bool measuring=false;
 U ib=4096,wb=0,ob=0,ow=0,oh=0,inbytes=0,weightbytes=0,outbytes=0;
 std::vector<uint8_t> input,weight;std::vector<U> gold;std::vector<bool> seen;
 std::array<U,4> held_mem{};std::array<U,3> held_block{};
 bool hold_mem=false,hold_block=false,hold_data=false;U held_data=0;
 Result result;Spec spec;
 Bench(bool optimized,Spec s):spec(s){
  ib+=s.offset;inbytes=s.w*s.h*s.ci;weightbytes=s.ci*s.co;
  wb=((ib+inbytes+127)&~63u)+s.offset;ob=(wb+weightbytes+127)&~63u;
  ow=(s.w-1)/s.stride+1;oh=(s.h-1)/s.stride+1;outbytes=ow*oh*s.co*4;
  need(ob+outbytes+32<=401408,"fixture does not fit real 392KiB RAM");
  std::mt19937 rng(733+s.w*11+s.ci+s.co+s.offset);
  input.resize(inbytes);weight.resize(weightbytes);
  for(auto&v:input)v=rng()%256;for(auto&v:weight)v=rng()%256;
  if(input.size()>1){input[0]=255;input[1]=128;}if(weight.size()>1){weight[0]=128;weight[1]=127;}
  for(U y=0;y<s.h;y+=s.stride)for(U x=0;x<s.w;x+=s.stride)for(U o=0;o<s.co;o++){
   int64_t sum=0;for(U c=0;c<s.ci;c++)sum+=int64_t(input[(y*s.w+x)*s.ci+c])*int8_t(weight[o*s.ci+c]);gold.push_back(U(sum));
  }
  seen.assign(gold.size(),false);
  d.optimized=optimized;d.rst_n=0;d.clear=d.start=d.stall=d.depthwise=0;
  d.input_base=ib;d.weight_base=wb;d.output_base=ob;d.width=s.w;d.height=s.h;
  d.in_channels=s.ci;d.out_channels=s.co;d.kernel=1;d.stride=s.stride;
  d.dma_valid=d.dma_write=d.dma_addr=d.dma_wdata=d.dma_wstrb=0;
  for(int i=0;i<4;i++)tick();d.rst_n=1;tick();
  preload(ib,input);preload(wb,weight);preload(ob-32,std::vector<uint8_t>(outbytes+64,0xa5));
 }
 Sample tick(){
  need(cycle<12000000,"test watchdog");
  d.clk=0;d.eval();
  Sample sample{bool(d.dma_ready),bool(d.dma_rsp_valid),U(d.dma_rdata)};
  if(measuring){
   need(!d.error&&!d.bank_fault,"unexpected engine/bank error");
   std::array<U,4> request{d.debug_write,d.debug_byte,d.debug_addr,d.debug_data};
   if(hold_mem)need(d.debug_valid&&request==held_mem,"scalar request changed under backpressure");
   hold_mem=d.debug_valid&&!d.debug_ready;held_mem=request;
   if(d.debug_valid&&d.debug_ready&&!d.debug_write){
    U n=d.debug_byte?1:4,a=d.debug_addr;
    need((a>=ib&&Q(a)+n<=Q(ib)+inbytes)||(a>=wb&&Q(a)+n<=Q(wb)+weightbytes),"read outside valid source");
   }
   std::array<U,3> packet{d.debug_block_base,d.debug_block_stride,d.debug_block_words};
   if(hold_block)need(d.debug_block_valid&&packet==held_block,"block descriptor changed under backpressure");
   hold_block=d.debug_block_valid&&!d.debug_block_ready;held_block=packet;
   if(hold_data)need(d.debug_data_valid&&d.debug_block_data==held_data,"block data changed under backpressure");
   hold_data=d.debug_data_valid&&!d.debug_data_ready;held_data=d.debug_block_data;
   if(d.commit_valid){
    U a=d.commit_addr;need(a>=ob&&Q(a)+4<=Q(ob)+outbytes&&(a-ob)%4==0,"bank write outside output");
    U index=(a-ob)/4;need(!seen[index],"duplicate bank write");seen[index]=true;
    need(d.commit_data==gold[index],"committed result differs from integer reference");
   }
   result.cycles++;if(d.mac_fire)result.mac_cycles++;if(d.queue_stall)result.queue_stall++;
   if(d.phase==9)result.drain_cycles++;
  }
  d.clk=1;d.eval();d.clk=0;d.eval();cycle++;
  return sample;
 }
 U dma(bool write,U a,U value=0,U mask=15){
  d.dma_addr=a;d.dma_write=write;d.dma_wdata=value;d.dma_wstrb=mask;d.dma_valid=1;
  for(U n=0;;n++){auto s=tick();if(s.dma_ready)break;need(n<100,"DMA not accepted");}
  d.dma_valid=0;
  for(U n=0;;n++){auto s=tick();if(s.dma_rsp){need(!d.dma_error,"DMA RAM error");return s.dma_data;}need(n<100,"DMA response missing");}
 }
 void preload(U base,const std::vector<uint8_t>&bytes){
  U i=0;while(i<bytes.size()){
   U address=(base+i)&~3u,value=0,mask=0;
   while(i<bytes.size()&&((base+i)&~3u)==address){U lane=(base+i)&3;value|=U(bytes[i])<<(lane*8);mask|=1u<<lane;i++;}
   dma(true,address,value,mask);
  }
 }
 Result run(bool restart=false,bool latch=false){
  measuring=true;d.start=1;tick();d.start=0;
  if(latch){d.width=0;d.input_base=0;d.out_channels=0;}
  bool did_restart=false;
  for(Q n=0;n<5000000;n++){
   d.stall=spec.stress && n%11<3;
   d.clk=0;d.eval();
   if(d.done){need(d.bank_idle,"done before bank writes/responses drained");break;}
   if(restart&&!did_restart&&d.debug_data_valid){
    measuring=false;d.clear=1;d.stall=0;tick();tick();d.clear=0;tick();
    preload(ob-32,std::vector<uint8_t>(outbytes+64,0xa5));seen.assign(gold.size(),false);result={};hold_mem=hold_block=hold_data=false;
    d.input_base=ib;d.width=spec.w;d.out_channels=spec.co;
    measuring=true;d.start=1;tick();d.start=0;did_restart=true;
   }
   tick();need(n<4999999,"engine not completed");
  }
  need(d.done,"no done");need(!restart||did_restart,"restart path not exercised");
  result.writes=d.write_commands;result.acks=d.write_completions;result.service=d.write_service_cycles;
  result.reads=d.read_commands;result.words=d.write_commits;result.bytes=outbytes;
  need(result.writes==result.acks,"missing write completion");need(result.words==gold.size(),"wrong committed word count");
  need(d.input_reads==ow*oh*spec.ci,"input bytes changed");need(d.mac_count==ow*oh*spec.ci*spec.co,"MAC count changed");
  need(std::all_of(seen.begin(),seen.end(),[](bool v){return v;}),"missing output writes");
  measuring=false;d.stall=0;
  for(U i=0;i<gold.size();i++)need(dma(false,ob+4*i)==gold[i],"physical RAM readback mismatch");
  for(U i=0;i<32;i+=4){need(dma(false,ob-32+i)==0xa5a5a5a5,"head guard corrupted");need(dma(false,ob+outbytes+i)==0xa5a5a5a5,"tail guard corrupted");}
  return result;
 }
};
static void output(std::ostream&f,const Result&r){
 f<<"{\"cycles\":"<<r.cycles<<",\"mac_cycles\":"<<r.mac_cycles<<",\"queue_stall_cycles\":"<<r.queue_stall<<",\"drain_cycles\":"<<r.drain_cycles
 <<",\"write_commands\":"<<r.writes<<",\"write_completions\":"<<r.acks<<",\"write_service_cycles\":"<<r.service<<",\"read_commands\":"<<r.reads<<",\"bank_write_words\":"<<r.words<<",\"output_bytes\":"<<r.bytes<<'}';
}
int main(int argc,char**argv){try{
 need(argc==2,"metrics path required");std::ofstream f(argv[1]);f<<"{\"status\":\"PASS\",\"ddr_included\":false,\"cases\":[";
 std::vector<Spec> specs={
  {7,7,32,64,1,0},{14,14,64,64,1,0},{28,28,64,64,1,0},{7,7,128,128,1,0},
  {14,14,128,64,1,0},{14,14,16,64,1,0},{14,14,4,64,1,0},
  {1,1,3,1,1,1},{1,3,7,5,1,3},{2,2,8,7,1,0},{5,3,64,17,1,0},
  {9,5,65,17,2,1},{7,3,512,5,1,0},{11,9,96,17,2,3,true},
  {5,3,64,8,1,0,true},{1,1,512,128,1,0,true},
 };
 for(U i=0;i<specs.size();i++){
  auto s=specs[i];std::cout<<"CASE "<<i<<std::endl;
  Result old=Bench(false,s).run(),tuned=Bench(true,s).run();
  need(old.reads==tuned.reads&&old.words==tuned.words&&old.mac_cycles==tuned.mac_cycles,"input/computation/bank word workload changed");
  if(i)f<<',';f<<"{\"id\":"<<i<<",\"width\":"<<s.w<<",\"height\":"<<s.h<<",\"ci\":"<<s.ci<<",\"co\":"<<s.co<<",\"stride\":"<<s.stride<<",\"offset\":"<<s.offset<<",\"stress\":"<<(s.stress?"true":"false")<<",\"old\":";output(f,old);f<<",\"new\":";output(f,tuned);f<<'}';
  std::cout<<"PERF "<<s.w<<'x'<<s.h<<" Ci="<<s.ci<<" Co="<<s.co<<" old="<<old.cycles<<" new="<<tuned.cycles<<" saved_pct="<<(100.0*(1-double(tuned.cycles)/old.cycles))<<std::endl;
 }
 Bench(true,{5,3,64,8,1,0,true}).run(true);
 Bench(true,{9,5,64,17,2,0,true}).run(false,true);
 f<<"],\"clear_mid_block_restart\":true,\"descriptor_latching\":true}\n";
 std::cout<<"PASS real bank block writes numerical/physical readback, strided layout, tails, backpressure, completion and restart cases="<<specs.size()<<std::endl;
 return 0;
}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<std::endl;return 1;}}
