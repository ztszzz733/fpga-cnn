#include "Vdownload_ram.h"
#include "verilated.h"
#include <iostream>
#include <stdexcept>
#ifndef RAM_BYTES
#define RAM_BYTES 16384
#endif
#ifndef RAM_BASE
#define RAM_BASE 65536
#endif
#ifndef ROM_CPU
#define ROM_CPU 0
#endif
Vdownload_ram d;
void ck(bool v,const char*s){if(!v)throw std::runtime_error(s);}
void tick(){d.clk=0;d.eval();d.clk=1;d.eval();}
uint32_t load(uint32_t a,bool wr,uint32_t data=0,unsigned mask=15,bool err=false){
 d.ld_addr=a;d.ld_write=wr;d.ld_wdata=data;d.ld_wstrb=mask;d.ld_valid=1;d.ld_rsp_ready=0;d.eval();ck(d.ld_ready,"loader ready");tick();d.ld_valid=0;
 ck(d.ld_rsp_valid && bool(d.ld_error)==err,"loader response");uint32_t value=d.ld_rdata;
 for(int i=0;i<4;i++){tick();ck(d.ld_rsp_valid && d.ld_rdata==value && !d.ld_ready,"response hold");}
 d.ld_rsp_ready=1;tick();d.ld_rsp_ready=0;return value;
}
int main(){try{
 d.rst_n=0;d.app_reset=1;d.app_halted=1;tick();d.rst_n=1;tick();
 // Tiny RV32I instruction sequence, data initializers and zero-filled BSS.
 uint32_t image[]={0x00100093,0x00208113,0x00202023,0x0000006f};
 for(unsigned a=0;a<16;a+=4)load(RAM_BASE+a,true,image[a/4]);
 for(unsigned a=16;a<80;a+=4)load(RAM_BASE+a,true,0);
 load(RAM_BASE+RAM_BYTES-4,true,0x89abcdef);
 ck(load(RAM_BASE+RAM_BYTES-4,false)==0x89abcdef,"last word");
 load(RAM_BASE+4,true,0xaa00bb00,10);ck(load(RAM_BASE+4,false)==0xaa20bb13,"byte lanes");
 load(RAM_BASE+RAM_BYTES,true,0xdeadbeef,15,true);load(RAM_BASE-4,false,0,15,true);load(RAM_BASE+1,false,0,15,true);
 d.app_halted=0;d.app_reset=0;load(RAM_BASE,true,0,15,true);
 d.cpu_re=1;d.cpu_addr=RAM_BASE;tick();ck(d.cpu_rdata==image[0] && !d.cpu_error,"one-cycle read");
 d.cpu_addr=RAM_BASE+16;tick();ck(d.cpu_rdata==0,"BSS");
 d.cpu_addr=RAM_BASE+RAM_BYTES;tick();ck(d.cpu_error && d.cpu_rdata==0,"CPU bounds");
 d.cpu_addr=RAM_BASE;d.app_halted=1;load(RAM_BASE,true,0,15,true);ck(d.cpu_rdata==image[0],"CPU priority");d.cpu_re=0;
 d.app_reset=1;tick();d.app_reset=0;d.cpu_re=1;tick();ck(d.cpu_rdata==image[0],"application reset retains memory");
 d.cpu_re=0;d.cpu_we=1;d.cpu_addr=RAM_BASE+16;d.cpu_wdata=0x12345678;d.cpu_wstrb=15;tick();ck(bool(d.cpu_error)==bool(ROM_CPU),"CPU write policy");d.cpu_we=0;
 ck(load(RAM_BASE+16,false)==(ROM_CPU?0:0x12345678),"CPU store");
 d.rst_n=0;tick();d.rst_n=1;tick();ck(load(RAM_BASE,false)==image[0],"service reset retains RAM");
 std::cout<<"PASS download_ram bytes="<<RAM_BYTES<<" base="<<RAM_BASE<<" readonly="<<ROM_CPU<<"\n";
}catch(std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
