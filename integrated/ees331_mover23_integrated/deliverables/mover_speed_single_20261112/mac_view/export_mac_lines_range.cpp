#include "fstapi.h"
#include <array>
#include <map>
#include <string>
#include <vector>
#include <iostream>
#include <fstream>
#include <cstdint>
using U=uint64_t;
struct Unit {unsigned phase=99;bool active=false;fstHandle text,act,read=0,acc=0,run=0,fire;};
struct App {fstWriterContext*w;std::array<Unit,8>units;std::map<fstHandle,std::pair<int,std::string>> in;std::map<std::string,fstHandle> global;U time=0,begin=0,limit=UINT64_MAX,firstRead=0,firstAcc=0,firstEnd=0;};
const std::vector<std::string>k3={"IDLE","SETUP","CHECK","TILE_BEGIN","INPUT_REQ","INPUT_WAIT","WEIGHT_REQ","WEIGHT_WAIT","MAC_READ","MAC_ACC","OUTPUT_REQ","OUTPUT_WAIT","FINISH","FAIL"};
const std::vector<std::string>k1={"IDLE","SETUP","CHECK","TILE_BEGIN","INPUT_LOAD","WEIGHT_LOAD","MAC_RUN","OUTPUT_QUEUE","OUTPUT_WAIT","DRAIN","FINISH","FAIL"};
const std::vector<std::string>mem={"IDLE","LOCAL_ACCESS","LOCAL_REPLY","WRITEBACK_REQ","WRITEBACK_WAIT","PAGE_FILL_REQ","PAGE_FILL_WAIT","FENCE_SCAN"};
const std::vector<std::string>mov={"IDLE","PREPARE","DDR_READ_REQ","DDR_READ_WAIT","LOCAL_REQ","LOCAL_WAIT","DDR_WRITE","DDR_WRITE_WAIT","NEXT_BEAT","RESPONSE"};
unsigned value(const unsigned char*p,unsigned n){unsigned v=0;for(unsigned i=0;i<n;i++)v=(v<<1)|(p[i]=='1');return v;}
std::string unitName(int i){return i<2?"K3_"+std::to_string(i):"K1_"+std::to_string(i-2);}
fstHandle bit(App&a,const char*n){return fstWriterCreateVar(a.w,FST_VT_VCD_WIRE,FST_VD_IMPLICIT,1,n,0);}
fstHandle text(App&a,const char*n){return fstWriterCreateVar(a.w,FST_VT_GEN_STRING,FST_VD_IMPLICIT,0,n,0);}
void emitText(App&a,fstHandle h,const std::string&s){fstWriterEmitVariableLengthValueChange(a.w,h,s.c_str(),s.size());}
void emitUnit(App&a,int i){auto&u=a.units[i];auto&names=i<2?k3:k1;emitText(a,u.text,u.active&&u.phase<names.size()?names[u.phase]:"IDLE_NO_TASK");
 if(i<2){fstWriterEmitValueChange32(a.w,u.read,1,u.active&&u.phase==8);fstWriterEmitValueChange32(a.w,u.acc,1,u.active&&u.phase==9);}
 else fstWriterEmitValueChange32(a.w,u.run,1,u.active&&u.phase==6);
 if(i==0&&u.active){if(u.phase==8&&!a.firstRead)a.firstRead=a.time;if(u.phase==9&&!a.firstAcc)a.firstAcc=a.time;if(a.firstAcc&&!a.firstEnd&&u.phase!=8&&u.phase!=9)a.firstEnd=a.time;}
}
void change(void*ptr,U t,fstHandle h,const unsigned char*raw){auto&a=*static_cast<App*>(ptr);if(t>a.limit)return;if(t<a.begin)t=a.begin;auto it=a.in.find(h);if(it==a.in.end())return;if(t!=a.time){fstWriterEmitTimeChange(a.w,t);a.time=t;}int i=it->second.first;auto name=it->second.second;
 if(i>=0){auto&u=a.units[i];if(name=="FSM"){u.phase=value(raw,4);emitUnit(a,i);}else if(name=="ACTIVE"){u.active=value(raw,1);fstWriterEmitValueChange32(a.w,u.act,1,u.active);emitUnit(a,i);}else fstWriterEmitValueChange(a.w,u.fire,raw);}
 else if(name=="MEMORY_FSM")emitText(a,a.global["MEMORY_STATE_TEXT"],mem.at(value(raw,3)));
 else if(name=="MOVER_FSM")emitText(a,a.global["MOVER_STATE_TEXT"],mov.at(value(raw,4)));
 else fstWriterEmitValueChange(a.w,a.global.at(name),raw);
}
int main(int argc,char**argv){if(argc!=4&&argc!=6)return 2;auto*r=fstReaderOpen(argv[1]);if(!r)return 3;App a;if(argc==6){a.begin=std::stoull(argv[4]);a.limit=std::stoull(argv[5]);a.time=a.begin;}a.w=fstWriterCreate(argv[2],1);fstWriterSetTimescale(a.w,fstReaderGetTimescale(r));fstWriterSetComment(a.w,"Derived display only: MAC_READ=ACTIVE && recorded FSM==8; MAC_ACC==9; K1 MAC_RUN==6. MAC_FIRE copies recorded convolution WORK. No RTL simulation rerun; timestamps preserved.");
 fstWriterSetScope(a.w,FST_ST_VCD_MODULE,"SOC",nullptr);
 for(auto name:{"CNN_RUNNING","CNN_COMPUTE_DONE","DDR_RETURNING_DATA","DDR_SENDING_DATA"})a.global[name]=bit(a,name);
 for(auto name:{"MEMORY_STATE_TEXT","MOVER_STATE_TEXT"})a.global[name]=text(a,name);
 for(int i=0;i<8;i++){fstWriterSetScope(a.w,FST_ST_VCD_MODULE,unitName(i).c_str(),nullptr);auto&u=a.units[i];u.text=text(a,"STATE_TEXT");u.act=bit(a,"ACTIVE");u.fire=bit(a,"MAC_FIRE");if(i<2){u.read=bit(a,"MAC_READ");u.acc=bit(a,"MAC_ACC");}else u.run=bit(a,"MAC_RUN");fstWriterSetUpscope(a.w);}
 fstWriterSetUpscope(a.w);fstReaderClrFacProcessMaskAll(r);std::vector<std::string>stack;
 while(auto*h=fstReaderIterateHier(r)){
  if(h->htyp==FST_HT_SCOPE)stack.emplace_back(h->u.scope.name);else if(h->htyp==FST_HT_UPSCOPE){if(!stack.empty())stack.pop_back();}
  else if(h->htyp==FST_HT_VAR){std::string n=h->u.var.name;n=n.substr(0,n.find_first_of(" ["));int i=-2;
   if(stack.size()==1&&stack[0]=="SOC"&&(n=="MEMORY_FSM"||n=="MOVER_FSM"||n=="CNN_RUNNING"||n=="CNN_COMPUTE_DONE"||n=="DDR_RETURNING_DATA"||n=="DDR_SENDING_DATA"))i=-1;
   if(stack.size()==2&&stack[0]=="SOC"&&(n=="FSM"||n=="ACTIVE"||n=="WORK"))for(int k=0;k<8;k++)if(stack[1]==unitName(k))i=k;
   if(i!=-2){a.in[h->u.var.handle]={i,n};fstReaderSetFacProcessMask(r,h->u.var.handle);}
  }
 }
 if(a.in.size()!=30){std::cerr<<"Missing source signals: "<<a.in.size()<<"\n";return 4;}
 fstWriterEmitTimeChange(a.w,a.begin);if(argc==6)fstReaderSetLimitTimeRange(r,a.begin,a.limit);fstReaderIterBlocks(r,change,&a,nullptr);U end=std::min(a.limit,fstReaderGetEndTime(r));fstWriterEmitTimeChange(a.w,end);fstWriterClose(a.w);fstReaderClose(r);
 std::ofstream f(argv[3]);f<<"{\"input_signals\":30,\"output_signals\":40,\"timescale\":\"1ps\",\"first_k3_mac_read_ps\":"<<a.firstRead<<",\"first_k3_mac_acc_ps\":"<<a.firstAcc<<",\"first_k3_compute_exit_ps\":"<<a.firstEnd<<",\"end_ps\":"<<end<<"}\n";
 std::cout<<"PASS: 40 signals; first MAC_READ="<<a.firstRead<<" MAC_ACC="<<a.firstAcc<<" exit="<<a.firstEnd<<"\n";
}
