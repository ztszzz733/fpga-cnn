// Cycle-driven RTL simulation. Host implements only SRAM/arbitration/checking;
// no host convolution, activation, padding, Add or intermediate tensor injection.
#include "Vquant_network_output.h"
#include "verilated.h"
#include <array>
#include <map>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <vector>
#include <string>

using Bytes=std::vector<uint8_t>;
Bytes load(const std::string& p){std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("missing "+p);return Bytes(std::istreambuf_iterator<char>(f),{});}
uint32_t word(const Bytes& v,size_t a){if(a+4>v.size())throw std::runtime_error("word outside SRAM");return uint32_t(v[a])|(uint32_t(v[a+1])<<8)|(uint32_t(v[a+2])<<16)|(uint32_t(v[a+3])<<24);}
struct Request{bool active=false,write=false,byte=false;uint32_t addr=0,data=0;};

int main(int argc,char** argv){
 try{
  if(argc<3)throw std::runtime_error("expected command_count mode");
  auto context=std::make_unique<VerilatedContext>();context->commandArgs(argc,argv);
  auto top=std::make_unique<Vquant_network_output>(context.get());
  auto mem=load("memory.bin"),jobs=load("jobs.bin"),regions=load("mutable.bin"),results=load("results.bin");
  auto lease=load("leases.bin"),expected=load("expected.bin"),expected_offsets=load("expected_offsets.bin");
  if(lease.size()!=jobs.size()/64*156)throw std::runtime_error("lease length");
  const auto original=mem;std::vector<bool> writable(mem.size(),false);
  for(size_t r=0;r<regions.size();r+=8){auto a=word(regions,r),n=word(regions,r+4);if(size_t(a)+n>mem.size())throw std::runtime_error("bad mutable range");for(size_t i=a;i<size_t(a)+n;i++)writable[i]=true;}
  unsigned total=std::stoul(argv[1]);unsigned mode=std::stoul(argv[2]);bool stall=mode==1;
  if(total==0 || total>1024 || jobs.size()!=total*64 || results.size()!=total*16 || expected_offsets.size()!=total*4 || regions.size()!=64)throw std::runtime_error("data sizes");
  top->task_count=total;top->engine_enable=3;
  std::array<Request,23> pending{};std::array<unsigned,4> rr{};
  uint64_t cycles=0,reads=0,writes=0,checked=0,completed=0,last_done=0;
  std::ofstream events("events.csv"),wave("control.vcd");
  events<<"cycle,command,layer,kind,checked_bytes,reads,writes,wall_seconds\n";
  const char* names[]={"active","operator_busy","unit_start","completion_pulse","completed_count","conv0_node","conv1_node","post_node","dw7_node","pad_node","done","error","buffer_live","buffer_release","buffer_allocate","wait_buffer","result_valid","result_ready","result_accept","result_frame","result_addr","result_bytes","external_hold","compute_done","outputs_pending"};
  wave<<"$timescale 1ns $end\n$scope module network $end\n";
  for(int i=0;i<25;i++)wave<<"$var wire 32 s"<<i<<" "<<names[i]<<" $end\n";
  wave<<"$upscope $end\n$enddefinitions $end\n";
  std::array<uint32_t,25> previous{};bool first=true;
  std::vector<bool> seen(total,false),launched(total,false);
  uint64_t allocations=0,releases=0,waiting=0;unsigned peak=0;
  std::array<unsigned,8> slotuses{};std::map<unsigned,Bytes> finals;
  std::map<unsigned,unsigned> result_nodes;uint64_t expected_allocations=0;
  for(unsigned j=0;j<total;j++){
   if(word(lease,j*156)!=0xffffffff)expected_allocations++;
   if(word(results,j*16)){
    unsigned tag=word(results,j*16+4);
    if(result_nodes.count(tag) || word(lease,j*156)==0xffffffff || word(results,j*16+8)!=word(jobs,j*64+40) || word(results,j*16+12)!=word(jobs,j*64+44))throw std::runtime_error("invalid result metadata");
    result_nodes[tag]=j;
   }
  }
  if(result_nodes.empty())throw std::runtime_error("no final result metadata");
  std::ofstream life("lifetime.csv");life<<"cycle,event,slot,owner\n";
  auto slot_owner=[&](unsigned slot){unsigned v=0;for(unsigned b=0;b<10;b++){unsigned bit=slot*10+b;v|=((top->buffer_owners[bit/32]>>(bit%32))&1)<<b;}return v;};
  uint64_t dual=0,convpost=0;std::array<unsigned,5> assignments{};
  std::ofstream launches("launches.csv");launches<<"cycle,unit,command,frame\n";
  bool reading=false;unsigned frame=0,readaddr=0,readbytes=0,readpos=0;
  uint64_t offered_at=0,accepted=0,reader_wait_cycles=0,progress_while_waiting=0,compute_finish_cycle=0;
  Bytes readout;std::map<unsigned,bool> acknowledged;unsigned result_node=0;
  std::ofstream handoffs("handoffs.csv");handoffs<<"cycle,event,frame,address,bytes,completed_count\n";
  auto started=std::chrono::steady_clock::now();
  while(!top->done){
   uint64_t local=cycles;
   top->clk=0;top->rst_n=local>=5;top->clear=0;top->start=local==total+12;top->memory_fault=0;
   top->program_valid=local>=10 && local<total+10;
   if(top->program_valid){unsigned j=local-10;top->program_index=j;
    for(unsigned k=0;k<16;k++)top->program_command[k]=word(jobs,j*64+k*4);
    auto a=word(jobs,j*64+56),b=word(jobs,j*64+60);
    top->program_dep_valid=(a!=0xffffffff ? 1:0)|(b!=0xffffffff ? 2:0);
    top->program_dep0=a&1023;top->program_dep1=b&1023;
    auto la=word(lease,j*156);top->program_allocate_valid=la!=0xffffffff;top->program_allocate_slot=la&7;
    top->program_result_valid=word(results,j*16);top->program_result_frame=word(results,j*16+4);
    top->program_result_addr=word(results,j*16+8);top->program_result_bytes=word(results,j*16+12);
    top->program_use_valid=0;top->program_use_slots=0;top->program_use_owners=0;
    for(unsigned k=0;k<3;k++){auto sl=word(lease,j*156+4+k*4),ow=word(lease,j*156+16+k*4);
     if(sl!=0xffffffff){top->program_use_valid|=1<<k;top->program_use_slots|=sl<<(k*3);top->program_use_owners|=ow<<(k*10);}}
    for(unsigned k=0;k<32;k++)top->program_hold_mask[k]=word(lease,j*156+28+k*4);
   }
   top->mem_ready=0;top->mem_response=0;
   for(int i=0;i<23;i++){
    top->mem_rdata[i]=0;auto r=pending[i];
    if(r.active){
     const unsigned n=r.byte?1:4;
     if(size_t(r.addr)+n>mem.size() || (!r.byte && (r.addr&3)))throw std::runtime_error("bad SRAM access at "+std::to_string(r.addr));
     if(r.write){
      for(unsigned sl=0;sl<8;sl++){auto a=word(regions,sl*8),len=word(regions,sl*8+4);if(r.addr>=a && r.addr<a+len && size_t(r.addr)+n>size_t(a)+len-64)throw std::runtime_error("write into slot guard");}
      for(unsigned b=0;b<n;b++){if(!writable[r.addr+b])throw std::runtime_error("immutable write at "+std::to_string(r.addr+b));mem[r.addr+b]=r.data>>(8*b);}writes++;}
     else{top->mem_rdata[i]=r.byte ? mem[r.addr]:word(mem,r.addr);reads++;}
     top->mem_response|=1<<i;
    }
   }
   top->result_ready=0;top->eval();
   // Model an external SRAM reader, not an arithmetic producer. It reads only
   // after valid, and acknowledges only after reading every byte. This direct
   // SRAM model does not claim system-bus bandwidth verification.
   if(top->result_valid){
    if(!reading){
     reading=true;frame=top->result_frame;readaddr=top->result_addr;readbytes=top->result_bytes;readpos=0;offered_at=cycles;readout.clear();
     if(!result_nodes.count(frame))throw std::runtime_error("unknown result frame");
     result_node=result_nodes.at(frame);
     if(acknowledged[frame] || !seen[result_node] || readbytes!=word(results,result_node*16+12) || top->result_error)throw std::runtime_error("bad result descriptor");
     if(readaddr!=word(jobs,result_node*64+40))throw std::runtime_error("bad result address");
     handoffs<<cycles<<",offer,"<<frame<<","<<readaddr<<","<<readbytes<<","<<completed<<"\n";
    }
    if(top->result_frame!=frame || top->result_addr!=readaddr || top->result_bytes!=readbytes)throw std::runtime_error("descriptor changed under backpressure");
    unsigned slot=word(lease,result_node*156);
    if(!(top->buffer_live&(1<<slot)) || !(top->external_hold&(1<<slot)) || slot_owner(slot)!=result_node)throw std::runtime_error("result ownership lost");
    if(cycles%64==0)for(unsigned k=0;k<readbytes;k++)if(mem.at(readaddr+k)!=expected.at(word(expected_offsets,result_node*4)+k))throw std::runtime_error("held result overwritten");
    if(!stall || (cycles-offered_at>=90000 && cycles%7==0)){
     for(unsigned k=0;k<4 && readpos<readbytes;k++,readpos++)readout.push_back(mem.at(readaddr+readpos));
    }
    top->result_ready=readpos==readbytes;
    if(!top->result_ready)reader_wait_cycles++;
   }else if(reading)throw std::runtime_error("descriptor disappeared without acknowledgement");
   std::array<Request,23> next{};
   if(top->rst_n && !top->cancel && (!stall || cycles%7!=3)){
    for(unsigned bank=0;bank<4;bank++)for(unsigned k=0;k<23;k++){
     unsigned i=(rr[bank]+k)%23;
     if((!stall || i>=10 || cycles%5==0) && (top->mem_valid&(1<<i)) && ((top->mem_addr[i]/4)%4==bank)){
      top->mem_ready|=1<<i;rr[bank]=(i+1)%23;
      next[i]={true,bool(top->mem_write&(1<<i)),bool(top->mem_byte&(1<<i)),top->mem_addr[i],top->mem_wdata[i]};break;
     }
    }
   }
   top->eval();top->clk=1;top->eval();pending=next;cycles++;context->timeInc(10);
   if(top->error)throw std::runtime_error("RTL error");
   if((top->operator_busy&3)==3)dual++;
   if((top->operator_busy&3) && (top->operator_busy&4))convpost++;
   for(unsigned u=0;u<5;u++){
    unsigned j=(top->unit_node>>(u*10))&1023;
    if(top->unit_start&(1<<u)){
     if(j>=total || launched[j])throw std::runtime_error("duplicate launch");
     auto a=word(jobs,j*64+56),b=word(jobs,j*64+60);
     if((a!=0xffffffff && !seen.at(a)) || (b!=0xffffffff && !seen.at(b)))throw std::runtime_error("early dependency");
     auto kind=word(jobs,j*64);unsigned expected=kind==0 ? u:(kind<=2 ? 2:kind);
     if((kind==0 && u>1) || u!=expected)throw std::runtime_error("wrong engine kind");
     launched[j]=true;assignments[u]++;launches<<cycles<<","<<u<<","<<j<<","<<word(jobs,j*64+52)<<"\n";
    }
    if(top->completion_pulse&(1<<u)){
     if(j>=total || !launched[j] || seen[j])throw std::runtime_error("duplicate/unlaunched completion");
     auto a=word(jobs,j*64+40),n=word(jobs,j*64+44);
     for(size_t b=0;b<n;b++)if(mem.at(a+b)!=expected.at(word(expected_offsets,j*4)+b))throw std::runtime_error("mismatch command="+std::to_string(j)+" addr="+std::to_string(a+b));
     if(reading && !top->result_ready)progress_while_waiting++;
     seen[j]=true;checked+=n;completed++;last_done=cycles;
     double wall=std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count();
     events<<cycles<<","<<j<<","<<word(jobs,j*64+48)<<","<<word(jobs,j*64)<<","<<n<<","<<reads<<","<<writes<<","<<wall<<"\n";events.flush();
     std::cout<<"DONE "<<completed<<"/"<<total<<" command="<<j<<" cycles="<<cycles<<" wall="<<wall<<std::endl;
    }
   }
   if(top->compute_done && !compute_finish_cycle)compute_finish_cycle=cycles;
   if(top->result_accept){
    if(!reading || !top->result_ready || readout.size()!=readbytes)throw std::runtime_error("ack before read complete");
    for(unsigned k=0;k<readbytes;k++)if(readout[k]!=expected.at(word(expected_offsets,result_node*4)+k))throw std::runtime_error("external output mismatch");
    finals[frame]=readout;acknowledged[frame]=true;accepted++;reading=false;
    handoffs<<cycles<<",read_complete,"<<frame<<","<<readaddr<<","<<readbytes<<","<<completed<<"\n";
   }
   std::array<uint32_t,25> now{top->unit_active,top->operator_busy,top->unit_start,top->completion_pulse,top->completed_count,
     uint32_t(top->unit_node&1023),uint32_t((top->unit_node>>10)&1023),uint32_t((top->unit_node>>20)&1023),
     uint32_t((top->unit_node>>30)&1023),uint32_t((top->unit_node>>40)&1023),top->done,top->error,top->buffer_live,top->buffer_release,top->buffer_allocate,top->wait_buffer,top->result_valid,top->result_ready,top->result_accept,top->result_frame,top->result_addr,top->result_bytes,top->external_hold,top->compute_done,top->outputs_pending};
   if(first || now!=previous){wave<<"#"<<cycles*10<<"\n";for(int i=0;i<25;i++)if(first || now[i]!=previous[i]){wave<<"b";for(int b=31;b>=0;b--)wave<<((now[i]>>b)&1);wave<<" s"<<i<<"\n";}previous=now;first=false;}
   waiting+=top->wait_buffer;unsigned live=0;for(unsigned b=0;b<8;b++)live+=(top->buffer_live>>b)&1;peak=std::max(peak,live);
   for(unsigned b=0;b<8;b++){
    if(top->buffer_allocate&(1<<b)){allocations++;slotuses[b]++;life<<cycles<<",allocate,"<<b<<","<<slot_owner(b)<<"\n";}
    if(top->buffer_release&(1<<b)){
     auto owner=slot_owner(b);
     if(word(results,owner*16) && !acknowledged[word(results,owner*16+4)])throw std::runtime_error("result released before external read complete");
     for(unsigned n=0;n<total;n++)if((lease[owner*156+28+n/8]>>(n%8))&1)if(!seen[n])throw std::runtime_error("early release of live consumer");
     unsigned a=word(regions,b*8),len=word(regions,b*8+4);
     for(auto req:pending)if(req.active && req.addr>=a && req.addr<a+len)throw std::runtime_error("release with pending access");
     // Host deliberately destroys freed data; it never generates operator results.
     std::fill(mem.begin()+a,mem.begin()+a+len,uint8_t(0xd7));
     releases++;life<<cycles<<",release,"<<b<<","<<owner<<"\n";
    }
   }
   if(cycles-last_done>10000000 || cycles>200000000)throw std::runtime_error("cycle watchdog at command "+std::to_string(completed));
  }
  if(completed!=total)throw std::runtime_error("incomplete command list");
  for(auto r:pending)if(r.active)throw std::runtime_error("early done with outstanding memory");
  for(size_t i=0;i<mem.size();i++)if(!writable[i] && mem[i]!=original[i])throw std::runtime_error("guard corruption");
  if((assignments[0]==0 || assignments[1]==0 || dual==0 || convpost==0))throw std::runtime_error("missing overlap");
  if(accepted!=result_nodes.size() || top->outputs_pending || reading)throw std::runtime_error("missing external results");
  if(!compute_finish_cycle || compute_finish_cycle>=cycles)throw std::runtime_error("compute/output completion not separated");
  if(stall && reader_wait_cycles<90000*result_nodes.size())throw std::runtime_error("slow reader pressure not exercised");
  std::ofstream output("outputs.bin",std::ios::binary);
  for(auto [tag,node]:result_nodes){auto &f=finals[tag];if(f.size()!=word(results,node*16+12))throw std::runtime_error("missing final frame");output.write(reinterpret_cast<char*>(f.data()),f.size());}output.close();
  if(top->buffer_live || allocations!=expected_allocations || releases!=expected_allocations)throw std::runtime_error("lease accounting");

  std::ofstream metrics("metrics.json");metrics<<"{\"cycles\":"<<cycles<<",\"commands\":"<<completed<<",\"checked_bytes\":"<<checked<<",\"dual_busy_cycles\":"<<dual<<",\"conv_post_busy_cycles\":"<<convpost<<",\"assignments\":[";
  for(int u=0;u<5;u++)metrics<<(u ? ",":"")<<assignments[u];metrics<<"],\"allocations\":"<<allocations<<",\"releases\":"<<releases<<",\"wait_buffer_cycles\":"<<waiting<<",\"peak_live_buffers\":"<<peak<<",\"accepted_results\":"<<accepted<<",\"reader_wait_cycles\":"<<reader_wait_cycles<<",\"completions_while_reader_waiting\":"<<progress_while_waiting<<",\"compute_finish_cycle\":"<<compute_finish_cycle<<"}\n";
  top->final();std::cout<<"PASS generic pair RTL checked="<<checked<<" cycles="<<cycles<<std::endl;return 0;
 }catch(const std::exception& e){std::cerr<<"FAIL "<<e.what()<<std::endl;return 1;}
}
