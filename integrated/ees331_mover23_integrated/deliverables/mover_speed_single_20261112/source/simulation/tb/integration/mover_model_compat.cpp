#include "legacy_axi_model.hpp"
#include "ees331_axi_mover_model.hpp"
#include <array>
#include <iostream>
#include <stdexcept>
struct D{
 uint32_t S_AXI_HP0_AWREADY=0,S_AXI_HP0_WREADY=0,S_AXI_HP0_ARREADY=0,S_AXI_HP0_RVALID=0,S_AXI_HP0_RID=0,S_AXI_HP0_RLAST=0,S_AXI_HP0_RRESP=0,S_AXI_HP0_BVALID=0,S_AXI_HP0_BID=0,S_AXI_HP0_BRESP=0;
 uint32_t S_AXI_HP0_AWADDR=0,S_AXI_HP0_AWID=0,S_AXI_HP0_AWLEN=0,S_AXI_HP0_AWSIZE=0,S_AXI_HP0_AWBURST=1,S_AXI_HP0_AWLOCK=0,S_AXI_HP0_AWVALID=0;
 uint32_t S_AXI_HP0_ARADDR=0,S_AXI_HP0_ARID=0,S_AXI_HP0_ARLEN=0,S_AXI_HP0_ARSIZE=0,S_AXI_HP0_ARBURST=1,S_AXI_HP0_ARLOCK=0,S_AXI_HP0_ARVALID=0;
 uint32_t S_AXI_HP0_WSTRB=0,S_AXI_HP0_WID=0,S_AXI_HP0_WLAST=1,S_AXI_HP0_WVALID=0,S_AXI_HP0_BREADY=0,S_AXI_HP0_RREADY=0;
 uint64_t S_AXI_HP0_RDATA=0,S_AXI_HP0_WDATA=0;
};
auto outputs(D&d){return std::array<uint64_t,11>{d.S_AXI_HP0_AWREADY,d.S_AXI_HP0_WREADY,d.S_AXI_HP0_ARREADY,d.S_AXI_HP0_RVALID,d.S_AXI_HP0_RDATA,d.S_AXI_HP0_RID,d.S_AXI_HP0_RLAST,d.S_AXI_HP0_RRESP,d.S_AXI_HP0_BVALID,d.S_AXI_HP0_BID,d.S_AXI_HP0_BRESP};}
int main(){try{
 D a,b;LegacyAxiDdr<D>old(a);AxiDdr<D>next(b);old.stress=next.stress=true;uint64_t cycle=0;
 for(unsigned i=0;i<65536;i++)old.data[i]=next.data[i]=uint8_t(i*37+i/8);
 for(unsigned n=0;n<512;n++){
  unsigned size=n%4,bytes=1u<<size,address=(n*97)%60000;address&=~(bytes-1);
  bool wr=n&1,as=false,ds=false,done=false;
  a.S_AXI_HP0_AWADDR=a.S_AXI_HP0_ARADDR=0x10000000+address;
  a.S_AXI_HP0_AWSIZE=a.S_AXI_HP0_ARSIZE=size;a.S_AXI_HP0_AWID=a.S_AXI_HP0_WID=a.S_AXI_HP0_ARID=n%64;
  a.S_AXI_HP0_AWVALID=a.S_AXI_HP0_WVALID=wr;a.S_AXI_HP0_ARVALID=!wr;
  a.S_AXI_HP0_WDATA=0x123456789abcdef0ULL^uint64_t(n*733);a.S_AXI_HP0_WSTRB=((1u<<bytes)-1)<<(address&7);
  for(unsigned guard=0;!done;guard++){
   if(guard>1000)throw std::runtime_error("model timeout");a.S_AXI_HP0_BREADY=cycle%7!=0;a.S_AXI_HP0_RREADY=cycle%9!=0;b=a;
   old.drive();next.drive();if(outputs(a)!=outputs(b))throw std::runtime_error("model output/timing mismatch");
   bool aw=a.S_AXI_HP0_AWVALID&&a.S_AXI_HP0_AWREADY,w=a.S_AXI_HP0_WVALID&&a.S_AXI_HP0_WREADY,ar=a.S_AXI_HP0_ARVALID&&a.S_AXI_HP0_ARREADY;
   done=wr?(a.S_AXI_HP0_BVALID&&a.S_AXI_HP0_BREADY):(a.S_AXI_HP0_RVALID&&a.S_AXI_HP0_RREADY);
   old.capture();next.capture();if(old.seed!=next.seed||old.read_bytes!=next.read_bytes||old.write_bytes!=next.write_bytes||old.stall_cycles!=next.stall_cycles)throw std::runtime_error("model random/counter mismatch");
   if(aw)a.S_AXI_HP0_AWVALID=0;if(w)a.S_AXI_HP0_WVALID=0;if(ar)a.S_AXI_HP0_ARVALID=0;cycle++;
  }
 }
 if(old.data!=next.data)throw std::runtime_error("model memory mismatch");
 std::cout<<"PASS old/new DDR models: 512 single-beat transfers, every ready/valid/data/last/ID/response cycle, random state and memory identical; cycles="<<cycle<<"\n";
}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
