// Control-only protocol/fairness tests. Operator delays are NOT arithmetic RTL.
#include "Vstream_dispatch.h"
#include "verilated.h"
#include <vector>
#include <array>
#include <iostream>
#include <fstream>
#include <stdexcept>
using U=unsigned;
void need(bool b,const char*s){if(!b)throw std::runtime_error(s);}
struct Job{U op=0;bool dw=false;int dep=-1;U frame=0;};
std::vector<U> run(std::vector<Job> jobs,int blocked=-1,bool late=false,bool restart=false,bool fault=false){
 Vstream_dispatch d;auto tick=[&]{d.clk=1;d.eval();d.clk=0;d.eval();};
 d.rst_n=0;d.clear=0;d.start=0;d.memory_fault=0;d.program_valid=0;d.frame_valid=0;d.buffer_ready=1;d.unit_busy=0;d.unit_done=0;d.unit_error=0;d.unit_enable=63;tick();tick();d.rst_n=1;tick();
 auto load=[&]{
  d.buffer_ready=blocked<0;
  for(U n=0;n<jobs.size();n++){
   need(d.program_ready,"program not ready");for(U k=0;k<16;k++)d.program_command[k]=0;
   auto j=jobs[n];d.program_command[0]=j.op;d.program_command[11]=j.dw;d.program_command[13]=100+j.frame;d.program_command[14]=j.frame;
   d.program_index=n;d.program_dep_valid=j.dep>=0;d.program_dep0=j.dep>=0?j.dep:0;d.program_dep1=0;d.program_valid=1;tick();
  }
  d.program_valid=0;d.task_count=jobs.size();d.start=1;tick();d.start=0;
  for(U f=0;f<(late?1:2);f++){d.frame_slot=f;d.frame_id=100+f;d.frame_valid=1;tick();}
  d.frame_valid=0;
 };
 load();std::vector<U> order;std::array<int,6> timers{};std::array<U,6> owner{};U finished=0;bool restarted=false,injected=false;
 for(U c=0;c<10000;c++){
  if((restart||fault)&&!restarted&&!order.empty()){
   if(fault){d.memory_fault=1;tick();need(d.cancel&&d.error,"fault not cancelled");d.memory_fault=0;}
   d.clear=1;tick();tick();d.clear=0;timers.fill(0);d.unit_busy=d.unit_done=0;order.clear();finished=0;tick();load();restarted=true;
  }
  d.frame_valid=late&&c==150;d.frame_slot=1;d.frame_id=101;
  d.buffer_ready=!(int(d.candidate_node)==blocked&&c<100);
  d.unit_busy=0;d.unit_done=0;
  for(U u=0;u<6;u++){
   if(timers[u]>0){d.unit_busy|=1u<<u;if(--timers[u]==0){d.unit_busy&=~(1u<<u);d.unit_done|=1u<<u;finished|=1u<<owner[u];}}
  }
  d.eval();
  if(d.unit_start)for(U u=0;u<6;u++)if(d.unit_start&(1u<<u)){
   U n=(d.unit_node>>(u*5))&31;need(n<jobs.size(),"node out of range");auto j=jobs[n];
   need(timers[u]==0,"preempted busy operator");need(j.dep<0||(finished&(1u<<j.dep)),"dependency violated");
   need(!(late&&j.frame==1&&c<=150),"uncommitted input dispatched");need(!(int(n)==blocked&&c<100),"buffer reservation bypassed");
   for(U old:order)need(old!=n,"duplicate dispatch");order.push_back(n);owner[u]=n;timers[u]=u==0?60:17;injected=true;
  }
  if(d.done)break;need(!d.error,"unexpected error");tick();
 }
 need(d.done&&order.size()==jobs.size(),"starvation or lost task");need(!(restart||fault)||restarted,"restart not exercised");return order;
}
int main(int argc,char**argv){try{
 need(argc==2,"JSON path");
 std::vector<Job> mixed={{0,false},{0,false},{0,true},{0,true},{0,true},{0,true}};
 auto order=run(mixed);for(U n:order)std::cout<<n<<' ';std::cout<<std::endl;
 need(mixed[order[0]].dw&&mixed[order[1]].dw&&!mixed[order[2]].dw,"DW priority/fairness");
 run({{0,false},{0,false},{0,false}});run({{0,true},{0,true},{0,true},{0,true}});
 auto blocked=run({{0,false},{0,true}},1);need(blocked[0]==0,"blocked preferred class stalled normal work");
 run({{0,false},{0,true,0},{5,false,1},{0,true,-1,1}},-1,true);
 run(mixed,-1,false,true);run(mixed,-1,false,false,true);
 std::ofstream o(argv[1]);o<<"{\"status\":\"PASS\",\"control_only\":true,\"cases\":7,\"mixed_order\":[";for(U i=0;i<order.size();i++){if(i)o<<',';o<<order[i];}o<<"],\"coverage\":[\"DW preference\",\"bounded ordinary fairness\",\"single-class fallback\",\"blocked buffer fallback\",\"dependency/input gating\",\"clear restart\",\"fault recovery\"]}\n";
 std::cout<<"PASS priority control 7 cases\n";return 0;
 }catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
