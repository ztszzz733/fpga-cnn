#include "Vdata_mover.h"
#include "verilated.h"
#define S_AXI_HP0_AWREADY awready
#define S_AXI_HP0_WREADY wready
#define S_AXI_HP0_ARREADY arready
#define S_AXI_HP0_RVALID rvalid
#define S_AXI_HP0_RDATA rdata
#define S_AXI_HP0_RID rid
#define S_AXI_HP0_RLAST rlast
#define S_AXI_HP0_RRESP rresp
#define S_AXI_HP0_BVALID bvalid
#define S_AXI_HP0_BID bid
#define S_AXI_HP0_BRESP bresp
#define S_AXI_HP0_AWADDR awaddr
#define S_AXI_HP0_AWID awid
#define S_AXI_HP0_AWLEN awlen
#define S_AXI_HP0_AWSIZE awsize
#define S_AXI_HP0_AWBURST awburst
#define S_AXI_HP0_AWLOCK awlock
#define S_AXI_HP0_ARADDR araddr
#define S_AXI_HP0_ARID arid
#define S_AXI_HP0_ARLEN arlen
#define S_AXI_HP0_ARSIZE arsize
#define S_AXI_HP0_ARBURST arburst
#define S_AXI_HP0_ARLOCK arlock
#define S_AXI_HP0_WDATA wdata
#define S_AXI_HP0_WSTRB wstrb
#define S_AXI_HP0_WID wid
#define S_AXI_HP0_WLAST wlast
#define S_AXI_HP0_AWVALID awvalid
#define S_AXI_HP0_WVALID wvalid
#define S_AXI_HP0_ARVALID arvalid
#define S_AXI_HP0_BREADY bready
#define S_AXI_HP0_RREADY rready
#include "arm_schedule/ees331_axi_mover_model.hpp"
#include <algorithm>
#include <deque>
#include <fstream>
#include <iostream>
#include <string>

