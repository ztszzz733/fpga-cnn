// Rising-edge samples of the existing top-level recording; no RTL execution.
#include "fstapi.h"
#include <array>
#include <map>
#include <set>
#include <string>
#include <fstream>
#include <iostream>
#include <cstdint>
using U64=uint64_t;using U32=uint32_t;
struct S{U64 time=0;bool clock=false;U32 valid=0,ready=0,write=0,response=0,byte=0,addr=0,data=0,state=0,memory=0,mover=0,rv=0,rr=0;};
struct C{
 fstWriterContext*w;std::map<fstHandle,std::string>in;std::map<std::string,fstHandle>out;
 S cur,prev;bool have=false,prevHave=false,pending=false,accepted=false,returned=false;
 U64 begin,end,accepts=0,returns=0,firstA=0,firstR=0;U32 addr=0,data=0,bytes=0,firstAddr=0,firstData=0;
};
const char*pw[]={"IDLE","SETUP","CHECK","TILE_BEGIN","INPUT_LOAD","WEIGHT_LOAD","MAC_RUN","OUTPUT_QUEUE","OUTPUT_WAIT","DRAIN","FINISH","FAIL"};
const char*memory[]={"IDLE","LOCAL_ACCESS","LOCAL_REPLY","WRITEBACK_REQ","WRITEBACK_WAIT","PAGE_FILL_REQ","PAGE_FILL_WAIT","FENCE_SCAN"};
const char*mover[]={"IDLE","PREPARE","DDR_READ_REQ","DDR_READ_WAIT","LOCAL_REQ","LOCAL_WAIT","DDR_WRITE","DDR_WRITE_WAIT","NEXT_BURST","RESPONSE"};
U32 num(const unsigned char*p,unsigned n){U32 v=0;for(unsigned j=0;j<n;j++)v=(v<<1)|(p[j]=='1');return v;}
void bit(C&c,const char*n,unsigned b,U32 v){fstWriterEmitValueChange32(c.w,c.out[n],b,v);}
void label(C&c,const char*n,const char*v){fstWriterEmitVariableLengthValueChange(c.w,c.out[n],v,std::char_traits<char>::length(v));}
void flush(C&c){
 if(!c.have)return;auto&s=c.cur;
 if(c.prevHave&&s.clock&&!c.prev.clock){
  auto&p=c.prev;bool take=p.valid&&p.ready;
  c.accepted=take&&!p.write;c.returned=p.response&&(c.pending||c.accepted);
  if(c.accepted){c.addr=p.addr;c.bytes=p.byte?1:4;}
  if(c.returned)c.data=p.data;
  if(p.response)c.pending=false;
  if(take)c.pending=!p.write&&!p.response;
  if(s.time>=c.begin&&s.time<=c.end){
   if(c.accepted){if(!c.accepts){c.firstA=s.time;c.firstAddr=c.addr;}c.accepts++;}
   if(c.returned){if(!c.returns){c.firstR=s.time;c.firstData=c.data;}c.returns++;}
  }
 }
 if(s.time>=c.begin&&s.time<=c.end){
  fstWriterEmitTimeChange(c.w,s.time);
  bit(c,"CLK",1,s.clock);bit(c,"K1_0_READ_REQUEST",1,s.valid&&!s.write);
  bit(c,"K1_0_READ_ACCEPTED",1,c.accepted);bit(c,"K1_0_READ_DATA_VALID",1,c.returned);
  bit(c,"K1_0_READ_ADDR",32,c.addr);bit(c,"K1_0_READ_DATA",32,c.data);bit(c,"K1_0_READ_BYTES",3,c.bytes);
  bit(c,"RAW_CNN_VALID",1,s.valid);bit(c,"RAW_CNN_READY",1,s.ready);bit(c,"RAW_CNN_WRITE",1,s.write);bit(c,"RAW_CNN_RESPONSE",1,s.response);
  bit(c,"DDR_DATA_VALID",1,s.rv);bit(c,"DDR_DATA_ACCEPTED",1,s.rv&&s.rr);
  label(c,"K1_0_STATE",s.state<12?pw[s.state]:"UNKNOWN");label(c,"MEMORY_STATE",memory[s.memory]);label(c,"MOVER_STATE",mover[s.mover]);
 }
 c.prev=s;c.prevHave=true;
}
void change(void*arg,U64 t,fstHandle h,const unsigned char*p){
 auto&c=*static_cast<C*>(arg);if(t>c.end)return;
 if(!c.have||t!=c.cur.time){flush(c);c.cur.time=t;c.have=true;}
 auto&n=c.in[h];auto&s=c.cur;constexpr unsigned k=2;
 if(n=="FCLK_CLK0")s.clock=p[0]=='1';
 else if(n=="debug_valid")s.valid=(num(p,12)>>k)&1;
 else if(n=="debug_ready")s.ready=(num(p,12)>>k)&1;
 else if(n=="debug_write")s.write=(num(p,12)>>k)&1;
 else if(n=="debug_response")s.response=(num(p,12)>>k)&1;
 else if(n=="debug_byte")s.byte=(num(p,12)>>k)&1;
 else if(n=="debug_addr")s.addr=num(p+384-32*(k+1),32);
 else if(n=="debug_rdata")s.data=num(p+384-32*(k+1),32);
 else if(n=="debug_operator_state")s.state=num(p+48-4*(k+1),4);
 else if(n=="debug_memory_state")s.memory=num(p,3);
 else if(n=="debug_mover_state")s.mover=num(p,4);
 else if(n=="S_AXI_HP0_RVALID")s.rv=p[0]=='1';
 else if(n=="S_AXI_HP0_RREADY")s.rr=p[0]=='1';
}
int main(int argc,char**argv){
 if(argc!=6)return 2;C c;c.begin=std::stoull(argv[3]);c.end=std::stoull(argv[4]);
 auto*r=fstReaderOpen(argv[1]);if(!r)return 3;c.w=fstWriterCreate(argv[2],1);fstWriterSetTimescale(c.w,-12);
 fstWriterSetComment(c.w,"K1_0 is client bit 2. READ_ACCEPTED and READ_DATA_VALID are rising-edge sampled request acceptance and data consumption, derived from the recorded valid/ready/write/response plus remembered request direction. No new simulation.");
 fstWriterSetScope(c.w,FST_ST_VCD_MODULE,"CNN_READ",nullptr);
 for(auto n:{"CLK","K1_0_READ_REQUEST","K1_0_READ_ACCEPTED","K1_0_READ_DATA_VALID","RAW_CNN_VALID","RAW_CNN_READY","RAW_CNN_WRITE","RAW_CNN_RESPONSE","DDR_DATA_VALID","DDR_DATA_ACCEPTED"})c.out[n]=fstWriterCreateVar(c.w,FST_VT_VCD_WIRE,FST_VD_IMPLICIT,1,n,0);
 for(auto n:{"K1_0_READ_ADDR","K1_0_READ_DATA"})c.out[n]=fstWriterCreateVar(c.w,FST_VT_VCD_WIRE,FST_VD_IMPLICIT,32,n,0);
 c.out["K1_0_READ_BYTES"]=fstWriterCreateVar(c.w,FST_VT_VCD_WIRE,FST_VD_IMPLICIT,3,"K1_0_READ_BYTES",0);
 for(auto n:{"K1_0_STATE","MEMORY_STATE","MOVER_STATE"})c.out[n]=fstWriterCreateVar(c.w,FST_VT_GEN_STRING,FST_VD_IMPLICIT,0,n,0);
 fstWriterSetUpscope(c.w);fstReaderClrFacProcessMaskAll(r);
 std::set<std::string>wanted={"FCLK_CLK0","debug_valid","debug_ready","debug_write","debug_response","debug_byte","debug_addr","debug_rdata","debug_operator_state","debug_memory_state","debug_mover_state","S_AXI_HP0_RVALID","S_AXI_HP0_RREADY"},found;
 while(auto*h=fstReaderIterateHier(r))if(h->htyp==FST_HT_VAR){std::string n=h->u.var.name;n=n.substr(0,n.find_first_of(" ["));if(wanted.count(n)&&!found.count(n)){found.insert(n);c.in[h->u.var.handle]=n;fstReaderSetFacProcessMask(r,h->u.var.handle);}}
 if(found!=wanted)return 4;
 fstWriterEmitTimeChange(c.w,c.begin);fstReaderSetLimitTimeRange(r,c.begin,c.end);fstReaderIterBlocks(r,change,&c,nullptr);flush(c);fstWriterEmitTimeChange(c.w,c.end);fstWriterClose(c.w);fstReaderClose(r);
 if(c.accepts==0||c.returns==0||c.returns>c.accepts||c.accepts-c.returns>1)return 5;
 std::ofstream f(argv[5]);f<<"{\"status\":\"PASS\",\"accepted_reads\":"<<c.accepts<<",\"returned_reads\":"<<c.returns<<",\"first_accept_ps\":"<<c.firstA<<",\"first_return_ps\":"<<c.firstR<<",\"first_address\":"<<c.firstAddr<<",\"first_data\":"<<c.firstData<<",\"begin_ps\":"<<c.begin<<",\"end_ps\":"<<c.end<<"}\n";
 std::cout<<"PASS read demo: accepted="<<c.accepts<<" returned="<<c.returns<<" first_address=0x"<<std::hex<<c.firstAddr<<" first_data=0x"<<c.firstData<<"\n";
}
