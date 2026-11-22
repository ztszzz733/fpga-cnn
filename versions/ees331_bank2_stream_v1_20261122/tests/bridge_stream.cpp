#include "Vsimple_mem_bridge.h"
#include "verilated.h"
#include <algorithm>
#include <deque>
#include <iostream>
#include <stdexcept>
#include <vector>
static void need(bool x,const char*s){if(!x)throw std::runtime_error(s);}
struct Bench{
 Vsimple_mem_bridge d;
 struct Reply{unsigned due;uint32_t value;};
 std::deque<Reply> q;
 std::vector<uint32_t> mem=std::vector<uint32_t>(4096);
 unsigned cycles=0,latency=9,issued=0,returned=0,max_pending=0;
 unsigned random=733;bool allow_requests=true,stress=false,held=false;
 uint32_t held_addr=0,held_data=0;unsigned held_control=0;
 unsigned rnd(){random^=random<<13;random^=random>>17;random^=random<<5;return random;}
 Bench(){for(unsigned i=0;i<mem.size();i++)mem[i]=0x12340000u+i*13;
  d.rst_n=0;d.__SYM__abort=0;d.c_valid=0;d.c_write=0;d.c_byte=0;d.c_read_beats=1;
  for(int i=0;i<3;i++)tick();d.rst_n=1;tick();}
 void tick(){
  need(cycles<20000,"bridge global watchdog");d.clk=0;
  d.m_ready=allow_requests&&(!stress||rnd()%4!=0);
  bool reply=!q.empty()&&q.front().due<=cycles;
  d.m_response=reply;d.m_rdata=reply?q.front().value:0;d.eval();
  unsigned ctl=unsigned(d.m_write)|(unsigned(d.m_byte)<<1);
  if(held)need(d.m_valid&&d.m_addr==held_addr&&d.m_wdata==held_data&&ctl==held_control,"external offer changed while stalled");
  bool take=d.m_valid&&d.m_ready;
  uint32_t value=0;
  if(take){
   need(d.m_addr%4==0&&d.m_addr/4<mem.size()&&!d.m_byte,"request geometry");
   value=mem[d.m_addr/4];if(d.m_write)mem[d.m_addr/4]=d.m_wdata;
   issued++;
  }
  bool immediate=take&&!reply&&q.empty()&&latency==0;
  if(immediate){d.m_response=1;d.m_rdata=value;d.eval();returned++;}
  if(reply){q.pop_front();returned++;}
  if(take&&!immediate){unsigned due=cycles+std::max(1u,latency);
   if(!q.empty())due=std::max(due,q.back().due+1);q.push_back({due,value});}
  max_pending=std::max(max_pending,unsigned(q.size()));
  held=d.m_valid&&!d.m_ready;held_addr=d.m_addr;held_data=d.m_wdata;held_control=ctl;
  d.clk=1;d.eval();d.clk=0;d.eval();cycles++;
 }
 void read(unsigned address,unsigned span,unsigned consume_count){
  d.c_valid=1;d.c_write=0;d.c_byte=0;d.c_read_beats=span;
  for(unsigned i=0;i<consume_count;i++){
   d.c_addr=address+i*4;d.eval();
   for(unsigned n=0;!d.c_ready;n++){need(n<1000,"core read watchdog");tick();}
   need(d.c_response&&d.c_rdata==mem[(address+i*4)/4],"read returned stale/wrong data");tick();
  }
  d.c_valid=0;d.eval();
 }
 void write(unsigned address,unsigned value){
  d.c_valid=1;d.c_write=1;d.c_byte=0;d.c_addr=address;d.c_wdata=value;d.eval();
  for(unsigned n=0;!d.c_ready;n++){need(n<1000,"posted write watchdog");tick();}
  need(d.c_response,"posted write acknowledgement");tick();d.c_valid=0;d.eval();
 }
 void idle(){d.c_valid=0;for(unsigned n=0;d.busy;n++){need(n<1000,"bridge drain watchdog");tick();}
  need(q.empty()&&issued==returned,"busy cleared before all replies");}
};
int main(){try{unsigned cases=0,peak=0;
 for(unsigned latency:{0u,1u,9u,40u})for(bool stress:{false,true}){
  Bench b;b.latency=latency;b.stress=stress;b.read(0,32,32);b.idle();
  for(unsigned i=0;i<16;i++)b.write(1024+i*4,0xabcd0000u+i);
  need(b.d.busy,"posted write queue was not counted as busy");b.idle();
  for(unsigned i=0;i<16;i++)need(b.mem[256+i]==0xabcd0000u+i,"posted write lost");
  // Interrupt a partially consumed read segment with a write, then change reads.
  b.read(2048,32,2);b.write(3072,0xdeadbeef);b.idle();
  need(b.mem[768]==0xdeadbeef,"read/write mode switch lost write");b.read(4096,7,7);b.idle();
  peak=std::max(peak,b.max_pending);cases++;
 }
 {Bench b;b.allow_requests=false;b.d.c_valid=1;b.d.c_write=0;b.d.c_addr=0;b.d.c_read_beats=16;
  for(unsigned n=0;!b.d.m_valid;n++){need(n<20,"no held read offer");b.tick();}
  b.d.__SYM__abort=1;b.d.c_valid=0;for(unsigned i=0;i<8;i++)b.tick();
  b.allow_requests=true;b.idle();b.d.__SYM__abort=0;b.mem[0]=0xfedcba98;b.read(0,1,1);b.idle();cases++;
 }
 {Bench b;b.allow_requests=false;b.write(0,0x11);b.write(4,0x22);b.d.__SYM__abort=1;
  for(unsigned i=0;i<8;i++)b.tick();b.allow_requests=true;b.idle();
  need(b.mem[0]==0x11&&b.mem[1]==0x22,"abort lost captured writes");b.d.__SYM__abort=0;b.read(0,2,2);b.idle();cases++;
 }
 need(peak==4,"four external read credits not exercised");
 std::cout<<"PASS bridge cases="<<cases<<" peak_pending="<<peak<<"; ordered reads, mode switches, posted writes, backpressure, abort and late replies\n";
 return 0;
}catch(const std::exception&e){std::cerr<<"FAIL: "<<e.what()<<'\n';return 1;}}