static void need(bool v,const char* text){if(!v)throw std::runtime_error(text);}
struct Bench {
 Vdata_mover d;
 AxiDdr<Vdata_mover> ram{d,65536};
 std::vector<uint8_t> local=std::vector<uint8_t>(401408);
 struct Reply{unsigned due;uint32_t data;bool error;};
 std::deque<Reply> replies;
 unsigned cycle=0,accepted=0,completed=0,latency=1,error_at=~0u,block_until=0;
 unsigned longest_local=0,longest_w=0,local_run=0,w_run=0,last_local=~0u,last_w=~0u;
 bool stress=false,axi_error=false,block_ar=false,block_b=false,hold_responses=false;
 bool held_local=false;uint32_t held_addr=0,held_data=0;
 unsigned rng=733;
 unsigned rnd(){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
 Bench(){
  d.rst_n=0;d.enable=1;d.recover=0;d.cmd_valid=0;d.rsp_ready=0;
  d.cfg_ddr_base=0x10000000;d.cfg_ddr_bytes=65536;d.cfg_local_bytes=local.size();
  for(unsigned i=0;i<65536;i++)ram.data[i]=uint8_t((i*17)^(i>>3)^0x39);
  for(unsigned i=0;i<local.size();i++)local[i]=uint8_t((i*23)^(i>>7)^0xa6);
  for(int i=0;i<4;i++)tick();d.rst_n=1;tick();
 }
 void tick(){
  need(cycle<200000,"global watchdog");d.clk=0;ram.stress=stress;ram.drive();
  if(axi_error){if(d.cmd_flags&1)d.bresp=2;else d.rresp=2;}
  if(block_ar && cycle<block_until)d.arready=0;
  if(block_b && cycle<block_until)d.bvalid=0;
  d.local_ready=(!stress || (rnd()%4)!=0) && replies.size()<8;
  d.local_rsp_valid=!replies.empty() && replies.front().due<=cycle &&
                    (!hold_responses || cycle>=block_until);
  d.local_error=d.local_rsp_valid && replies.front().error;
  d.local_rdata=d.local_rsp_valid?replies.front().data:0;
  d.eval();
  if(held_local && !d.fault_locked)need(d.local_valid && d.local_addr==held_addr &&
                                     d.local_wdata==held_data,"local payload changed under stall");
  held_local=d.local_valid&&!d.local_ready;held_addr=d.local_addr;held_data=d.local_wdata;
  bool take=d.local_valid&&d.local_ready,done=d.local_rsp_valid;
  if(done){replies.pop_front();completed++;}
  if(take){
   need(d.local_addr%4==0 && d.local_addr+4<=local.size(),"local range");
   uint32_t value=0;for(unsigned b=0;b<4;b++)value|=uint32_t(local[d.local_addr+b])<<(8*b);
   bool err=accepted==error_at;
   if(d.local_write && !err){need(d.local_wstrb==15,"fill strobes");
    for(unsigned b=0;b<4;b++)local[d.local_addr+b]=uint8_t(d.local_wdata>>(8*b));}
   unsigned due=cycle+(stress?(1+rnd()%latency):latency);
   if(!replies.empty())due=std::max(due,replies.back().due+1);
   replies.push_back({due,value,err});accepted++;
   local_run=last_local+1==cycle?local_run+1:1;last_local=cycle;
   longest_local=std::max(longest_local,local_run);
  }
  if(d.wvalid&&d.wready){w_run=last_w+1==cycle?w_run+1:1;last_w=cycle;longest_w=std::max(longest_w,w_run);}
  if(d.rst_n)ram.capture();d.clk=1;d.eval();d.clk=0;d.eval();cycle++;
 }
 unsigned command(bool wb,unsigned dd=3072,unsigned loc=200704,unsigned flags=~0u,unsigned bytes=1024){
  d.cmd_src=wb?loc:dd;d.cmd_dst=wb?dd:loc;d.cmd_flags=flags==~0u?unsigned(wb):flags;
  d.cmd_bytes=bytes;d.cmd_valid=1;unsigned start=cycle;
  for(unsigned n=0;;n++){need(n<12000,"command accept watchdog");d.eval();bool ready=d.cmd_ready;tick();if(ready)break;}
  d.cmd_valid=0;
  for(unsigned n=0;!d.rsp_valid;n++){need(n<12000,"command completion watchdog");tick();}
  need(replies.empty() && accepted==completed,"completion before local drain");
  unsigned elapsed=cycle-start;uint32_t status=d.rsp_status,done_bytes=d.rsp_bytes_done;
  // The response and result must survive response backpressure.
  for(unsigned n=0;n<3;n++){tick();need(d.rsp_valid&&d.rsp_status==status&&d.rsp_bytes_done==done_bytes,"response stability");}
  d.rsp_ready=1;tick();d.rsp_ready=0;need(d.drained,"not drained at idle");return elapsed;
 }
 void recover(){d.recover=1;tick();d.recover=0;tick();need(!d.fault_locked&&d.cmd_ready,"recover failed");}
};
int main(int argc,char** argv){try{
 unsigned cases=0,fill=0,wb=0,local_streak=0,w_streak=0;
 for(bool dir:{false,true})for(unsigned latency:{1u,2u,5u,9u})for(unsigned seed=0;seed<8;seed++){
  Bench b;b.stress=seed!=0;b.ram.seed=733+seed;b.rng=991+seed;b.latency=latency;
  unsigned loc=std::array<unsigned,4>{0,199680,200704,400384}[seed%4],dd=(seed%4)*1024;
  auto before_local=b.local,before_ddr=b.ram.data;
  unsigned cycles=b.command(dir,dd,loc);need(b.d.rsp_status==0&&b.d.rsp_bytes_done==1024,"success status");
  need(b.accepted==256,"word count");
  if(dir){std::copy(before_local.begin()+loc,before_local.begin()+loc+1024,before_ddr.begin()+dd);
   need(b.ram.data==before_ddr&&b.local==before_local,"writeback data/guard mismatch");}
  else{std::copy(before_ddr.begin()+dd,before_ddr.begin()+dd+1024,before_local.begin()+loc);
   need(b.local==before_local&&b.ram.data==before_ddr,"fill data/guard mismatch");}
  if(seed==0&&latency==1){if(dir)wb=cycles;else fill=cycles;local_streak=std::max(local_streak,b.longest_local);w_streak=std::max(w_streak,b.longest_w);}
  cases++;
 }
 for(bool dir:{false,true})for(unsigned error:{0u,7u,31u,255u}){
  Bench b;b.latency=5;b.error_at=error;b.command(dir);need(b.d.rsp_status==10&&b.d.fault_locked,"local error status");
  b.recover();b.error_at=~0u;b.command(false);need(b.d.rsp_status==0,"restart after local error");cases++;
 }
 for(bool dir:{false,true}){Bench b;b.axi_error=true;b.command(dir);
  need(b.d.rsp_status==(dir?6u:5u)&&b.d.fault_locked,"AXI error status");
  b.axi_error=false;b.recover();b.command(false);need(b.d.rsp_status==0,"restart after AXI error");cases++;}
 for(bool dir:{false,true}){Bench b;b.hold_responses=true;b.block_until=b.cycle+160;b.command(dir);
  need(b.d.rsp_status==7&&b.d.fault_locked,"local timeout status");b.hold_responses=false;b.recover();
  b.command(false);need(b.d.rsp_status==0,"restart after local timeout");cases++;}
 {Bench b;b.block_ar=true;b.block_until=b.cycle+80;b.command(false);need(b.d.rsp_status==7&&b.d.fault_locked,"AR timeout");cases++;}
 {Bench b;b.block_b=true;b.block_until=b.cycle+1600;b.command(true);need(b.d.rsp_status==7&&b.d.fault_locked,"B timeout");cases++;}
 for(unsigned mode=0;mode<4;mode++){Bench b;
  b.command(false,mode==3?1:3072,mode==2?401408:200704,mode==0?2:0,mode==1?1023:1024);
  need(b.d.rsp_status==mode+1,"invalid command code");need(b.accepted==0,"invalid command accessed local RAM");cases++;}
 std::cout<<"{\"status\":\"PASS\",\"cases\":"<<cases<<",\"fill_cycles\":"<<fill<<",\"writeback_cycles\":"<<wb
          <<",\"longest_local_stream\":"<<local_streak<<",\"longest_axi_write_stream\":"<<w_streak<<"}"<<std::endl;
 return 0;
}catch(const std::exception& e){std::cerr<<"FAIL: "<<e.what()<<std::endl;return 1;}}
