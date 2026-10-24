#include "Vdatasram_ddr_subsystem.h"
#include "verilated.h"
#include <array>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <random>
#include <stdexcept>
#include <vector>

static void require(bool yes,const char* why){if(!yes)throw std::runtime_error(why);}
struct Sample {uint32_t ready,response;std::array<uint32_t,10> data;};
struct Sim {
 Vdatasram_ddr_subsystem d;
 std::mt19937 rng{733};
 std::vector<uint8_t> memory=std::vector<uint8_t>(65536),shadow=std::vector<uint8_t>(65536);
 uint64_t cycles=0,read_bursts=0,write_bursts=0,checks=0;
 bool ar=false,aw=false,rv=false,bv=false,pause_reads=false,pause_b=false;
 bool next_read_error=false,next_write_error=false,read_error=false,write_error=false;
 int rbeat=0,wbeats=0;
 uint32_t ra=0,wa=0;
 uint64_t held_r=0;
 std::array<uint64_t,8> write_data{};
 bool old_stall_aw=false,old_stall_ar=false,old_stall_w=false;
 uint32_t old_aw=0,old_ar=0;
 uint64_t old_w=0;bool old_last=false;
 Sim(){
  for(unsigned a=0;a<memory.size();a++) memory[a]=shadow[a]=uint8_t((a*37u)^(a>>7));
  d.clk=0;d.rst_n=0;d.cnn_valid=d.cnn_write=d.cnn_byte=d.cnn_cancel=0;
  d.dmem_re=d.dmem_we=d.dmem_addr=d.dmem_wdata=d.dmem_wstrb=0;
  d.cache_csr_re=d.cache_csr_we=d.cache_csr_addr=d.cache_csr_wdata=0;
  d.S_AXI_HP0_RID=d.S_AXI_HP0_BID=0;
  for(int i=0;i<5;i++)tick();d.rst_n=1;
  for(int i=0;i<100;i++){tick();if(csr(0)&1)return;}throw std::runtime_error("cache init timeout");
 }
 uint32_t word(const std::vector<uint8_t>& m,unsigned a){
  return uint32_t(m.at(a))|uint32_t(m.at(a+1))<<8|uint32_t(m.at(a+2))<<16|uint32_t(m.at(a+3))<<24;
 }
 uint64_t quad(unsigned a){return uint64_t(word(memory,a))|uint64_t(word(memory,a+4))<<32;}
 Sample tick(){
  if(ar && !rv && !pause_reads && rng()%4){rv=true;held_r=quad(ra+rbeat*8);}
  d.clk=0;
  d.S_AXI_HP0_ARREADY=!ar && (rng()%3!=0);
  d.S_AXI_HP0_AWREADY=!aw && (rng()%3!=0);
  d.S_AXI_HP0_WREADY=wbeats<8 && (rng()%3!=0);
  d.S_AXI_HP0_RVALID=rv;d.S_AXI_HP0_RDATA=held_r;
  d.S_AXI_HP0_RLAST=rbeat==7;d.S_AXI_HP0_RRESP=read_error?2:0;
  d.S_AXI_HP0_BVALID=bv&&!pause_b;d.S_AXI_HP0_BRESP=write_error?2:0;
  d.eval();
  Sample s{d.cnn_ready,d.cnn_response,{}};for(int i=0;i<10;i++)s.data[i]=d.cnn_rdata[i];
  if(old_stall_aw)require(d.S_AXI_HP0_AWVALID&&d.S_AXI_HP0_AWADDR==old_aw,"AW unstable under stall");
  if(old_stall_ar)require(d.S_AXI_HP0_ARVALID&&d.S_AXI_HP0_ARADDR==old_ar,"AR unstable under stall");
  if(old_stall_w)require(d.S_AXI_HP0_WVALID&&d.S_AXI_HP0_WDATA==old_w&&bool(d.S_AXI_HP0_WLAST)==old_last,"W unstable under stall");
  old_stall_aw=d.S_AXI_HP0_AWVALID&&!d.S_AXI_HP0_AWREADY;old_aw=d.S_AXI_HP0_AWADDR;
  old_stall_ar=d.S_AXI_HP0_ARVALID&&!d.S_AXI_HP0_ARREADY;old_ar=d.S_AXI_HP0_ARADDR;
  old_stall_w=d.S_AXI_HP0_WVALID&&!d.S_AXI_HP0_WREADY;old_w=d.S_AXI_HP0_WDATA;old_last=d.S_AXI_HP0_WLAST;
  bool ah=d.S_AXI_HP0_AWVALID&&d.S_AXI_HP0_AWREADY;
  bool wh=d.S_AXI_HP0_WVALID&&d.S_AXI_HP0_WREADY;
  bool bh=d.S_AXI_HP0_BVALID&&d.S_AXI_HP0_BREADY;
  bool rh=d.S_AXI_HP0_RVALID&&d.S_AXI_HP0_RREADY;
  bool arh=d.S_AXI_HP0_ARVALID&&d.S_AXI_HP0_ARREADY;
  uint32_t awaddr=d.S_AXI_HP0_AWADDR,araddr=d.S_AXI_HP0_ARADDR;
  uint64_t wd=d.S_AXI_HP0_WDATA;bool wl=d.S_AXI_HP0_WLAST;
  if(ah||arh){
   uint32_t a=ah?awaddr:araddr;require(a>=0x10000000&&a<0x10010000&&(a&63)==0,"DDR address range/alignment");
   require(d.S_AXI_HP0_AWLEN==7&&d.S_AXI_HP0_ARLEN==7&&d.S_AXI_HP0_AWSIZE==3&&d.S_AXI_HP0_ARSIZE==3,"AXI burst geometry");
   require(d.S_AXI_HP0_AWBURST==1&&d.S_AXI_HP0_ARBURST==1&&d.S_AXI_HP0_AWID==0&&d.S_AXI_HP0_ARID==0,"AXI attributes");
  }
  if(wh)require(d.S_AXI_HP0_WSTRB==255&&d.S_AXI_HP0_WID==0&&wl==(wbeats==7),"AXI WID/WSTRB/WLAST");
  d.clk=1;d.eval();cycles++;
  if(arh){ar=true;ra=araddr-0x10000000;rbeat=0;read_error=next_read_error;next_read_error=false;read_bursts++;}
  if(rh){rv=false;if(rbeat==7){ar=false;rbeat=0;read_error=false;}else rbeat++;}
  if(ah){aw=true;wa=awaddr-0x10000000;write_error=next_write_error;next_write_error=false;}
  if(wh)write_data[wbeats++]=wd;
  if(aw&&wbeats==8&&!bv){
   for(int i=0;i<8;i++)for(int j=0;j<8;j++)memory.at(wa+i*8+j)=uint8_t(write_data[i]>>(j*8));
   bv=true;write_bursts++;
  }
  if(bh){aw=false;wbeats=0;bv=false;write_error=false;}
  if(cycles>500000)throw std::runtime_error("watchdog");
  return s;
 }
 uint32_t csr(unsigned addr){d.cache_csr_addr=addr;d.cache_csr_re=1;d.eval();uint32_t v=d.cache_csr_rdata;d.cache_csr_re=0;return v;}
 void wr(unsigned addr,uint32_t v){d.cache_csr_addr=addr;d.cache_csr_wdata=v;d.cache_csr_we=1;tick();d.cache_csr_we=0;}
 void idle(){for(int i=0;i<30000;i++){if(!(csr(0)&2))return;tick();}throw std::runtime_error("cache idle timeout");}
 void maint(unsigned start,unsigned length,int command=1){idle();wr(8,start);wr(12,length);wr(4,command);idle();require(!(csr(0)&12),"maintenance fault");}
 uint32_t access(int owner,unsigned addr,bool write=false,uint32_t data=0,bool byte=false,bool fault=false){
  d.cnn_valid=1u<<owner;d.cnn_write=write?1u<<owner:0;d.cnn_byte=byte?1u<<owner:0;d.cnn_addr[owner]=addr;d.cnn_wdata[owner]=data;
  bool accepted=false;uint64_t accepted_at=0;
  for(int n=0;n<20000;n++){
   auto s=tick();
   if(s.ready&(1u<<owner)){require(!accepted,"duplicate accept");accepted=true;accepted_at=cycles;d.cnn_valid=0;}
   if(s.response&(1u<<owner)){require(accepted&&cycles>accepted_at,"same-cycle/unsolicited response");require(!fault,"response for fault");checks++;return s.data[owner];}
   if(d.cnn_mem_fault){require(fault,"unexpected CNN memory fault");d.cnn_valid=0;idle();checks++;return 0;}
  }throw std::runtime_error("CNN access timeout");
 }
 void clear_error(){idle();wr(4,3);require(!(csr(0)&12),"error did not clear");}
 void check_read(int c,unsigned a,bool byte=false){uint32_t expected=byte?uint32_t(int32_t(int8_t(shadow.at(a)))):word(shadow,a);require(access(c,a,false,0,byte)==expected,"CNN value mismatch");}
 void store(int c,unsigned a,uint32_t v,bool byte=false){access(c,a,true,v,byte);for(int i=0;i<(byte?1:4);i++)shadow[a+i]=uint8_t(v>>(8*i));}
 void batch(){
  uint32_t pending=1023,accepted=0,finished=0;std::array<uint32_t,10> expected{};std::array<uint64_t,10> at{};
  d.cnn_valid=pending;d.cnn_write=0;d.cnn_byte=0;
  for(int i=0;i<10;i++){
   bool byte=rng()%2,write=rng()%2;unsigned a=(rng()%4096)*4+(byte?rng()%4:0);
   d.cnn_addr[i]=a;d.cnn_wdata[i]=rng();if(byte)d.cnn_byte|=1u<<i;if(write)d.cnn_write|=1u<<i;
  }
  for(int n=0;n<40000&&finished!=1023;n++){
   auto s=tick();
   for(int i=0;i<10;i++)if(s.ready&(1u<<i)){
    require(!(accepted&(1u<<i)),"batch duplicate accept");accepted|=1u<<i;pending&=~(1u<<i);at[i]=cycles;
    unsigned a=d.cnn_addr[i];bool byte=(d.cnn_byte>>i)&1,write=(d.cnn_write>>i)&1;
    if(write){expected[i]=0;for(int j=0;j<(byte?1:4);j++)shadow[a+j]=uint8_t(d.cnn_wdata[i]>>(8*j));}
    else expected[i]=byte?uint32_t(int32_t(int8_t(shadow[a]))):word(shadow,a);
   }
   for(int i=0;i<10;i++)if(s.response&(1u<<i)){
    require((accepted&(1u<<i))&&!(finished&(1u<<i))&&cycles>at[i],"batch response ownership/order");
    require(s.data[i]==expected[i],"batch numerical mismatch");finished|=1u<<i;checks++;
   }
   d.cnn_valid=pending;require(!d.cnn_mem_fault,"batch fault");
  }require(finished==1023,"batch timeout");
 }
};
int main(int argc,char**argv){
 Verilated::commandArgs(argc,argv);
 try{
  Sim s;
  // CPU local memory has fixed one-clock reads and byte strobes, no DDR traffic.
  s.d.dmem_addr=20;s.d.dmem_we=1;s.d.dmem_wstrb=15;s.d.dmem_wdata=0x11223344;s.tick();
  s.d.dmem_wstrb=2;s.d.dmem_wdata=0x0000aa00;s.tick();s.d.dmem_we=0;s.d.dmem_re=1;s.tick();
  require(s.d.dmem_rdata==0x1122aa44,"CPU byte strobes/fixed read latency");s.d.dmem_re=0;
  require(s.read_bursts==0&&s.write_bursts==0,"CPU local access went to DDR");
  s.check_read(0,64);auto rb=s.read_bursts;s.check_read(1,64);require(s.read_bursts==rb,"cached read missed");
  s.store(2,65,0x80,true);s.check_read(3,65,true);require(s.memory[65]!=0x80,"write-through instead of WB");
  s.maint(64,64);require(s.memory[65]==0x80,"fence failed to flush byte write");
  auto wb=s.write_bursts;s.maint(65,0,2);require(s.write_bursts==wb,"zero length maintenance changed memory");
  s.store(0,0,0xaabbccdd);s.store(1,512,0xdeadbeef);s.check_read(2,1024);
  require(s.word(s.memory,0)==0xaabbccdd,"dirty conflict eviction failed");
  for(int i=0;i<80;i++)s.batch();
  s.maint(0,65536);require(s.memory==s.shadow,"fenced DDR differs from complete logical scoreboard");
  // Invalidate a partial range; future read must see the independently changed PS data.
  s.check_read(0,40000);s.maint(40001,1,2);s.memory[40000]=s.shadow[40000]=0xf7;s.check_read(1,40000);
  // Reject illegal requests without aliasing them into low DDR.
  s.access(0,65536,false,0,false,true);s.clear_error();
  s.access(0,3,false,0,false,true);s.clear_error();
  s.wr(16,256);s.wr(20,1);s.access(0,4,true,123,false,true);s.clear_error();s.wr(20,0);
  s.check_read(1,4);
  // A result fence can be enqueued during another frame's miss. Its range is
  // captured atomically by command, independently of later staging writes.
  s.maint(0,65536,2);s.store(7,0x2040,0x19283746);s.pause_reads=true;
  s.d.cnn_valid=1u<<8;s.d.cnn_write=0;s.d.cnn_byte=0;s.d.cnn_addr[8]=0x3000;
  bool queued_accept=false;for(int n=0;n<100;n++){auto q=s.tick();if(q.ready&(1u<<8)){queued_accept=true;s.d.cnn_valid=0;}if(s.ar)break;}
  require(queued_accept&&s.ar,"queued fence did not start concurrent read");
  s.wr(8,0x2040);s.wr(12,4);s.wr(4,1);s.wr(8,0x3000);s.wr(12,64);
  require(!(s.csr(0)&12)&&(s.csr(0)&2),"queued fence rejected during CNN busy");
  s.pause_reads=false;bool queued_response=false;
  for(int n=0;n<30000;n++){auto q=s.tick();if(q.response&(1u<<8)){queued_response=true;require(q.data[8]==s.word(s.shadow,0x3000),"queued fence changed concurrent read");}if(!(s.csr(0)&2))break;}
  require(queued_response&&s.word(s.memory,0x2040)==0x19283746,"queued fence/snapshot visibility failed");
  // Cancel a live read, keep AXI draining, and suppress all stale CNN responses.
  s.maint(0,65536,2);s.pause_reads=true;
  s.d.cnn_valid=1;s.d.cnn_write=0;s.d.cnn_byte=0;s.d.cnn_addr[0]=32000;
  bool accepted=false;for(int n=0;n<100;n++){auto q=s.tick();if(q.ready&1){accepted=true;s.d.cnn_valid=0;}if(s.ar)break;}
  require(accepted&&s.ar,"cancel test did not reach live AXI read");s.d.cnn_cancel=1;
  for(int i=0;i<9;i++){auto q=s.tick();require(!q.response,"response during cancel");require(s.csr(0)&16,"cancel drain not busy");}
  s.pause_reads=false;
  for(int i=0;i<100;i++){auto q=s.tick();require(!q.response,"stale response after cancel");if(!(s.csr(0)&2))break;}
  require(!(s.csr(0)&2),"cancel did not drain");s.d.cnn_cancel=0;s.check_read(0,32000);
  // Cancellation also drains dirty eviction all the way through its B reply.
  s.maint(0,65536,2);s.store(0,0,0xc001cafe);s.store(1,512,0x33557799);s.pause_b=true;
  s.d.cnn_valid=1u<<2;s.d.cnn_write=0;s.d.cnn_byte=0;s.d.cnn_addr[2]=1024;
  bool wb_accepted=false;for(int n=0;n<200;n++){auto q=s.tick();if(q.ready&(1u<<2)){wb_accepted=true;s.d.cnn_valid=0;}if(s.bv)break;}
  require(wb_accepted&&s.bv,"cancel test did not reach held write response");s.d.cnn_cancel=1;
  s.d.cnn_valid=1u<<9;s.d.cnn_addr[9]=2048;
  for(int n=0;n<10;n++){auto q=s.tick();require(!q.ready&&!q.response&&(s.csr(0)&16),"write cancel accepted new request/response before drain");}
  s.d.cnn_valid=0;s.pause_b=false;
  for(int n=0;n<100;n++){auto q=s.tick();require(!q.response,"canceled writeback returned stale CNN response");if(!(s.csr(0)&2))break;}
  require(!(s.csr(0)&2)&&s.word(s.memory,0)==0xc001cafe,"dirty writeback not drained");
  s.d.cnn_cancel=0;s.check_read(2,1024);
  // Slave read/write errors are latched; failed writeback retains dirty metadata.
  s.maint(0,65536,2);s.next_read_error=true;s.access(1,20000,false,0,false,true);s.clear_error();s.check_read(1,20000);
  s.store(2,20000,0x76543210);s.next_write_error=true;s.idle();s.wr(8,20000);s.wr(12,4);s.wr(4,1);s.idle();
  require(s.d.cnn_mem_fault&&(s.csr(0)&4),"B error not propagated");s.clear_error();s.maint(20000,4);s.check_read(2,20000);
  // A 64B line crossing the 4KiB boundary never occurs: line-aligned bursts.
  s.store(3,4092,0x01020304);s.store(4,4096,0x05060708);s.maint(4092,8);s.check_read(5,4092);s.check_read(6,4096);
  s.maint(0,65536);require(s.memory==s.shadow,"final DDR scoreboard mismatch");
  std::ofstream f("metrics.json");f<<"{\"cycles\":"<<s.cycles<<",\"checks\":"<<s.checks<<",\"read_bursts\":"<<s.read_bursts<<",\"write_bursts\":"<<s.write_bursts<<"}\n";
  std::cout<<"PASS cnn_ddr_cache checks="<<s.checks<<" cycles="<<s.cycles<<" read_bursts="<<s.read_bursts<<" write_bursts="<<s.write_bursts<<"\n";
  return 0;
 }catch(const std::exception&e){std::cerr<<"FAIL cnn_ddr_cache: "<<e.what()<<"\n";return 1;}
}
