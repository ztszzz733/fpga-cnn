#include "Vcnn_paged_mover.h"
#include "verilated.h"
#include <iostream>
#include <stdexcept>
#include <string>
static void need(bool ok,const char* why){if(!ok)throw std::runtime_error(why);}
struct Bench{
 Vcnn_paged_mover d;
 unsigned cycles=0;
 Bench(){
  d.clk=0;d.rst_n=0;d.cnn_valid=0;d.cnn_write=0;d.cnn_byte=0;d.cnn_cancel=0;
  d.cache_csr_addr=0;d.cache_csr_wdata=0;d.cache_csr_re=0;d.cache_csr_we=0;
  for(int i=0;i<23;i++){d.cnn_addr[i]=0;d.cnn_wdata[i]=0;}
  d.S_AXI_HP0_AWREADY=0;d.S_AXI_HP0_WREADY=0;d.S_AXI_HP0_BVALID=0;
  d.S_AXI_HP0_ARREADY=1;d.S_AXI_HP0_RVALID=0;d.S_AXI_HP0_RLAST=0;
  d.S_AXI_HP0_RDATA=0;d.S_AXI_HP0_BID=0;d.S_AXI_HP0_RID=0;
  d.S_AXI_HP0_BRESP=0;d.S_AXI_HP0_RRESP=0;
  for(int i=0;i<5;i++)tick();d.rst_n=1;tick();
 }
 void tick(){need(cycles<10000,"test watchdog");d.clk=0;d.eval();d.clk=1;d.eval();d.clk=0;d.eval();cycles++;}
 void csr(unsigned a,unsigned v){d.cache_csr_addr=a;d.cache_csr_wdata=v;d.cache_csr_we=1;tick();d.cache_csr_we=0;tick();}
 void request(unsigned owner,unsigned addr,bool write){
  d.cnn_addr[owner]=addr;d.cnn_wdata[owner]=0x1234;
  d.cnn_valid=1u<<owner;d.cnn_write=write?(1u<<owner):0;
  d.eval();need((d.cnn_ready>>owner)&1,"request not accepted");
  tick();d.cnn_valid=0;d.cnn_write=0;
 }
 void run(){
  request(22,1,false);tick();need(d.cnn_mem_fault,"unaligned word was not rejected");
  need(d.cnn_response==0,"bad request produced response");
  csr(4,3);need(!d.cnn_mem_fault,"fault clear failed");
  csr(0x10,0x100);csr(0x14,1);
  request(7,0x80,true);tick();need(d.cnn_mem_fault,"protected write was not rejected");
  csr(4,3);need(!d.cnn_mem_fault,"protected fault clear failed");
  request(3,0x1000,false);
  bool ar=false;
  for(int i=0;i<40;i++){
   d.eval();if(d.S_AXI_HP0_ARVALID){tick();ar=true;break;}tick();
  }
  need(ar,"MOVER did not issue DDR read");
  d.S_AXI_HP0_RVALID=1;d.S_AXI_HP0_RLAST=1;d.S_AXI_HP0_RRESP=2;
  d.S_AXI_HP0_RID=0;d.S_AXI_HP0_RDATA=0;
  tick();d.S_AXI_HP0_RVALID=0;d.S_AXI_HP0_RRESP=0;
  bool failed=false;
  for(int i=0;i<40;i++){need(d.cnn_response==0,"AXI error produced CNN response");if(d.cnn_mem_fault){failed=true;break;}tick();}
  need(failed,"AXI error did not reach CNN fault");
  csr(4,3);need(!d.cnn_mem_fault,"MOVER fault recovery failed");
  d.cache_csr_addr=0;d.eval();
  need((d.cache_csr_rdata&8)==0,"fault status did not clear");
  // Cancel after acceptance. The already issued DDR page fill must drain,
  // while the cancelled CNN request receives no response.
  request(5,0x2000,false);d.cnn_cancel=1;tick();d.cnn_cancel=0;
  unsigned read_beats=0;bool pending_read=false,drained=false;
  for(int i=0;i<5000;i++){
   d.eval();need(d.cnn_response==0,"cancelled request produced response");
   if(pending_read){
    d.S_AXI_HP0_RVALID=1;d.S_AXI_HP0_RLAST=1;d.S_AXI_HP0_RRESP=0;
    d.S_AXI_HP0_RDATA=0;tick();d.S_AXI_HP0_RVALID=0;
    pending_read=false;read_beats++;
   }else if(d.S_AXI_HP0_ARVALID){tick();pending_read=true;}
   else tick();
   d.cache_csr_addr=0;d.eval();
   if(read_beats==128 && (d.cache_csr_rdata&2)==0){drained=true;break;}
  }
  need(drained&&read_beats==128&&!d.cnn_mem_fault,"cancelled page fill did not drain cleanly");
  std::cout<<"PASS mover23 faults: unaligned, readonly, AXI RRESP, recovery, cancel-drain beats="<<read_beats<<" cycles="<<cycles<<"\n";
 }
};
int main(){try{Bench b;b.run();return 0;}catch(const std::exception&e){std::cerr<<"FAIL mover23 faults: "<<e.what()<<"\n";return 1;}}
