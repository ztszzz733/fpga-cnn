#include "Vplanned_read_adapter.h"
#include "verilated.h"
#include "k3_plan.h"
#include <algorithm>
#include <cstdint>
#include <deque>
#include <iostream>
#include <stdexcept>
#include <vector>
static void need(bool b,const char *s){if(!b)throw std::runtime_error(s);}
struct Bench {
 Vplanned_read_adapter d;
 struct Reply{unsigned due;uint32_t value;};
 struct Request{uint32_t addr,data;bool byte,write;};
 struct Step{bool ready,response;uint32_t data;};
 std::vector<uint8_t> mem=std::vector<uint8_t>(131072);
 std::deque<Reply> replies;
 std::vector<Request> log;
 unsigned cycle=0,rng=7713,max_pending=0,stalled=0;
 bool held=false,inject=false,zero_write=false;
 Request previous{};
 unsigned random(){rng=rng*1664525u+1013904223u;return rng;}
 uint32_t load(unsigned a,bool byte){
  need(a+(byte?1:4)<=mem.size(),"bus address outside test memory");
  if(byte)return uint32_t(int32_t(int8_t(mem[a])));
  return uint32_t(mem[a])|uint32_t(mem[a+1])<<8|uint32_t(mem[a+2])<<16|uint32_t(mem[a+3])<<24;
 }
 Step tick(){
  need(cycle++<1000000,"adapter watchdog");
  d.clk=0;d.m_ready=(random()%5)!=0;
  bool returning=!replies.empty()&&replies.front().due<=cycle;
  d.m_response=returning||inject;d.m_rdata=returning?replies.front().value:0xabcdef12;
  d.eval();
  bool zero=zero_write&&d.m_valid&&d.m_write&&d.m_ready;
  if(zero){d.m_response=1;d.m_rdata=0;d.eval();}
  Step s{bool(d.c_ready),bool(d.c_response),d.c_rdata};
  Request now{d.m_addr,d.m_wdata,bool(d.m_byte),bool(d.m_write)};
  if(held&&!d.clear)need(d.m_valid&&now.addr==previous.addr&&now.data==previous.data&&
                         now.byte==previous.byte&&now.write==previous.write,"request changed under backpressure");
  held=d.m_valid&&!d.m_ready;previous=now;if(held)++stalled;
  if(returning)replies.pop_front();
  if(d.m_valid&&d.m_ready){
   need(now.addr+(now.byte?1:4)<=mem.size(),"request escaped segment address space");
   uint32_t value=0;
   if(now.write){for(unsigned b=0;b<(now.byte?1u:4u);++b)mem[now.addr+b]=uint8_t(now.data>>(8*b));}
   else value=load(now.addr,now.byte);
   unsigned due=cycle+1+random()%7;
   if(!replies.empty())due=std::max(due,replies.back().due+1);
   if(!zero)replies.push_back({due,value});log.push_back(now);
  }
  max_pending=std::max(max_pending,unsigned(replies.size()));
  d.clk=1;d.eval();d.clk=0;d.eval();return s;
 }
 Bench(){
  for(unsigned i=0;i<mem.size();++i)mem[i]=uint8_t(i*29u+(i>>5));
  d.rst_n=0;d.clear=0;d.c_valid=0;d.c_write=0;d.c_byte=0;d.c_addr=0;d.c_wdata=0;d.segment_beats=0;
  tick();tick();d.rst_n=1;tick();
 }
 void read(unsigned base,unsigned count,bool byte){
  size_t first=log.size();
  for(unsigned i=0;i<count;++i){
   d.c_valid=1;d.c_write=0;d.c_byte=byte;d.c_addr=base+i*(byte?1:4);d.segment_beats=count;
   while(!tick().ready)need(!d.fault,"fault before demand accept");
   d.c_valid=0;
   for(;;){auto s=tick();need(!d.fault,"read fault");if(s.response){need(s.data==load(d.c_addr,byte),"ordered read data mismatch");break;}}
   for(unsigned j=random()%7;j;--j)tick();
  }
  need(d.idle&&replies.empty(),"segment did not completely drain");
  need(log.size()-first==count,"extra or missing prefetch request");
  for(unsigned i=0;i<count;++i)need(!log[first+i].write&&log[first+i].addr==base+i*(byte?1:4)&&
                                      log[first+i].byte==byte,"segment address/width sequence mismatch");
 }
 void write(unsigned addr,uint32_t data,bool byte){
  d.c_valid=1;d.c_write=1;d.c_byte=byte;d.c_addr=addr;d.c_wdata=data;
  while(!tick().ready)need(!d.fault,"write accept fault");
  d.c_valid=0;while(!tick().response)need(!d.fault,"write response fault");
  need(d.idle&&replies.empty(),"write did not drain");
 }
 void clear(){d.c_valid=0;d.clear=1;while(!replies.empty()){auto s=tick();need(!s.response,"reply crossed cancellation barrier");}tick();d.clear=0;tick();need(!d.fault&&d.idle,"clear failed");}
 void run(){
  for(unsigned n:{1u,3u,4u,5u,67u,128u}){read(0x1000,n,false);read(0x4001,n,true);}
  read(0x10000,4608,true);read(0x10000,1152,false);
  auto neighbor=mem[0x2000];write(0x2001,0x9a,true);need(mem[0x2000]==neighbor&&mem[0x2001]==0x9a,"byte write mask");
  write(0x2004,0x12345678,false);read(0x2000,5,false);
  zero_write=true;write(0x2010,0x11223344,false);write(0x2015,0x81,true);zero_write=false;
  read(0x2010,2,false);
  d.c_valid=1;d.c_write=0;d.c_byte=0;d.c_addr=0x4000;d.segment_beats=64;
  while(replies.empty())tick();clear();read(0x3000,5,false);
  for(unsigned kind=0;kind<4;++kind){
   size_t before=log.size();d.c_valid=1;d.c_write=0;d.c_byte=0;
   d.c_addr=kind==2?1:kind==3?0xfffffffcu:0x1000;
   d.segment_beats=kind==0?0:kind==1?4609:kind==3?2:1;
   for(unsigned i=0;i<4;++i)tick();need(d.fault&&log.size()==before,"invalid segment reached bus");clear();
  }
  inject=true;tick();inject=false;need(d.fault,"unexpected response not detected");clear();read(0x5000,4,false);
  need(stalled>20&&max_pending>=2,"stress scenarios not exercised");
  uint32_t row[20]={};row[0]=0;row[1]=0;row[2]=0;row[3]=0x1000;row[6]=4;row[7]=7;row[8]=7;row[9]=8;row[10]=1;
  row[4]=28;row[5]=36;row[11]=0x80000700;row[12]=196;row[15]=288;
  need(ees331_validate_k3(row),"valid software plan rejected");
  row[12]++;need(!ees331_validate_k3(row),"incorrect software extent accepted");row[12]--;
  row[1]=1;need(!ees331_validate_k3(row),"unaligned word plan accepted");row[1]=0;
  row[11]&=~EES331_K3_PLANNED;need(!ees331_validate_k3(row),"legacy plan accepted");
  std::cout<<"PASS planned reads: byte/word segments, exact bounds, ordered data, FIFO/backpressure, read/write transitions, cancellation barrier, errors and software schema; cycles="<<cycle<<"\n";
 }
};
int main(){try{Bench b;b.run();return 0;}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<"\n";return 1;}}
