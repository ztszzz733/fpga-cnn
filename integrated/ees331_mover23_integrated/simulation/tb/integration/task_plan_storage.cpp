#include "Vcnn_plan_storage.h"
#include "verilated.h"
#include "ees331_axi_mover_model.hpp"
#include <cstdint>
#include <iostream>
#include <stdexcept>
using U=uint32_t;
using Q=uint64_t;
static constexpr U LOCAL=0x04000000, DDR=0x20000;
static void need(bool ok,const char* why){if(!ok)throw std::runtime_error(why);}
struct Sample {
 U ready,response,data0,data1,data2,data3;
 bool cmd_ready,rsp_valid;
 U epoch,frame,id,kind,status;
};
struct Bench {
 Vcnn_plan_storage d;
 AxiDdr<Vcnn_plan_storage> ram{d};
 Q cycle=0;
 bool inject_read_error=false;
 bool hold_read_responses=false;
 Bench(){
  d.rst_n=0;d.cnn_valid=d.cnn_write=d.cnn_byte=d.cnn_cancel=0;
  d.cache_csr_addr=d.cache_csr_wdata=d.cache_csr_re=d.cache_csr_we=0;
  d.plan_cmd_valid=d.plan_cmd_epoch=d.plan_cmd_frame_id=d.plan_cmd_id=0;
  d.plan_cmd_direction=d.plan_cmd_ddr_offset=d.plan_cmd_local_offset=d.plan_cmd_bytes=0;
  d.plan_rsp_ready=1;d.plan_recover=0;
  for(int k=0;k<12;k++)d.cnn_addr[k]=d.cnn_wdata[k]=0;
  ram.stress=true;
  for(U i=0;i<4096;i++)ram.data[DDR+i]=uint8_t((i*37u+11u)&255u);
  for(int i=0;i<5;i++)step();d.rst_n=1;step();
 }
 Sample step(){
  need(cycle<300000,"watchdog");
  d.clk=0;ram.drive();
  if(inject_read_error && d.S_AXI_HP0_RVALID){
   d.S_AXI_HP0_RRESP=2;inject_read_error=false;
  }
  if(hold_read_responses)d.S_AXI_HP0_RVALID=0;
  d.eval();
  Sample s{U(d.cnn_ready),U(d.cnn_response),U(d.cnn_rdata[0]),U(d.cnn_rdata[1]),
   U(d.cnn_rdata[2]),U(d.cnn_rdata[3]),
   bool(d.plan_cmd_ready),bool(d.plan_rsp_valid),U(d.plan_rsp_epoch),
   U(d.plan_rsp_frame_id),U(d.plan_rsp_id),U(d.plan_rsp_kind),U(d.plan_rsp_status)};
  if(d.rst_n)ram.capture();d.clk=1;d.eval();d.clk=0;d.eval();cycle++;
  need(!d.cnn_mem_fault,"CNN memory fault");
  return s;
 }
 U word(U at)const{
  U v=0;for(U i=0;i<4;i++)v|=U(ram.data[at+i])<<(i*8);return v;
 }
 U csr(U addr){d.cache_csr_addr=addr;d.eval();return d.cache_csr_rdata;}
 void cfg(U addr,U value){
  d.cache_csr_addr=addr;d.cache_csr_wdata=value;d.cache_csr_we=1;
  step();d.cache_csr_we=0;step();
 }
 U access(U addr,bool write=false,U value=0,U client=0){
  d.cnn_addr[client]=addr;d.cnn_wdata[client]=value;
  d.cnn_valid=1u<<client;d.cnn_write=write?(1u<<client):0;
  for(U n=0;n<100000;n++){
   auto s=step();if(s.ready&(1u<<client))break;
   need(n<99999,"CNN accept timeout");
  }
  d.cnn_valid=d.cnn_write=0;
  for(U n=0;n<100000;n++){
   auto s=step();if(s.response&(1u<<client))return client==0?s.data0:s.data1;
   need(n<99999,"CNN response timeout");
  }
  throw std::runtime_error("unreachable");
 }
 void submit(U epoch,U frame,U id,bool store,U ddr,U local,U bytes){
  d.plan_cmd_epoch=epoch;d.plan_cmd_frame_id=frame;d.plan_cmd_id=id;
  d.plan_cmd_direction=store;d.plan_cmd_ddr_offset=ddr;
  d.plan_cmd_local_offset=local;d.plan_cmd_bytes=bytes;
  d.plan_cmd_valid=1;
  for(U n=0;n<100000;n++){
   auto s=step();if(s.cmd_ready){d.plan_cmd_valid=0;return;}
   need(n<99999,"plan command accept timeout");
  }
 }
 void complete(U epoch,U frame,U id,U kind,U status=0){
  for(U n=0;n<100000;n++){
   auto s=step();if(s.rsp_valid){
    need(s.epoch==epoch&&s.frame==frame&&s.id==id,"plan identity mismatch");
    need(s.kind==kind&&s.status==status,"plan completion mismatch");
    return;
   }
   need(n<99999,"plan completion timeout");
  }
 }
 void run(){
  // A paging hit and a direct local address coexist in one batch.
  U old=access(DDR);
  need(old==word(DDR),"DDR paged read");
  access(DDR,true,0x44332211);
  need(ram.data[DDR]!=0x11,"dirty page wrote back early");

  // The explicit LOAD must flush and invalidate an overlapping dirty page.
  submit(7,21,100,false,DDR,0,1033);
  complete(7,21,100,0);
  need(access(LOCAL)==0x44332211,"LOAD did not see dirty page");
  need(word(DDR)==0x44332211,"coherence writeback missing");
  need(access(LOCAL+1028)==word(DDR+1028),"unaligned length tail");

  // The local aperture spans physical banks. Four clients must be served in
  // the same cycle when their addresses are on distinct banks.
  access(LOCAL+32768,true,0x12345678);
  access(LOCAL+131072,true,0xabcddcba);
  access(LOCAL+233472,true,0x98765432);
  d.cnn_addr[0]=LOCAL;d.cnn_addr[1]=LOCAL+32768;
  d.cnn_addr[2]=LOCAL+131072;d.cnn_addr[3]=LOCAL+233472;
  d.cnn_valid=15;d.cnn_write=0;
  auto both=step();
  need((both.ready&15)==15,"four local clients not accepted together");
  d.cnn_valid=0;
  U seen=0;
  for(U n=0;n<20&&seen!=15;n++){
   auto s=step();
   if(s.response&1){need(s.data0==0x44332211,"local client 0 data");seen|=1;}
   if(s.response&2){need(s.data1==0x12345678,"local client 1 data");seen|=2;}
   if(s.response&4){need(s.data2==0xabcddcba,"local client 2 data");seen|=4;}
   if(s.response&8){need(s.data3==0x98765432,"local client 3 data");seen|=8;}
  }
  need(seen==15,"four local replies missing");

  // DMA to a different bank must leave compute ports usable while active.
  need(access(DDR+8192)==word(DDR+8192),"unrelated DDR page warmup");
  Q bursts_before=ram.read_bursts;
  submit(7,22,101,false,DDR+2048,65536,4096);
  for(U n=0;n<30000&&ram.read_bursts==bursts_before;n++){
   step();need(n<29999,"DMA did not start");
  }
  need(ram.reading,"DMA not reading when overlap test starts");
  U overlap=0;
  for(U n=0;n<30000;n++){
   d.cnn_valid=1;d.cnn_addr[0]=LOCAL;
   auto s=step();
   if(s.ready&1){need(ram.reading,"DMA completed before local access");
                  overlap++;d.cnn_valid=0;break;}
  }
  need(overlap==1,"local read blocked by DMA");
  bool local_reply=false;
  for(U n=0;n<20;n++){auto s=step();if(s.response&1){need(s.data0==0x44332211,"overlap data");local_reply=true;break;}}
  need(local_reply,"overlap reply missing");
  d.cnn_valid=1;d.cnn_addr[0]=DDR+8192;
  bool cached_hit_during_dma=false;
  for(U n=0;n<100;n++){
   auto s=step();if(s.ready&1){
    need(d.plan_busy,"DDR cache hit accepted after DMA ended");
    cached_hit_during_dma=true;break;
   }
  }
  need(cached_hit_during_dma,"resident DDR hit blocked by DMA");
  d.cnn_valid=0;
  bool cached_reply=false;
  for(U n=0;n<20;n++){
   auto s=step();if(s.response&1){
    need(s.data0==word(DDR+8192),"resident DDR hit data");
    cached_reply=true;break;
   }
  }
  need(cached_reply,"resident DDR hit reply missing");
  complete(7,22,101,0);
  need(csr(0x6c)>0,"hardware overlap counter stayed zero");
  need(access(LOCAL+65536)==word(DDR+2048),"second LOAD data");

  // STORE invalidates the old paged copy. A subsequent DDR read refills it.
  access(LOCAL,true,0xaabbccdd);
  submit(7,21,102,true,DDR,0,8);
  complete(7,21,102,2);
  need(word(DDR)==0xaabbccdd,"STORE did not reach DDR");
  need(access(DDR)==0xaabbccdd,"DDR pager returned stale value");
  need(csr(0x88)>=1033+4096 && csr(0x8c)==8,
       "explicit HP0 traffic counters");
  need(csr(0x80)>=csr(0x88) && csr(0x84)>=csr(0x8c),
       "total HP0 traffic counters");

  // Capabilities and a crossing-4KiB transfer use the same command path.
  need(csr(0x3c)==335872 && csr(0x40)==LOCAL && csr(0x44)==65536,
       "reported local geometry");
  need(csr(0x58)==0x01000000 && csr(0x60)==4,"reported DDR/queue caps");
  submit(8,22,104,false,DDR+4088,233472,32);
  complete(8,22,104,0);
  need(access(LOCAL+233472)==word(DDR+4088),"4K crossing first word");
  need(access(LOCAL+233472+28)==word(DDR+4116),"4K crossing last word");

  // Precheck failures are reported with the original command identity.
  submit(9,33,105,false,DDR+3,0,8);
  complete(9,33,105,0,4);
  submit(9,33,106,false,0x01000000-8,0,16);
  complete(9,33,106,0,3);
  submit(9,33,107,false,DDR,335872-4,8);
  complete(9,33,107,0,3);
  cfg(0x10,DDR+1024);cfg(0x14,1);
  submit(9,33,108,true,DDR,0,8);
  complete(9,33,108,2,8);
  cfg(0x14,0);

  // Completion backpressure keeps identities and data stable; credits bound
  // accepted commands even when every completion slot is occupied.
  d.plan_rsp_ready=0;
  for(U i=0;i<4;i++)submit(9+i,33+i,109+i,false,DDR,0,0);
  for(U n=0;n<20;n++)step();
  need(!d.plan_cmd_ready,"full queue did not backpressure");
  for(U n=0;n<5;n++){
   auto s=step();need(s.rsp_valid&&s.id==109&&s.status==2,
                      "backpressured completion changed");
  }
  d.plan_rsp_ready=1;
  for(U i=0;i<4;i++)complete(9+i,33+i,109+i,0,2);
  need(d.plan_drained,"storage not drained");
  // An AXI read error is attributed to its command, then the locked MOVER
  // can be recovered only after the old transaction has drained.
  inject_read_error=true;
  submit(10,44,113,false,DDR+3072,0,64);
  complete(10,44,113,0,5);
  need(d.plan_fault,"AXI error did not lock");
  for(U n=0;n<10000&&!d.plan_drained;n++){
   step();need(n<9999,"AXI error did not drain");
  }
  d.plan_recover=1;step();d.plan_recover=0;step();
  need(!d.plan_fault,"plan recovery failed");
  submit(10,44,114,false,DDR+3072,0,64);
  complete(10,44,114,0);
  need(access(LOCAL)==word(DDR+3072),"post-recovery LOAD");
  // A timeout may report failure before the AXI read eventually returns.
  // Drain the late response before accepting an unrelated epoch.
  hold_read_responses=true;
  submit(11,55,115,false,DDR+3072,0,64);
  complete(11,55,115,0,7);
  need(d.plan_fault&&!d.plan_drained,"timeout falsely reported drained");
  hold_read_responses=false;
  for(U n=0;n<10000&&!d.plan_drained;n++){
   step();need(n<9999,"late AXI response did not drain");
  }
  d.plan_recover=1;step();d.plan_recover=0;step();
  need(!d.plan_fault,"timeout recovery failed");
  submit(12,66,116,false,DDR+3072,0,64);
  complete(12,66,116,0);
  std::cout<<"PASS mixed DDR/local, coherence, 4-client bank access, DMA overlap, identity/backpressure"
           <<" cycles="<<cycle<<" overlap_cycles="<<csr(0x6c)
           <<" plan_dma_cycles="<<csr(0x94)
           <<" HP0_read="<<csr(0x80)<<" HP0_write="<<csr(0x84)
           <<" plan_read="<<csr(0x88)<<" plan_write="<<csr(0x8c)<<"\n";
 }
};
static Q throughput_case(bool overlap){
 Bench b;
 b.access(LOCAL,true,0x13572468);
 if(overlap)b.d.plan_rsp_ready=0;
 const Q start=b.cycle;
 b.submit(3,4,5,false,DDR+2048,65536,4096);
 if(!overlap)b.complete(3,4,5,0);
 for(U n=0;n<512;n++)need(b.access(LOCAL)==0x13572468,
                         "throughput case local data");
 if(overlap){
  need(b.csr(0x6c)>0,"throughput case did not overlap compute and DMA");
  b.d.plan_rsp_ready=1;b.complete(3,4,5,0);
 }
 return b.cycle-start;
}
int main(){try{
 Bench b;b.run();
 const Q serial=throughput_case(false),parallel=throughput_case(true);
 need(parallel<serial,"overlap did not reduce total cycles");
 std::cout<<"PASS short overlap comparison serial="<<serial
          <<" overlapping="<<parallel
          <<" saved="<<(serial-parallel)
          <<" gain_pct="<<(100.0*double(serial-parallel)/double(serial))<<"\n";
 return 0;}
 catch(const std::exception& e){std::cerr<<"FAIL "<<e.what()<<"\n";return 1;}}
