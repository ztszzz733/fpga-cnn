#include "Vcnn_paged_mover.h"
#include "verilated.h"
#include "ees331_axi_mover_model.hpp"
#include <iostream>
#include <stdexcept>
using U32=uint32_t;
static void need(bool ok,const char*s){if(!ok)throw std::runtime_error(s);}
struct Bench{
 Vcnn_paged_mover d;AxiDdr<Vcnn_paged_mover> ram{d};unsigned cycle=0;
 Bench(){
  d.rst_n=0;d.cnn_valid=d.cnn_write=d.cnn_byte=d.cnn_cancel=0;
  d.cache_csr_we=d.cache_csr_re=0;d.cache_csr_addr=d.cache_csr_wdata=0;
  for(int k=0;k<12;k++)d.cnn_addr[k]=d.cnn_wdata[k]=0;
  ram.stress=true;for(int i=0;i<5;i++)tick();d.rst_n=1;tick();
 }
 void tick(){need(cycle++<2000000,"watchdog");d.clk=0;ram.drive();d.eval();if(d.rst_n)ram.capture();d.clk=1;d.eval();d.clk=0;d.eval();}
 U32 csr(U32 a){d.cache_csr_addr=a;d.cache_csr_re=1;d.eval();U32 v=d.cache_csr_rdata;d.cache_csr_re=0;return v;}
 void cfg(U32 a,U32 v){d.cache_csr_addr=a;d.cache_csr_wdata=v;d.cache_csr_we=1;tick();d.cache_csr_we=0;tick();}
 U32 access(unsigned owner,U32 a,bool wr=false,U32 v=0,bool byte=false){
  d.cnn_addr[owner]=a;d.cnn_wdata[owner]=v;d.cnn_write=wr?(1u<<owner):0;d.cnn_byte=byte?(1u<<owner):0;d.cnn_valid=1u<<owner;
  for(unsigned i=0;;i++){need(i<30000,"accept timeout");d.eval();bool h=(d.cnn_ready>>owner)&1;tick();if(h)break;}
  d.cnn_valid=d.cnn_write=d.cnn_byte=0;
  for(unsigned i=0;;i++){need(i<30000&&!d.cnn_mem_fault,"response timeout/fault");d.eval();if((d.cnn_response>>owner)&1){U32 r=d.cnn_rdata[owner];tick();return r;}tick();}
 }
 void run(){
  need(csr(0x3c)==3072,"non-power-of-two capacity CSR");
  for(unsigned pass=0;pass<3;pass++){
   for(unsigned i=0;i<9;i++)access(i%12,0x10000+i*1024+1020,true,0x12340000+pass*256+i);
   for(int i=8;i>=0;i--)need(access(i%12,0x10000+i*1024+1020)==0x12340000+pass*256+i,"victim wrap/writeback corruption");
  }
  access(11,0x10001,true,0x7b,true);need(access(10,0x10000)==0xa5a57ba5,"byte enables/neighbor preservation");
  cfg(8,0x10000);cfg(12,9*1024);cfg(4,2);
  while(csr(0)&2)tick();
  need(ram.data[0x10001]==0x7b,"fence did not flush byte");
  for(unsigned i=0;i<9;i++){
   U32 a=0x10000+i*1024+1020,v=0;for(int j=0;j<4;j++)v|=U32(ram.data[a+j])<<(8*j);
   need(v==0x12340200+i,"DDR fence output");
   need(access(i%12,a)==v,"invalidate/refill corruption");
  }
  need(csr(0x24)>30&&ram.read_bytes>0&&ram.write_bytes>0,"paging paths not covered");
  std::cout<<"PASS 3-slot non-power-of-two paging: repeated victim wrap, last word, byte enables, writeback, fence, invalidate, refill; cycles="<<cycle<<"\n";
 }
};
int main(){try{Bench b;b.run();return 0;}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<"\n";return 1;}}
