// Testbench PS/DDR memory, not an arithmetic oracle. Data comes only from the
// fixture/PS uploads and real AXI writes. Random pauses are deterministic.
#pragma once
#include <cstdint>
#include <vector>
#include <stdexcept>
#include <array>
template<class D> struct AxiDdr {
 using U32=uint32_t;using U64=uint64_t;
 D& d;std::vector<uint8_t> data;
 bool reading=false,writing=false,bvalid=false,rvalid=false;
 U32 ra=0,wa=0,ri=0,wi=0,rid=0,wid=0,rdelay=0,bdelay=0;
 U64 rd=0,read_bursts=0,write_bursts=0,read_bytes=0,write_bytes=0,stall_cycles=0;
 U32 seed=733;bool stress=false;
 bool held_aw=false,held_ar=false,held_w=false;
 std::array<U64,6> old_aw{},old_ar{},old_w{};
 explicit AxiDdr(D& x,size_t bytes=16777216):d(x),data(bytes,0xa5){}
 void need(bool c,const char* s){if(!c)throw std::runtime_error(s);}
 U32 rnd(){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
 U32 offset(U32 a){need(a>=0x10000000u&&U64(a)+64<=0x11000000ULL,"AXI physical window");return a-0x10000000u;}
 U64 load(U32 a){U64 v=0;for(unsigned b=0;b<8;b++)v|=U64(data.at(a+b))<<(8*b);return v;}
 void drive(){
  const U32 r=rnd();
  d.S_AXI_HP0_AWREADY=!writing&&!bvalid&&(!stress||(r&7)!=0);
  d.S_AXI_HP0_WREADY=writing&&!bvalid&&(!stress||(r&0x38)!=0);
  d.S_AXI_HP0_ARREADY=!reading&&!rvalid&&(!stress||(r&0x1c0)!=0);
  if(reading&&!rvalid){if(rdelay)--rdelay;else if(!stress||(r&3)){rd=load(ra+ri*8);rvalid=true;}}
  d.S_AXI_HP0_RVALID=rvalid;d.S_AXI_HP0_RDATA=rd;d.S_AXI_HP0_RID=rid;
  d.S_AXI_HP0_RLAST=ri==7;d.S_AXI_HP0_RRESP=0;
  if(bdelay)--bdelay;
  d.S_AXI_HP0_BVALID=bvalid&&bdelay==0;d.S_AXI_HP0_BID=wid;d.S_AXI_HP0_BRESP=0;
 }
 void capture(){
  std::array<U64,6> aw={d.S_AXI_HP0_AWADDR,d.S_AXI_HP0_AWID,d.S_AXI_HP0_AWLEN,d.S_AXI_HP0_AWSIZE,d.S_AXI_HP0_AWBURST,d.S_AXI_HP0_AWLOCK};
  std::array<U64,6> ar={d.S_AXI_HP0_ARADDR,d.S_AXI_HP0_ARID,d.S_AXI_HP0_ARLEN,d.S_AXI_HP0_ARSIZE,d.S_AXI_HP0_ARBURST,d.S_AXI_HP0_ARLOCK};
  std::array<U64,6> w={d.S_AXI_HP0_WDATA,d.S_AXI_HP0_WSTRB,d.S_AXI_HP0_WID,d.S_AXI_HP0_WLAST,0,0};
  need(!held_aw||(d.S_AXI_HP0_AWVALID&&aw==old_aw),"AW payload changed while stalled");
  need(!held_ar||(d.S_AXI_HP0_ARVALID&&ar==old_ar),"AR payload changed while stalled");
  need(!held_w||(d.S_AXI_HP0_WVALID&&w==old_w),"W payload changed while stalled");
  held_aw=d.S_AXI_HP0_AWVALID&&!d.S_AXI_HP0_AWREADY;held_ar=d.S_AXI_HP0_ARVALID&&!d.S_AXI_HP0_ARREADY;held_w=d.S_AXI_HP0_WVALID&&!d.S_AXI_HP0_WREADY;
  old_aw=aw;old_ar=ar;old_w=w;if(held_aw||held_ar||held_w)++stall_cycles;
  if(d.S_AXI_HP0_BVALID&&d.S_AXI_HP0_BREADY)bvalid=false;
  if(d.S_AXI_HP0_RVALID&&d.S_AXI_HP0_RREADY){rvalid=false;read_bytes+=8;if(ri==7)reading=false;else{++ri;rdelay=stress?rnd()%4:0;}}
  if(d.S_AXI_HP0_AWVALID&&d.S_AXI_HP0_AWREADY){
   need(!writing&&!bvalid&&d.S_AXI_HP0_AWLEN==7&&d.S_AXI_HP0_AWSIZE==3&&d.S_AXI_HP0_AWBURST==1&&!(d.S_AXI_HP0_AWADDR&63),"AW burst geometry");
   writing=true;wa=offset(d.S_AXI_HP0_AWADDR);wi=0;wid=d.S_AXI_HP0_AWID;++write_bursts;
  }
  if(d.S_AXI_HP0_WVALID&&d.S_AXI_HP0_WREADY){
   need(writing&&wi<8&&d.S_AXI_HP0_WID==wid&&bool(d.S_AXI_HP0_WLAST)==(wi==7),"AXI write sequence");
   for(unsigned b=0;b<8;b++)if((d.S_AXI_HP0_WSTRB>>b)&1){data[wa+wi*8+b]=uint8_t(d.S_AXI_HP0_WDATA>>(b*8));++write_bytes;}
   if(wi==7){writing=false;bvalid=true;bdelay=stress?rnd()%12:2;}else ++wi;
  }
  if(d.S_AXI_HP0_ARVALID&&d.S_AXI_HP0_ARREADY){
   need(!reading&&!rvalid&&d.S_AXI_HP0_ARLEN==7&&d.S_AXI_HP0_ARSIZE==3&&d.S_AXI_HP0_ARBURST==1&&!(d.S_AXI_HP0_ARADDR&63),"AR burst geometry");
   reading=true;ra=offset(d.S_AXI_HP0_ARADDR);ri=0;rid=d.S_AXI_HP0_ARID;rdelay=stress?rnd()%20:5;++read_bursts;
  }
 }
};
