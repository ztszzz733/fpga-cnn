#include "Vcpu_download.h"
#include "verilated.h"
#include <iostream>
#include <stdexcept>
Vcpu_download d;
void ck(bool b,const char*s){if(!b)throw std::runtime_error(s);}
void tick(){d.clk=0;d.eval();d.clk=1;d.eval();ck(!d.memory_error,"CPU address/timing error");}
uint32_t ld(bool data,uint32_t a,bool wr,uint32_t v=0,bool error=false){
 d.target_data=data;d.ld_addr=a;d.ld_wdata=v;d.ld_wstrb=15;d.ld_write=wr;d.ld_rsp_ready=0;d.ld_valid=1;d.eval();ck(d.ld_ready,"load ready");tick();d.ld_valid=0;
 ck(d.ld_rsp_valid && bool(d.ld_error)==error,"load response");uint32_t r=d.ld_rdata;d.ld_rsp_ready=1;tick();d.ld_rsp_ready=0;return r;
}
uint32_t st(unsigned reg,unsigned off,unsigned funct){return ((off>>5)<<25)|(reg<<20)|(1<<15)|(funct<<12)|((off&31)<<7)|0x23;}
int main(){try{
 d.rst_n=0;d.app_run=0;tick();d.rst_n=1;tick();
 uint32_t program[]={0x000100b7,0x1000a103,0x1040a183,0x00310233,0x00720213,st(4,264,2),0x05a00293,st(5,269,0),0x10d0c303,st(6,272,2),st(4,8,2),0x00100393,st(7,12,2),0x0000006f};
 for(unsigned i=0;i<sizeof(program)/4;i++){ld(false,i*4,true,program[i]);ck(ld(false,i*4,false)==program[i],"program verify");}
 ld(true,0x10100,true,35);for(unsigned a=0x10104;a<=0x10110;a+=4)ld(true,a,true,0);
 for(int run=0;run<2;run++){
  d.app_run=1;ld(false,0,true,0,true);
  int cycles=0;while(!d.done){ck(cycles++<200,"real CPU completion timeout");tick();}
  for(int i=0;i<20;i++)tick();d.app_run=0;tick();
  ck(ld(true,0x10108,false)==42,"data+BSS+arithmetic");ck(ld(true,0x1010c,false)==0x5a00,"SB byte address");ck(ld(true,0x10110,false)==0x5a,"LBU and store");ck(ld(true,0x10008,false)==42,"mailbox result");
  ck(ld(false,0,false)==program[0],"program retained after application reset");
 }
 std::cout<<"PASS real CPU Control+Datapath downloaded RV32I, data/BSS, SB/LBU, mailbox, restart twice\n";
}catch(std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
