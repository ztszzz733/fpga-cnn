#include "Vconv_memory_perf_top.h"
#include "verilated.h"
#include "ees331_axi_mover_model.hpp"
#include <cstdint>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
using U=uint32_t;using Q=uint64_t;
static void need(bool good,const char* why){if(!good)throw std::runtime_error(why);}
struct Bench{
 Vconv_memory_perf_top d;AxiDdr<Vconv_memory_perf_top> ram{d};
 Q cycle=0,work0=0,work1=0,work_overlap=0;
 Q started[2]={0,0},finished[2]={0,0};
 std::set<U> completed;
 bool plan;U k,w,h,ci,co,ow,oh,inbytes,weightbytes,outbytes;
 static constexpr U IN0=0x100000,IN1=0x200000,OUT0=0x300000,OUT1=0x400000;
 static constexpr U LOCAL=0x04000000,LI0=32768,LI1=131072,LW=0,LO0=65536,LO1=233472;
 Bench(bool p,U kernel,U width,U height,U inputs,U outputs):plan(p),k(kernel),w(width),h(height),ci(inputs),co(outputs){
  ow=w-k+1;oh=h-k+1;inbytes=w*h*ci;weightbytes=k*k*ci*co;outbytes=ow*oh*co*4;
  need(LI0+inbytes<=LO0 && LO0+outbytes<=LI1 && LI1+inbytes<=LO1 && LO1+outbytes<=335872 && weightbytes<=LI0,"fixture exceeds reserved buffers");
  d.rst_n=0;d.kind=k==3;d.start=0;d.width=w;d.height=h;d.ci=ci;d.co=co;
  d.input_base0=plan?LOCAL+LI0:IN0;d.input_base1=plan?LOCAL+LI1:IN1;
  d.weight_base=plan?LOCAL+LW:0;d.output_base0=plan?LOCAL+LO0:OUT0;d.output_base1=plan?LOCAL+LO1:OUT1;
  d.cache_csr_addr=d.cache_csr_wdata=d.cache_csr_re=d.cache_csr_we=0;
  d.plan_cmd_valid=d.plan_cmd_epoch=d.plan_cmd_frame_id=d.plan_cmd_id=0;
  d.plan_cmd_direction=d.plan_cmd_ddr_offset=d.plan_cmd_local_offset=d.plan_cmd_bytes=0;
  d.plan_rsp_ready=1;d.plan_recover=0;
  ram.stress=true;
  for(U f=0;f<2;f++)for(U i=0;i<inbytes;i++)ram.data[(f?IN1:IN0)+i]=uint8_t((i*13+f*71+5)%256);
  for(U i=0;i<weightbytes;i++)ram.data[i]=uint8_t(int(i*7%17)-8);
  for(int i=0;i<5;i++)tick();d.rst_n=1;tick();
 }
 bool tick(){
  need(cycle<12000000,"benchmark watchdog");
  d.clk=0;ram.drive();d.eval();
  bool accepted=d.plan_cmd_valid&&d.plan_cmd_ready;
  if(d.plan_rsp_valid&&d.plan_rsp_ready){
   U id=d.plan_rsp_id;
   need(d.plan_rsp_epoch==17&&d.plan_rsp_status==0,"DMA completion error");
   need(id<=4&&d.plan_rsp_frame_id==((id==2||id==4)?1:0),"DMA identity mismatch");
   need(d.plan_rsp_kind==(id>=3?2:0),"DMA kind mismatch");
   need(completed.insert(id).second,"duplicate DMA completion");
  }
  if(d.rst_n){
   if(d.mac_work&1)work0++;if(d.mac_work&2)work1++;if(d.mac_work==3)work_overlap++;
   for(U f=0;f<2;f++)if((d.done>>f&1)&&!finished[f])finished[f]=cycle;
   ram.capture();
  }
  d.clk=1;d.eval();d.clk=0;d.eval();cycle++;
  need(!d.error&&!d.cnn_mem_fault&&!d.plan_fault,"operator/storage error");
  return accepted;
 }
 U csr(U addr){d.cache_csr_addr=addr;d.cache_csr_re=1;d.eval();U value=d.cache_csr_rdata;d.cache_csr_re=0;return value;}
 void cfg(U addr,U value){d.cache_csr_addr=addr;d.cache_csr_wdata=value;d.cache_csr_we=1;tick();d.cache_csr_we=0;tick();}
 void move(U id,bool store,U dd,U ll,U bytes){
  d.plan_cmd_epoch=17;d.plan_cmd_frame_id=(id==2||id==4)?1:0;d.plan_cmd_id=id;
  d.plan_cmd_direction=store;d.plan_cmd_ddr_offset=dd;d.plan_cmd_local_offset=ll;d.plan_cmd_bytes=bytes;d.plan_cmd_valid=1;
  for(U n=0;n<1000000;n++)if(tick()){d.plan_cmd_valid=0;return;}
  throw std::runtime_error("DMA queue stuck");
 }
 void start(U mask){for(U f=0;f<2;f++)if(mask>>f&1)started[f]=cycle;d.start=mask;tick();d.start=0;}
 U word(U address){U v=0;for(U i=0;i<4;i++)v|=U(ram.data[address+i])<<(i*8);return v;}
 void verify(){
  for(U f=0;f<2;f++)for(U y=0;y<oh;y++)for(U x=0;x<ow;x++)for(U oc=0;oc<co;oc++){
   int32_t sum=0;
   for(U ky=0;ky<k;ky++)for(U kx=0;kx<k;kx++)for(U ic=0;ic<ci;ic++){
    U a=(f?IN1:IN0)+((y+ky)*w+x+kx)*ci+ic;
    U wi=((oc*k+ky)*k+kx)*ci+ic;
    sum+=int32_t(ram.data[a])*int32_t(int8_t(ram.data[wi]));
   }
   U actual=word((f?OUT1:OUT0)+((y*ow+x)*co+oc)*4);
   need(actual==U(sum),"integer convolution result mismatch");
  }
  U expected=ow*oh*co*ci*k*k;
  need(d.macs0==expected&&d.macs1==expected,"effective MAC count mismatch");
 }
 void run(){
  Q begin=cycle;
  if(plan){
   move(0,false,0,LW,weightbytes);move(1,false,IN0,LI0,inbytes);
   while(!completed.count(0)||!completed.count(1))tick();
   start(1);move(2,false,IN1,LI1,inbytes);
   bool saved0=false,saved1=false,running1=false;
   while(!saved0||!saved1||!completed.count(3)||!completed.count(4)){
    tick();
    if(!running1&&completed.count(2)){running1=true;start(2);}
    if(!saved0&&finished[0]){saved0=true;move(3,true,OUT0,LO0,outbytes);}
    if(!saved1&&finished[1]){saved1=true;move(4,true,OUT1,LO1,outbytes);}
   }
  }else{
   start(3);while(!finished[0]||!finished[1])tick();
   cfg(8,OUT0);cfg(12,OUT1+outbytes-OUT0);cfg(4,1);
   while(csr(0)&2)tick();
  }
  Q total=cycle-begin;
  verify();
  std::cout<<"PERF {\"mode\":\""<<(plan?"explicit":"legacy")<<"\",\"kernel\":"<<k<<",\"width\":"<<w<<",\"height\":"<<h<<",\"ci\":"<<ci<<",\"co\":"<<co
   <<",\"images\":2,\"cycles\":"<<total<<",\"run0_cycles\":"<<(finished[0]-started[0])<<",\"run1_cycles\":"<<(finished[1]-started[1])
   <<",\"mac_work0\":"<<work0<<",\"mac_work1\":"<<work1<<",\"mac_overlap_cycles\":"<<work_overlap
   <<",\"ddr_read_bytes\":"<<ram.read_bytes<<",\"ddr_write_bytes\":"<<ram.write_bytes
   <<",\"local_dma_overlap_cycles\":"<<(plan?csr(0x6c):0)<<",\"checked_bytes\":"<<2*outbytes<<",\"status\":\"PASS\"}"<<std::endl;
 }
};
int main(int argc,char**argv){try{
 need(argc==2,"usage: executable legacy|explicit");bool plan=std::string(argv[1])=="explicit";
 {Bench b(plan,1,14,14,64,64);b.run();}
 {Bench b(plan,3,18,18,16,16);b.run();}
 return 0;
}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<std::endl;return 1;}}
