// Control-only tests. Operator delays deliberately model occupancy, not arithmetic.
#include "Vstream_dispatch.h"
#include "verilated.h"
#include <vector>
#include <array>
#include <iostream>
#include <fstream>
#include <stdexcept>
using U=unsigned;
void need(bool b,const char*s){if(!b)throw std::runtime_error(s);}
struct Job { U op=0,frame=0; int dep=-1; bool dw=false; };
struct Options { int blocked=-1,late=-1; bool restart=false,fault=false,recheck=false; };
struct Event { U node,unit,cycle; };
std::vector<Event> run(std::vector<Job> jobs,std::vector<U> commit_order,Options o={}) {
 Vstream_dispatch d; std::array<U,4> tags{700,900,100,500};
 auto tick=[&]{d.clk=1;d.eval();d.clk=0;d.eval();};
 d.rst_n=0;d.clear=0;d.start=0;d.memory_fault=0;d.program_valid=0;d.frame_valid=0;
 d.buffer_ready=0;d.unit_busy=0;d.unit_done=0;d.unit_error=0;d.unit_enable=63;tick();tick();d.rst_n=1;tick();
 U committed=0;
 auto load=[&]{
  d.buffer_ready=0; committed=0;
  for(U n=0;n<jobs.size();n++) {
   need(d.program_ready,"program not ready"); for(U k=0;k<16;k++)d.program_command[k]=0;
   auto j=jobs[n];d.program_command[0]=j.op;d.program_command[11]=j.dw;
   d.program_command[13]=tags[j.frame];d.program_command[14]=j.frame;
   d.program_index=n;d.program_dep_valid=j.dep>=0;d.program_dep0=j.dep>=0?j.dep:0;
   d.program_dep1=0;d.program_valid=1;tick();
  }
  d.program_valid=0;d.task_count=jobs.size();d.start=1;tick();d.start=0;
  for(U f:commit_order)if(int(f)!=o.late) {
   d.frame_slot=f;d.frame_id=tags[f];d.frame_valid=1;d.eval();need(d.frame_ready,"commit not ready");
   tick();committed|=1u<<f;
  }
  d.frame_valid=0;
 };
 load();std::vector<Event> events;std::array<int,6> timers{};std::array<U,6> owner{};
 U finished=0;bool restarted=false,rechecked=false,concurrent=false;
 for(U c=0;c<10000;c++) {
  if((o.restart||o.fault)&&!restarted&&!events.empty()) {
   if(o.fault){d.memory_fault=1;tick();need(d.cancel&&d.error,"fault not cancelled");d.memory_fault=0;}
   d.clear=1;tick();tick();d.clear=0;timers.fill(0);d.unit_busy=d.unit_done=0;
   events.clear();finished=0;tick();load();restarted=true;
  }
  // Observe starts from the previous rising edge before changing this cycle's gates.
  if(d.unit_start)for(U u=0;u<6;u++)if(d.unit_start&(1u<<u)) {
   U n=(d.unit_node>>(u*5))&31;need(n<jobs.size(),"node range");auto j=jobs[n];
   need(timers[u]==0,"preempted busy operator");
   need(j.dep<0||(finished&(1u<<j.dep)),"dependency violated");
   need(committed&(1u<<j.frame),"uncommitted input dispatched");
   for(auto e:events)need(e.node!=n,"duplicate dispatch");
   for(auto t:timers)if(t)concurrent=true;
   events.push_back({n,u,c});owner[u]=n;timers[u]=u==0?100:23;
  }
  d.frame_valid=o.late>=0&&c==180;
  if(d.frame_valid){d.frame_slot=o.late;d.frame_id=tags[o.late];d.eval();need(d.frame_ready,"late commit ready");}
  d.unit_busy=0;d.unit_done=0;
  for(U u=0;u<6;u++)if(timers[u]>0) {
   d.unit_busy|=1u<<u;
   if(--timers[u]==0){d.unit_busy&=~(1u<<u);d.unit_done|=1u<<u;finished|=1u<<owner[u];}
  }
  d.buffer_ready=!(int(d.candidate_node)==o.blocked&&c<160);d.eval();
  // Withdraw the buffer exactly in the chosen winner's issue cycle, then retry.
  if(o.recheck&&!rechecked&&d.reserve_commit) {
   d.buffer_ready=0;d.eval();need(!d.reserve_commit,"winner failed to recheck buffer");
   rechecked=true;
  }
  if(d.reserve_commit)need(!(int(d.candidate_node)==o.blocked&&c<160),"buffer bypass");
  if(d.done)break;need(!d.error,"unexpected error");
  bool accepted=d.frame_valid&&d.frame_ready;U slot=d.frame_slot;tick();
  if(accepted)committed|=1u<<slot;
 }
 need(d.done&&events.size()==jobs.size(),"starvation or lost task");
 need(!(o.restart||o.fault)||restarted,"recovery not exercised");
 need(!o.recheck||rechecked,"issue recheck not exercised");
 if(jobs.size()==3&&jobs[1].op==5)need(concurrent,"idle second pool was blocked");
 return events;
}
int main(int argc,char**argv){try{
 need(argc==2,"JSON output path");
 std::vector<Job> chain={{0,2},{0,0},{0,1,-1,true},{0,1,2,true},{0,2,0},{0,0,1}};
 auto a=run(chain,{1,2,0});std::vector<U> want{2,3,0,4,1,5};
 for(U i=0;i<want.size();i++)need(a[i].node==want[i],"not oldest committed frame first");
 auto b=run({{0,0},{0,1}},{0,1},Options{.blocked=0});need(b[0].node==1,"blocked old frame prevented progress");
 auto c=run({{0,0},{5,1},{0,0,0,true}},{0,1});need(c[0].node==0&&c[1].node==1,"idle other pool not used");
 auto e=run({{0,0},{0,1}},{0,1},Options{.late=0});need(e[0].node==1,"uncommitted old slot won");
 run(chain,{1,2,0},Options{.restart=true});run(chain,{1,2,0},Options{.fault=true});
 run(chain,{1,2,0},Options{.recheck=true});
 std::ofstream out(argv[1]);out<<"{\"status\":\"PASS\",\"control_only\":true,\"cases\":7,\"commit_order\":[1,2,0],\"launch_order\":[2,3,0,4,1,5],\"coverage\":[\"arrival order independent of slot and tag\",\"dependency and input gating\",\"blocked buffer fallback\",\"cross-pool concurrency\",\"non-preemption\",\"winner gate recheck\",\"clear and fault recovery\"]}\n";
 std::cout<<"PASS oldest-frame control 7 cases\n";return 0;
 }catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
