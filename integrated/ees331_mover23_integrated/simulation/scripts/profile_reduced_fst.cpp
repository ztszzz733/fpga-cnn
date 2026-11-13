// Read an existing recording only; no RTL is evaluated and no run is repeated.
#include "fstapi.h"
#include <array>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <string>
using U64=uint64_t;
struct P{
 U64 begin,end,last=0,total=0,overlap=0,macFire=0;
 unsigned memory=0,mover=0,active=0,work=0;
 std::array<unsigned,12> phase{};
 std::array<U64,8> mem{};std::array<U64,10> move{};
 std::array<std::array<U64,16>,12> unit{};
 std::map<std::string,U64> classes;
 std::map<fstHandle,std::string> names;
 void integrate(U64 t){
  U64 a=last>begin?last:begin,b=t<end?t:end;last=t;if(b<=a)return;
  U64 dt=b-a;total+=dt;mem.at(memory)+=dt;move.at(mover)+=dt;
  if(work&255)macFire+=dt;
  if(active&(active-1))overlap+=dt;
  std::string c="no_active_operator";
  if(active){
   unsigned k=__builtin_ctz(active),p=phase[k];unit[k][p]+=dt;
   if(k<2)c=(p==4||p==5)?"conv_input_load":(p==6||p==7)?"conv_weight_load":(p==8||p==9)?"conv_compute_phase":(p==10||p==11)?"conv_output":"conv_setup_other";
   else if(k<8)c=p==4?"conv_input_load":p==5?"conv_weight_load":p==6?"conv_compute_phase":(p>=7&&p<=9)?"conv_output":"conv_setup_other";
   else c=k<11?"post_add_total":"pad_total";
  }
  classes[c]+=dt;
 }
};
unsigned number(const unsigned char*p,unsigned n){unsigned v=0;for(unsigned i=0;i<n;i++)v=(v<<1)|(p[i]=='1');return v;}
void change(void*arg,U64 t,fstHandle h,const unsigned char*raw){
 auto&p=*static_cast<P*>(arg);if(t>p.end)return;p.integrate(t);auto&s=p.names[h];
 if(s=="debug_memory_state")p.memory=number(raw,3);
 else if(s=="debug_mover_state")p.mover=number(raw,4);
 else if(s=="debug_unit_active")p.active=number(raw,12);
 else if(s=="debug_work")p.work=number(raw,12);
 else if(s=="debug_operator_state")for(unsigned k=0;k<12;k++)p.phase[k]=number(raw+48-4*(k+1),4);
}
int main(int argc,char**argv){
 if(argc!=5)return 2;P p;p.begin=std::stoull(argv[2]);p.end=std::stoull(argv[3]);
 auto*r=fstReaderOpen(argv[1]);if(!r)return 3;if(fstReaderGetTimescale(r)!=-12)return 4;
 std::set<std::string>wanted={"debug_memory_state","debug_mover_state","debug_unit_active","debug_work","debug_operator_state"},found;
 fstReaderClrFacProcessMaskAll(r);
 while(auto*h=fstReaderIterateHier(r))if(h->htyp==FST_HT_VAR){
  std::string n=h->u.var.name;n=n.substr(0,n.find_first_of(" ["));
  if(wanted.count(n)&&!found.count(n)){found.insert(n);p.names[h->u.var.handle]=n;fstReaderSetFacProcessMask(r,h->u.var.handle);}
 }
 if(found!=wanted)return 5;
 fstReaderIterBlocks(r,change,&p,nullptr);p.integrate(p.end);fstReaderClose(r);
 if(p.total!=p.end-p.begin)return 6;
 const char*memnames[]={"IDLE","ACCESS","REPLY","WB_REQ","WB_WAIT","FILL_REQ","FILL_WAIT","SCAN"};
 const char*movenames[]={"IDLE","PREP","DDR_READ_REQ","DDR_READ_WAIT","LOCAL_REQ","LOCAL_WAIT","DDR_WRITE","DDR_WRITE_WAIT","NEXT_BEAT","RESPONSE"};
 std::ofstream f(argv[4]);f<<std::fixed<<std::setprecision(1);
 f<<"{\n\"window_cycles\":"<<double(p.total)/10000<<",\n\"actual_conv_mac_fire_cycles\":"<<double(p.macFire)/10000<<",\n\"multiple_active_operator_cycles\":"<<double(p.overlap)/10000<<",\n";
 auto arr=[&](const char*name,auto&a,const char**labels){f<<"\""<<name<<"\":{";for(unsigned i=0;i<a.size();i++){if(i)f<<",";f<<"\""<<labels[i]<<"\":"<<double(a[i])/10000;}f<<"},\n";};
 arr("memory_cycles",p.mem,memnames);arr("mover_cycles",p.move,movenames);
 f<<"\"operator_class_cycles\":{";bool comma=false;for(auto&[n,v]:p.classes){if(comma)f<<",";comma=true;f<<"\""<<n<<"\":"<<double(v)/10000;}f<<"},\n\"unit_phase_cycles\":[";
 for(unsigned k=0;k<12;k++){if(k)f<<",";f<<"[";for(unsigned j=0;j<16;j++){if(j)f<<",";f<<double(p.unit[k][j])/10000;}f<<"]";}
 f<<"]\n}\n";f.close();std::cout<<"PASS recorded-wave profile; cycles="<<double(p.total)/10000<<"\n";
}
