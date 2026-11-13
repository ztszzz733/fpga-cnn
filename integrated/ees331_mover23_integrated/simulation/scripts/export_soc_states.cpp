// Decode recorded RTL states; all transition timestamps are preserved.
#include "fstapi.h"
#include <array>
#include <bitset>
#include <iostream>
#include <map>
#include <set>
#include <string>
#include <vector>
using U64=uint64_t;
const std::vector<std::vector<std::string>> phases={
 {"IDLE","SETUP","CHECK","TILE_BEGIN","INPUT_REQ","INPUT_WAIT","WEIGHT_REQ","WEIGHT_WAIT","MAC_READ","MAC_ACC","OUTPUT_REQ","OUTPUT_WAIT","FINISH","FAIL"},
 {"IDLE","SETUP","CHECK","TILE_BEGIN","INPUT_LOAD","WEIGHT_LOAD","MAC_RUN","OUTPUT_QUEUE","OUTPUT_WAIT","DRAIN","FINISH","FAIL"},
 {"IDLE","WEIGHT_REQ","WEIGHT_WAIT","INPUT_REQ","INPUT_WAIT","ZERO","RAM_READ","MAC","OUTPUT_REQ","OUTPUT_WAIT","FINISH","FAIL"},
 {"IDLE","PARAM_REQ","PARAM_WAIT","GROUP","A_REQ","A_WAIT","B_REQ","B_WAIT","DRAIN","WRITE_REQ","WRITE_WAIT","FINISH","FAIL"},
 {"IDLE","SELECT","READ_REQ","READ_WAIT","WRITE_REQ","WRITE_WAIT","FINISH","FAIL"},
 {"IDLE","LOCAL_ACCESS","LOCAL_REPLY","WRITEBACK_REQ","WRITEBACK_WAIT","PAGE_FILL_REQ","PAGE_FILL_WAIT","FENCE_SCAN"},
 {"IDLE","PREPARE","DDR_READ_REQ","DDR_READ_WAIT","LOCAL_REQ","LOCAL_WAIT","DDR_WRITE","DDR_WRITE_WAIT","NEXT_BEAT","RESPONSE"}
};
std::string unit(unsigned k){if(k<4)return "K3_"+std::to_string(k);if(k<16)return "K1_"+std::to_string(k-4);if(k==16)return "DW7";if(k<21)return "POST_"+std::to_string(k-17);return k==21?"ADD":"PAD";}
unsigned kind(unsigned k){return k<4?0:k<16?1:k==16?2:k<22?3:4;}
fstEnumHandle table(fstWriterContext*w,unsigned type,bool qualified){
 std::vector<std::string> labels,values;
 if(qualified){labels.push_back("IDLE_NO_TASK");values.push_back("00000");}
 unsigned bits=qualified?5:type==5?3:4;
 for(unsigned i=0;i<phases[type].size();i++){labels.push_back(phases[type][i]);values.push_back(std::bitset<5>((qualified?16:0)+i).to_string().substr(5-bits));}
 std::vector<const char*> l,v;for(auto&s:labels)l.push_back(s.c_str());for(auto&s:values)v.push_back(s.c_str());
 std::string name="type_"+std::to_string(type)+(qualified?"_task":"_fsm");
 return fstWriterCreateEnumTable(w,name.c_str(),l.size(),bits,l.data(),v.data());
}
struct C {
 fstWriterContext*w;std::map<fstHandle,std::string> inputs;std::map<std::string,fstHandle> out;
 std::array<fstHandle,23> state{},label{},raw{},active{},work{},job{},frame{},step{};
 std::array<unsigned,23> phase{};unsigned activeMask=0;
 U64 time=0,begin=0,end=UINT64_MAX;U64 transitions=0;unsigned cpuWe=0,cpuAddr=0,cpuData=0;
};
fstHandle variable(C&c,const std::string&name,unsigned bits,fstEnumHandle e=0){
 if(e)fstWriterEmitEnumTableRef(c.w,e);
 auto h=fstWriterCreateVar(c.w,FST_VT_VCD_WIRE,FST_VD_IMPLICIT,bits,name.c_str(),0);c.out[name]=h;return h;
}
unsigned number(const unsigned char*p,unsigned n){unsigned v=0;for(unsigned i=0;i<n;i++)v=(v<<1)|(p[i]=='1');return v;}
void state(C&c,unsigned k){
 bool active=(c.activeMask>>k)&1;
 fstWriterEmitValueChange32(c.w,c.state[k],5,active?16+c.phase[k]:0);
 const std::string s=active&&c.phase[k]<phases[kind(k)].size()?phases[kind(k)][c.phase[k]]:"IDLE_NO_TASK";
 fstWriterEmitVariableLengthValueChange(c.w,c.label[k],s.c_str(),s.size());
}
void cfg(C&c){if(c.cpuWe){fstWriterEmitValueChange32(c.w,c.out["CPU_LAST_CFG_ADDR"],32,c.cpuAddr);fstWriterEmitValueChange32(c.w,c.out["CPU_LAST_CFG_DATA"],32,c.cpuData);}}
void change(void*p,U64 t,fstHandle h,const unsigned char*raw){
 auto&c=*static_cast<C*>(p);if(t>c.end)return;if(t<c.begin)t=c.begin;auto it=c.inputs.find(h);if(it==c.inputs.end())return;
 if(t!=c.time){fstWriterEmitTimeChange(c.w,t);c.time=t;}c.transitions++;
 auto&s=it->second;
 if(s=="debug_operator_state"){
  for(unsigned k=0;k<23;k++){unsigned v=number(raw+92-4*(k+1),4);if(v!=c.phase[k]){c.phase[k]=v;fstWriterEmitValueChange32(c.w,c.raw[k],4,v);state(c,k);}}return;
 }
 if(s=="debug_unit_active"||s=="debug_work"){
  unsigned v=number(raw,23);if(s=="debug_unit_active")c.activeMask=v;
  for(unsigned k=0;k<23;k++){fstWriterEmitValueChange32(c.w,s=="debug_work"?c.work[k]:c.active[k],1,(v>>k)&1);if(s=="debug_unit_active")state(c,k);}return;
 }
 if(s=="debug_node"){
  for(unsigned k=0;k<23;k++){unsigned n=number(raw+253-11*(k+1),11);fstWriterEmitValueChange32(c.w,c.job[k],11,n);fstWriterEmitValueChange32(c.w,c.frame[k],3,n%5);fstWriterEmitValueChange32(c.w,c.step[k],8,n/5);}return;
 }
 if(s=="debug_mmio_we"){c.cpuWe=number(raw,1);fstWriterEmitValueChange32(c.w,c.out["CPU_WRITE_CNN"],1,c.cpuWe);cfg(c);return;}
 if(s=="debug_mmio_addr"){c.cpuAddr=number(raw,32);cfg(c);return;}
 if(s=="debug_mmio_data"){c.cpuData=number(raw,32);cfg(c);return;}
 static const std::map<std::string,std::string> mapping={
 {"debug_memory_state","MEMORY_FSM"},{"debug_mover_state","MOVER_FSM"},{"debug_cnn_running","CNN_RUNNING"},{"debug_cnn_finished","CNN_COMPUTE_DONE"},
 {"debug_error","CNN_ERROR"},{"debug_fault","MEMORY_FAULT"},{"debug_completed","COMPLETED_TASKS"},{"debug_page_misses","PAGE_MISSES"},
 {"debug_mover_read_bytes","DDR_READ_BYTES"},{"debug_mover_write_bytes","DDR_WRITE_BYTES"},
 {"S_AXI_HP0_RVALID","DDR_RETURNING_DATA"},{"S_AXI_HP0_WVALID","DDR_SENDING_DATA"},{"FCLK_RESET0_N","RESET_RELEASED"},
 {"debug_cpu_re","CPU_RAM_READ"},{"debug_cpu_we","CPU_RAM_WRITE"},{"M_AXI_GP0_WVALID","PS_MAILBOX_WRITE"},{"M_AXI_GP0_ARVALID","PS_MAILBOX_READ"}};
 auto m=mapping.find(s);if(m!=mapping.end())fstWriterEmitValueChange(c.w,c.out[m->second],raw);
 if(s=="debug_memory_state"||s=="debug_mover_state"){
  unsigned type=s=="debug_memory_state"?5:6,v=number(raw,type==5?3:4);
  const auto&label=phases[type].at(v);
  fstWriterEmitVariableLengthValueChange(c.w,c.out[type==5?"MEMORY_STATE_TEXT":"MOVER_STATE_TEXT"],label.c_str(),label.size());
 }
}
int main(int argc,char**argv){
 if(argc!=3&&argc!=5)return 2;auto*r=fstReaderOpen(argv[1]);if(!r){std::cerr<<"Cannot open source FST\n";return 3;}
 C c;if(argc==5){c.begin=std::stoull(argv[3]);c.end=std::stoull(argv[4]);}c.time=c.begin;c.phase.fill(99);c.w=fstWriterCreate(argv[2],1);fstWriterSetTimescale(c.w,fstReaderGetTimescale(r));
 fstWriterSetComment(c.w,"Exact recorded states. Task STATE is IDLE_NO_TASK when unit_active=0, otherwise the actual RTL FSM. MAC/work are separate indicators. Frame is slot 0..4.");
 fstWriterSetScope(c.w,FST_ST_VCD_MODULE,"SOC",nullptr);
 auto mem=table(c.w,5,false),mover=table(c.w,6,false);
 variable(c,"MEMORY_FSM",3,mem);variable(c,"MOVER_FSM",4,mover);
 for(auto s:{"CPU_WRITE_CNN","CNN_RUNNING","CNN_COMPUTE_DONE","CNN_ERROR","MEMORY_FAULT","DDR_RETURNING_DATA","DDR_SENDING_DATA","RESET_RELEASED","CPU_RAM_READ","CPU_RAM_WRITE","PS_MAILBOX_WRITE","PS_MAILBOX_READ"})variable(c,s,1);
 for(auto s:{"MEMORY_STATE_TEXT","MOVER_STATE_TEXT"})c.out[s]=fstWriterCreateVar(c.w,FST_VT_GEN_STRING,FST_VD_IMPLICIT,0,s,0);
 for(auto s:{"CPU_LAST_CFG_ADDR","CPU_LAST_CFG_DATA","PAGE_MISSES","DDR_READ_BYTES","DDR_WRITE_BYTES"})variable(c,s,32);
 variable(c,"COMPLETED_TASKS",12);
 for(unsigned k=0;k<23;k++){
  fstWriterSetScope(c.w,FST_ST_VCD_MODULE,unit(k).c_str(),nullptr);
  c.state[k]=variable(c,"STATE",5,table(c.w,kind(k),true));c.raw[k]=variable(c,"FSM",4,table(c.w,kind(k),false));
  c.label[k]=fstWriterCreateVar(c.w,FST_VT_GEN_STRING,FST_VD_IMPLICIT,0,"STATE_TEXT",0);
  c.active[k]=variable(c,"ACTIVE",1);c.work[k]=variable(c,"WORK",1);c.job[k]=variable(c,"TASK",11);c.frame[k]=variable(c,"FRAME_SLOT",3);c.step[k]=variable(c,"STEP",8);
  fstWriterSetUpscope(c.w);
 }
 fstWriterSetUpscope(c.w);fstReaderClrFacProcessMaskAll(r);
 std::set<std::string> wanted={"debug_operator_state","debug_unit_active","debug_work","debug_node","debug_memory_state","debug_mover_state","debug_cnn_running","debug_cnn_finished","debug_error","debug_fault","debug_completed","debug_page_misses","debug_mover_read_bytes","debug_mover_write_bytes","debug_mmio_we","debug_mmio_addr","debug_mmio_data","S_AXI_HP0_RVALID","S_AXI_HP0_WVALID","FCLK_RESET0_N","debug_cpu_re","debug_cpu_we","M_AXI_GP0_WVALID","M_AXI_GP0_ARVALID"},found;
 while(auto*h=fstReaderIterateHier(r))if(h->htyp==FST_HT_VAR){std::string n=h->u.var.name;n=n.substr(0,n.find_first_of(" ["));if(wanted.count(n)&&!found.count(n)){found.insert(n);c.inputs[h->u.var.handle]=n;fstReaderSetFacProcessMask(r,h->u.var.handle);}}
 if(found!=wanted){for(auto&s:wanted)if(!found.count(s))std::cerr<<"Missing "<<s<<"\n";return 4;}
 fstWriterEmitTimeChange(c.w,c.begin);if(argc==5)fstReaderSetLimitTimeRange(r,c.begin,c.end);fstReaderIterBlocks(r,change,&c,nullptr);auto end=std::min(c.end,fstReaderGetEndTime(r));fstWriterEmitTimeChange(c.w,end);fstWriterClose(c.w);fstReaderClose(r);
 std::cout<<"PASS exported "<<found.size()<<" source signals and "<<c.transitions<<" transitions; end_ps="<<end<<"\n";
}
