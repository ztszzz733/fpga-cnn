#include "Vdata_mover.h"
#include "verilated.h"
#include <vector>
#include <array>
#include <iostream>
#include <fstream>
#include <filesystem>
#include <stdexcept>
#include <random>
using U=uint32_t;using Q=uint64_t;using Bytes=std::vector<uint8_t>;
struct Bench{
 Vdata_mover d;Bytes mem,local;std::mt19937 rng{733};Q ticks=0,transactions=0,local_ops=0;
 bool ar=false,aw=false,wd=false,lr=false;U ra=0,wa=0,la=0;unsigned rs=0,ws=0,rdly=0,bdly=0,ldly=0;Q wbuf=0;U strobes=0;
 bool lwrite=false;U ldata=0,lmask=0;int injection=0;U begin=0,end=0;bool check_range=true,expect_timeout=false;unsigned timeout_observed=0;
 std::array<Q,4> prev{};std::array<bool,4> hold{};
 void need(bool v,const char*s){if(!v)throw std::runtime_error(std::string(s)+" at "+std::to_string(ticks));}
 void reset(){d.rst_n=0;d.cmd_valid=0;d.rsp_ready=0;d.recover=0;d.enable=1;ar=aw=wd=lr=false;hold={};tick();d.rst_n=1;tick();}
 void tick(){
  d.clk=0;d.arready=!ar && rng()%4!=0;d.awready=!aw && rng()%3!=0;d.wready=!wd && rng()%4!=0;
  d.rvalid=ar && rdly==0;d.rlast=1;d.rid=injection==3?1:0;d.rresp=injection==1?2:0;d.rdata=0;
  if(d.rvalid){for(unsigned i=0;i<(1u<<rs);i++)d.rdata|=Q(mem.at(ra+i))<<(8*((ra+i)&7));}
  d.bvalid=aw && wd && bdly==0;d.bid=injection==4?1:0;d.bresp=injection==2?2:0;
  d.local_ready=!lr && rng()%3!=0;d.local_rsp_valid=lr&&ldly==0;d.local_error=injection==5;d.local_rdata=0;
  if(d.local_rsp_valid && !lwrite)for(unsigned i=0;i<4;i++)d.local_rdata|=U(local.at(la+i))<<(i*8);
  d.eval();
  std::array<bool,4> valid={bool(d.arvalid),bool(d.awvalid),bool(d.wvalid),bool(d.local_valid)};
  std::array<bool,4> ready={bool(d.arready),bool(d.awready),bool(d.wready),bool(d.local_ready)};
  std::array<Q,4> payload={Q(d.araddr)|(Q(d.arsize)<<32),Q(d.awaddr)|(Q(d.awsize)<<32),d.wdata ^ Q(d.wstrb),Q(d.local_addr)|(Q(d.local_wdata)<<32)};
  for(unsigned i=0;i<4;i++){if(hold[i])need(valid[i]&&prev[i]==payload[i],"payload stability");hold[i]=valid[i]&&!ready[i];prev[i]=payload[i];}
  bool take_ar=d.arvalid&&d.arready,take_r=d.rvalid&&d.rready,take_aw=d.awvalid&&d.awready,take_w=d.wvalid&&d.wready,take_b=d.bvalid&&d.bready,take_l=d.local_valid&&d.local_ready,take_lr=d.local_rsp_valid;
  if(take_ar){ra=d.araddr-d.cfg_ddr_base;rs=d.arsize;need(d.arlen==0 && d.arburst==1 && d.arid==0,"AR shape");need((ra&((1u<<rs)-1))==0,"read alignment");if(check_range)need(ra>=begin && Q(ra)+(1u<<rs)<=end,"exact read range");need((d.araddr&4095)+(1u<<rs)<=4096,"read 4K boundary");}
  if(take_aw){wa=d.awaddr-d.cfg_ddr_base;ws=d.awsize;need(d.awlen==0&&d.awburst==1&&d.awid==0,"AW shape");need((wa&((1u<<ws)-1))==0,"write alignment");if(check_range)need(wa>=begin&&Q(wa)+(1u<<ws)<=end,"exact write range");need((d.awaddr&4095)+(1u<<ws)<=4096,"write 4K boundary");}
  if(take_w){wbuf=d.wdata;strobes=d.wstrb;need(d.wlast&&d.wid==0,"W shape");}
  if(take_l){la=d.local_addr;lwrite=d.local_write;ldata=d.local_wdata;lmask=d.local_wstrb;need(la%4==0 && la+4<=local.size(),"local bounds");local_ops++;}
  if(take_lr && lwrite && injection!=5){for(unsigned i=0;i<4;i++)if(lmask>>i&1)local.at(la+i)=ldata>>(i*8);}
  if(take_b){need(strobes==(((1u<<(1u<<ws))-1)<<(wa&7)),"exact write lanes");for(unsigned i=0;i<8;i++)if(strobes>>i&1)mem.at((wa&~7u)+i)=wbuf>>(i*8);transactions++;}
  if(expect_timeout && d.fault_locked && !d.drained){timeout_observed++;need(!d.cmd_ready && !d.rsp_valid,"no completion before drain");}
  d.clk=1;d.eval();ticks++;
  if(ar&&rdly)rdly--;if(aw&&wd&&bdly)bdly--;if(lr&&ldly)ldly--;
  if(take_r){ar=false;transactions++;}if(take_b){aw=false;wd=false;}
  if(take_lr)lr=false;
  if(take_ar){ar=true;rdly=injection==6?1100:rng()%9;}
  if(take_aw){aw=true;bdly=injection==7?1100:10+rng()%12;}
  if(take_w)wd=true;
  if(take_l){lr=true;ldly=injection==8?1100:rng()%5;}
 }
 void recover(){need(!ar&&!aw&&!wd&&!lr&&d.drained,"drained before recovery");d.recover=1;tick();d.recover=0;need(!d.fault_locked,"recover");}
 void transfer(U s,U dst,U n,U flags,U status=0){
  begin=flags&1?dst:s;end=begin+n;d.cmd_src=s;d.cmd_dst=dst;d.cmd_bytes=n;d.cmd_flags=flags;
  d.cmd_valid=1;d.rsp_ready=0;d.eval();need(d.cmd_ready,"command ready");tick();d.cmd_valid=0;
  for(unsigned count=0;!d.rsp_valid;count++){need(count<400000,"test timeout");tick();need(!d.cmd_ready,"single outstanding");}
  need(d.drained&&!ar&&!aw&&!wd&&!lr,"response after all transactions");
  need(d.rsp_status==status,"status");need(d.rsp_bytes_done==(status?0:n),"bytes done");
  for(unsigned i=0;i<7;i++){tick();need(d.rsp_valid&&!d.cmd_ready&&d.rsp_status==status,"held response");}
  d.rsp_ready=1;tick();d.rsp_ready=0;
 }
};
U u32(std::ifstream&f){U a;f.read((char*)&a,4);if(!f)throw std::runtime_error("vector file");return a;}
int main(int argc,char**argv){try{
 Bench b;b.mem.resize(65536);b.local.resize(65536);b.d.cfg_ddr_base=0x10000000;b.d.cfg_ddr_bytes=65536;b.d.cfg_local_bytes=65536;b.reset();
 std::ifstream f(std::filesystem::path(argv[1])/"transfers.bin",std::ios::binary);U cases=u32(f);
 for(U c=0;c<cases;c++){
  U nd=u32(f),nl=u32(f),s=u32(f),dst=u32(f),n=u32(f),flags=u32(f);b.mem.resize(nd);b.local.resize(nl);f.read((char*)b.mem.data(),nd);f.read((char*)b.local.data(),nl);
  b.d.cfg_ddr_bytes=nd;b.d.cfg_local_bytes=nl;auto md=b.mem,ml=b.local;
  for(U i=0;i<n;i++)if(flags)md.at(dst+i)=ml.at(s+i);else ml.at(dst+i)=md.at(s+i);
  b.transfer(s,dst,n,flags);b.need(b.mem==md&&b.local==ml,"package bytes + guard regions");
 }
 b.mem.resize(65536);b.local.resize(65536);b.d.cfg_ddr_bytes=65536;b.d.cfg_local_bytes=65536;
 for(U i=0;i<65536;i++){b.mem[i]=b.rng();b.local[i]=b.rng();}
 for(U k=0;k<100;k++){
  U s=4088+(k%2)*8192,l=17+k%8,n=1+b.rng()%257;auto md=b.mem,ml=b.local;bool wr=k%2;
  for(U i=0;i<n;i++)if(wr)md[s+i]=ml[l+i];else ml[l+i]=md[s+i];
  b.transfer(wr?l:s,wr?s:l,n,wr);b.need(b.mem==md&&b.local==ml,"random cross-page bytes");
 }
 Q before=b.transactions;
 b.transfer(0,0,1,2,1);b.transfer(0,0,0,0,2);b.transfer(65528,0,9,0,3);b.transfer(0,65535,2,0,3);b.transfer(0xfffffff8,0,16,0,3);b.transfer(1,0,8,0,4);
 b.d.cfg_ddr_base=0xfffffff8;b.transfer(8,0,8,0,3);b.transfer(0,0,9,0,3);b.d.cfg_ddr_base=0x10000000;b.need(before==b.transactions,"illegal commands have no bus effects");
 for(int inj=1;inj<=8;inj++){
  b.injection=inj;b.expect_timeout=inj>=6;bool wr=inj==2||inj==4||inj==7;
  U status=inj==1||inj==3?5:inj==2||inj==4?6:inj==5?10:7;
  b.transfer(16,24,16,wr,status);b.need(b.d.fault_locked&&!b.d.cmd_ready,"error lock");b.injection=0;b.expect_timeout=false;b.recover();b.transfer(16,24,8,0);
 }
 b.need(b.timeout_observed>0,"timeout drain exercised");
 b.d.enable=0;b.d.eval();b.need(!b.d.cmd_ready,"DDR not ready gate");
 std::cout<<"PASS data_mover package_cases="<<cases<<" random_cross_page=100 invalid=8 errors=8 timeouts=3 cycles="<<b.ticks<<" axi_transactions="<<b.transactions<<" local_operations="<<b.local_ops<<"\n";
}catch(std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
