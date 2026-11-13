#include "Vtile_local_ram.h"
#include "verilated.h"
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <vector>
constexpr unsigned BYTES=401408,WORDS=BYTES/4;
static void need(bool c,const char*s){if(!c)throw std::runtime_error(s);}
struct Bench{
 Vtile_local_ram d;std::vector<uint32_t> ref=std::vector<uint32_t>(WORDS);
 void tick(){d.clk=0;d.eval();d.clk=1;d.eval();d.clk=0;d.eval();}
 Bench(){d.rst_n=0;d.comp_req=d.comp_we=d.dma_valid=d.dma_write=0;d.comp_addr=d.dma_addr=d.comp_wdata=d.dma_wdata=0;d.comp_wstrb=d.dma_wstrb=0;tick();d.rst_n=1;tick();}
 void run(){
  for(unsigned i=0;i<WORDS;i++){
   ref[i]=(i*0x9e3779b9u)^0x733badaa;
   d.comp_req=d.comp_we=1;d.comp_addr=i*4;d.comp_wdata=ref[i];d.comp_wstrb=15;tick();need(!d.comp_error,"compute write error");
  }
  d.comp_req=0;d.dma_valid=1;d.dma_write=0;
  for(unsigned i=0;i<WORDS;i++){d.dma_addr=i*4;d.eval();need(d.dma_ready,"DMA not ready");tick();need(d.dma_rsp_valid&&!d.dma_error&&d.dma_rdata==ref[i],"full capacity DMA read mismatch");}
  d.dma_write=1;
  for(unsigned i=0;i<WORDS;i++){
   unsigned byte=i%4,mask=255u<<(byte*8);uint32_t value=(~ref[i])&mask;
   d.dma_addr=i*4;d.dma_wdata=value;d.dma_wstrb=1u<<byte;tick();ref[i]=(ref[i]&~mask)|value;
  }
  d.dma_valid=0;d.comp_we=0;d.comp_req=1;
  for(unsigned i=0;i<WORDS;i++){d.comp_addr=i*4;tick();need(!d.comp_error&&d.comp_rdata==ref[i],"full capacity compute read/byte mask mismatch");}
  d.dma_valid=1;d.dma_write=0;
  for(unsigned i=0;i<1000;i++){
   unsigned a=(i&1)?(256*1024/4+i):(WORDS-1-i),b=i;
   d.comp_addr=a*4;d.dma_addr=b*4;tick();need(d.comp_rdata==ref[a]&&d.dma_rdata==ref[b]&&d.dma_rsp_valid,"simultaneous cross-bank read mismatch");
  }
  d.comp_we=1;d.comp_addr=d.dma_addr=BYTES-4;d.comp_wstrb=15;d.comp_wdata=0x10203040;
  d.dma_write=1;d.dma_wstrb=15;d.dma_wdata=0xff;d.eval();need(!d.dma_ready,"same-word collision not blocked");tick();need(!d.dma_rsp_valid,"blocked DMA response");ref.back()=0x10203040;
  d.dma_valid=0;d.comp_we=0;tick();need(d.comp_rdata==ref.back(),"compute collision winner");
  d.comp_addr=BYTES;tick();need(d.comp_error,"end address not rejected");d.comp_addr=1;tick();need(d.comp_error,"unaligned address not rejected");
  d.comp_req=0;d.dma_valid=1;d.dma_addr=BYTES;tick();need(d.dma_rsp_valid&&d.dma_error,"DMA end address not rejected");
  d.dma_valid=0;d.rst_n=0;tick();d.rst_n=1;tick();d.comp_req=1;d.comp_addr=BYTES-4;tick();need(d.comp_rdata==ref.back(),"RAM was reset");
  std::cout<<"PASS all "<<WORDS<<" words of 392 KiB: both ports, byte masks, three bank boundaries, concurrent reads, collision, range/alignment, reset retention\n";
 }
};
int main(){try{Bench b;b.run();return 0;}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<"\n";return 1;}}
