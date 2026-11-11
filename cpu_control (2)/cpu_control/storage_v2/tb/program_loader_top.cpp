#include "Vprogram_loader_top.h"
#include "verilated.h"
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
using U=uint32_t;
static Vprogram_loader_top d;
static U cycles=0;
static void need(bool v,const std::string&s){if(!v)throw std::runtime_error(s+" at "+std::to_string(cycles));}
static void tick(){d.clk=0;d.eval();d.clk=1;d.eval();cycles++;}
static U csr(U off,bool write,U value=0,U expected=0,unsigned be=15){
 d.bus_addr=0x40001000+off;d.bus_write=write;d.bus_wdata=value;d.bus_wstrb=be;
 d.bus_valid=1;d.bus_rsp_ready=0;d.eval();need(d.bus_ready,"CSR ready");tick();d.bus_valid=0;
 need(d.bus_rsp_valid && d.bus_status==expected,"CSR response status");U data=d.bus_rdata;
 for(int i=0;i<2;i++){tick();need(d.bus_rsp_valid&&d.bus_rdata==data&&d.bus_status==expected,"CSR response hold");}
 d.bus_rsp_ready=1;tick();d.bus_rsp_ready=0;return data;
}
static U download(bool ram,U addr,bool write,U value=0,unsigned strb=15,bool error=false){
 csr(0,true,ram);csr(4,true,addr);csr(8,true,value);csr(12,true,strb);csr(20,true,write?1:2);
 U status=0;
 for(int i=0;i<50;i++){status=csr(16,false);if(status&2)break;}
 need((status&2)!=0 && bool(status&4)==error,"loader done/error");
 U data=csr(24,false);csr(28,true,1);need((csr(16,false)&6)==0,"clear sticky result");
 return data;
}
int main(){try{
 d.rst_n=0;d.app_reset=1;d.app_halted=1;d.bus_valid=0;d.bus_rsp_ready=0;
 d.imem_cpu_re=0;d.ram_cpu_re=0;d.ram_cpu_we=0;tick();d.rst_n=1;tick();
 U program[]={0x00100093,0x00208113,0x00202023,0x0000006f};
 for(U i=0;i<4;i++)download(false,4*i,true,program[i]);
 for(U i=0;i<4;i++)need(download(false,4*i,false)==program[i],"IMEM verify");
 download(true,0x10000,true,35);download(true,0x10004,true,0);
 need(download(true,0x10000,false)==35,".data load");
 need(download(true,0x10004,false)==0,".bss clear");
 download(true,0x10008,true,0x11223344);download(true,0x10008,true,0xaa0000bb,9);
 need(download(true,0x10008,false)==0xaa2233bb,"byte write");
 download(false,65536,true,0xdeadbeef,15,true);
 download(true,0x14000,true,0xdeadbeef,15,true);
 need(download(false,0,false)==program[0],"bounds reject retained IMEM");
 csr(4,true,1);csr(20,true,2);for(int i=0;i<50;i++)if(csr(16,false)&2)break;
 need((csr(16,false)&6)==6,"unaligned loader error");csr(28,true,1);
 csr(4,true,0);csr(20,true,3,1);csr(4,true,0,1,3);
 d.app_reset=0;d.app_halted=0;
 csr(20,true,1,3);need((csr(16,false)&6)==0,"running command rejected");
 d.imem_cpu_addr=0;d.imem_cpu_re=1;tick();need(d.imem_cpu_rdata==program[0]&&!d.imem_cpu_error,"CPU IMEM read");d.imem_cpu_re=0;
 d.ram_cpu_addr=0x10000;d.ram_cpu_re=1;tick();need(d.ram_cpu_rdata==35&&!d.ram_cpu_error,"CPU .data");d.ram_cpu_re=0;
 d.ram_cpu_addr=0x10004;d.ram_cpu_re=1;tick();need(d.ram_cpu_rdata==0,"CPU .bss");d.ram_cpu_re=0;
 d.app_reset=1;tick();d.app_reset=0;d.imem_cpu_re=1;tick();
 need(d.imem_cpu_rdata==program[0],"app reset retains IMEM");d.imem_cpu_re=0;
 d.app_halted=1;need(download(true,0x10000,false)==35,"app reset retains RAM");
 std::cout<<"PASS program_loader_csr IMEM and RAM download/readback, bounds, busy, reset cycles="<<cycles<<"\n";
}catch(std::exception&e){std::cerr<<"FAIL program_loader_csr: "<<e.what()<<"\n";return 1;}}
