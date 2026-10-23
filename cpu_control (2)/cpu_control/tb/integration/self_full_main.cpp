// Cycle-driven test harness only. CNN operators, dispatch, leases and bai SRAM
// all execute in the Verilated RTL. Shadow bytes are CHECKER state, never a
// memory responder; every input is transferred through the RTL CPU/IO ports.
#include "Vself_full_sim_top.h"
#include "verilated.h"
#include <array>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <memory>

#ifndef CNN_K3
#define CNN_K3 4
#endif
#ifndef CNN_K1
#define CNN_K1 2
#endif
#ifndef CNN_POST
#define CNN_POST 1
#endif
namespace fs=std::filesystem;
constexpr unsigned K3=CNN_K3,K1=CNN_K1,POSTS=CNN_POST,DW=K3+K1,POST=DW+1,ADD=POST+POSTS,PAD=ADD+1,NU=PAD+1;
using U64=uint64_t;using U32=uint32_t;using Bytes=std::vector<uint8_t>;
std::vector<U32> hexwords(const fs::path& p){std::ifstream f(p);if(!f)throw std::runtime_error("open "+p.string());std::vector<U32> a;U32 v;while(f>>std::hex>>v)a.push_back(v);return a;}
Bytes bytes(const fs::path& p){std::ifstream f(p,std::ios::binary|std::ios::ate);if(!f)throw std::runtime_error("open "+p.string());Bytes a(static_cast<size_t>(f.tellg()));f.seekg(0);f.read(reinterpret_cast<char*>(a.data()),a.size());return a;}
unsigned pop(U32 x){unsigned n=0;while(x){x&=x-1;++n;}return n;}
struct Unit {U64 active=0,work=0,wait=0,read_bytes=0,write_bytes=0,tasks=0;};
struct Pending {bool valid=false,write=false;U32 addr=0,n=0,data=0,expected=0;};
struct Frame {U64 begin=UINT64_MAX,commit=UINT64_MAX,first=UINT64_MAX,result=UINT64_MAX;unsigned next=0;bool active=false,seen=false;};
struct Wave {
 std::ofstream f;bool open=false;U64 origin=0,stop=0;
 void begin(const fs::path& p,U64 cycle,U64 length){f.open(p);open=true;origin=cycle;stop=cycle+length;
  f<<"$timescale 1ns $end\n$scope module cnn_full $end\n";
  const char* names[]={"unit_active","operator_work","mem_valid","mem_ready","mem_write","mem_response","frames_ready","result_valid","result_ready","completed_count"};
  for(unsigned i=0;i<10;i++)f<<"$var wire "<<(i<6?NU:i==6?4:i<9?1:11)<<" "<<char('!'+i)<<" "<<names[i]<<" $end\n";
  f<<"$upscope $end\n$enddefinitions $end\n";
 }
 void sample(U64 cycle,const Vself_full_sim_top& d){if(!open)return;if(cycle>stop){f.close();open=false;return;}
  f<<"#"<<(cycle-origin)*10<<"\n";U32 a[]={d.unit_active,d.operator_work,d.mem_valid,d.mem_ready,d.mem_write,d.mem_response,d.frames_ready,d.result_valid,d.result_ready,d.completed_count};
  for(unsigned i=0;i<10;i++){f<<'b';unsigned w=i<6?NU:i==6?4:i<9?1:11;for(int b=int(w)-1;b>=0;b--)f<<((a[i]>>b)&1);f<<' '<<char('!'+i)<<'\n';}
 }
};

class Bench {
public:
 std::unique_ptr<VerilatedContext> context=std::make_unique<VerilatedContext>();
 std::unique_ptr<Vself_full_sim_top> d=std::make_unique<Vself_full_sim_top>(context.get());
 fs::path data,out;std::string mode;
 std::vector<U32> info,im,cmd,tm,meta,node;
 Bytes memory,shadow,expected,images,written,outputs;
 std::vector<U64> writes_per_node,mac_per_node,launch_cycle,finish_cycle;
 std::array<Unit,NU> unit;std::array<Pending,NU> pending;
 std::array<bool,NU> held{};std::array<std::array<U32,4>,NU> fields{};
 std::array<Frame,4> frame{};
 std::array<U64,6> capacity_wait{},scan_wait{};
 unsigned nf=0,steps=0,nt=0,memsize=0,pace=80,send_frame=0,send_offset=0,send_wait=0;
 bool checking=false,commit_pending=false,reader_active=false,reader_pending=false,reader_done=false;
 unsigned reader_frame=0,reader_addr=0,reader_n=0,reader_offset=0,reader_wait=0;
 U64 cycle=0,absolute=0,maxcycles=10000000000ULL,checks=0,expanded=0,completed=0,allocs=0,releases=0,results=0;
 U64 multi_frame=0,multi_work=0,cross_work=0,multi_k3=0,input_mac=0,input_work=0,io_work=0,compute_cycle=0;
 unsigned peak_frames=0,peak_mac=0;bool captured_mac=false,captured_pipeline=false;
 Wave macwave,pipelinewave;std::ofstream events,progress;
 std::chrono::steady_clock::time_point begin_wall=std::chrono::steady_clock::now();
 Bench(fs::path a,fs::path b,std::string m,unsigned p,U64 limit):data(a),out(b),mode(m),pace(p),maxcycles(limit){
  info=hexwords(data/"info.hex");im=hexwords(data/"image_info.hex");cmd=hexwords(data/"commands.hex");tm=hexwords(data/"template_commands.hex");meta=hexwords(data/"template_meta.hex");node=hexwords(data/"node_info.hex");
  memory=bytes(data/"memory.bin");shadow=memory;expected=bytes(data/"expected.bin");images=bytes(data/"images.bin");
  need(info.size()==40,"info header + 16 guards");nf=info[0];steps=info[1];nt=info[2];memsize=info[3];
  need(nf>=1&&nf<=4&&steps<=256&&nt==nf*steps&&nt<=1024,"fixture dimensions");
  need(memsize<=16777216&&memory.size()==info[4]&&expected.size()==info[5]&&images.size()==info[7],"fixture sizes");
  need(cmd.size()==nt*16&&node.size()==nt*4&&tm.size()==steps*16&&meta.size()==steps*18&&im.size()==nf*5,"fixture tables");
  shadow.resize(memsize,0xa5);written.resize(expected.size());writes_per_node.resize(nt);mac_per_node.resize(nt);launch_cycle.resize(nt,UINT64_MAX);finish_cycle.resize(nt,UINT64_MAX);
  size_t final_size=0;for(unsigned f=0;f<nf;f++)final_size+=node[((steps-1)*nf+f)*4+1];outputs.resize(final_size);
  fs::create_directories(out);events.open(out/"events.csv");events<<"cycle,event,unit,node,frame\n";
  progress.open(out/"progress.jsonl");d->rst_n=0;d->clear=0;d->start=0;d->template_valid=0;d->address_valid=0;d->frame_valid=0;d->result_ready=0;
  d->io_mem_req=0;d->io_mem_we=0;d->io_mem_addr=0;d->io_mem_wdata=0;d->io_mem_be=0;
  d->dmem_we=0;d->dmem_re=0;d->dmem_addr=0;d->dmem_wdata=0;d->dmem_wstrb=0;
  d->image_count=nf;d->unit_enable=(1u<<NU)-1;send_wait=pace;
 }
 void need(bool c,const std::string& message){if(!c){std::ostringstream s;s<<message<<" at cycle="<<cycle<<" completed="<<completed;throw std::runtime_error(s.str());}}
 void need(bool c,const char* message){if(!c)need(false,std::string(message));}
 double seconds()const{return std::chrono::duration<double>(std::chrono::steady_clock::now()-begin_wall).count();}
 unsigned unit_node(unsigned k)const{constexpr unsigned IW=10;unsigned bit=k*IW;U64 v=d->unit_node[bit/32];if(bit%32+IW>32)v|=U64(d->unit_node[bit/32+1])<<32;return unsigned((v>>(bit%32))&1023);}
 U32 word(const Bytes& a,unsigned address,unsigned n)const{U32 v=0;for(unsigned b=0;b<n;b++)v|=U32(a[address+b])<<(b*8);return v;}
 unsigned kind(unsigned k)const{return k<K3?0:k<DW?5:k==DW?3:k<ADD?1:k==ADD?2:4;}
 void event(const char* e,int u,int n,unsigned f){events<<cycle<<','<<e<<','<<u<<','<<n<<','<<im[f*5+4]<<'\n';}
 void tick(bool run=false){
  d->clk=0;d->eval();if(run)observe();
  d->clk=1;d->eval();context->timeInc(10);++absolute;if(run)++cycle;
  need(!context->gotFinish(),"RTL stopped unexpectedly");
 }
 void initialise(){
  for(unsigned i=0;i<4;i++)tick();d->rst_n=1;tick();
  if(mode=="preloaded")for(unsigned f=0;f<nf;f++)for(unsigned b=0;b<im[f*5+1];b++)memory[im[f*5]+b]=shadow[im[f*5]+b]=images[im[f*5+2]+b];
  // Actual port A writes, not hierarchical memory assignment.
  for(unsigned a=0;a<memory.size();a+=4){d->dmem_we=1;d->dmem_wstrb=15;d->dmem_addr=a;d->dmem_wdata=word(memory,a,4);tick();}
  d->dmem_we=0;d->dmem_wstrb=0;tick();
  for(unsigned s=0;s<steps;s++){
   need(d->configuration_ready,"configuration unavailable");d->template_valid=1;d->template_index=s;
   for(unsigned w=0;w<16;w++)d->template_command[w]=tm[s*16+w];
   const U32* a=&meta[s*18];d->template_source_modes=a[0];d->template_dep_valid=a[1];d->template_dep0=a[2];d->template_dep1=a[3];d->template_allocate_slot=a[4];
   for(unsigned w=0;w<8;w++)d->template_hold_mask[w]=a[5+w];
   d->template_use_valid=a[13];d->template_use_slots=a[14];d->template_use_owners=a[15];d->template_result_valid=a[16];d->template_result_bytes=a[17];tick();
  }
  d->template_valid=0;
  for(unsigned f=0;f<nf;f++){d->address_valid=1;d->address_slot=f;d->image_base=im[f*5];d->workspace_base=im[f*5+3];d->address_frame=im[f*5+4];tick();}
  d->address_valid=0;d->start=1;tick();d->start=0;checking=true;begin_wall=std::chrono::steady_clock::now();
 }
 void drive(){
  d->dmem_we=0;d->dmem_re=0;d->dmem_wstrb=0;
  if(mode=="stress"&&cycle%11<5&&d->mem_valid){for(unsigned k=0;k<NU;k++)if((d->mem_valid>>k)&1){d->dmem_re=1;d->dmem_addr=d->mem_addr[k]&~3u;break;}}
  if(mode=="preloaded"&&send_frame<nf&&!commit_pending){commit_pending=true;frame[send_frame].begin=cycle;}
  d->frame_valid=commit_pending&&send_frame<nf;d->frame_slot=send_frame&3;d->frame_id=send_frame<nf?im[send_frame*5+4]:0;
  d->result_ready=reader_active&&reader_done;
  bool read=reader_active&&!reader_pending&&!reader_done&&reader_wait==0;
  bool write=mode!="preloaded"&&send_frame<nf&&!commit_pending&&send_wait==0&&!reader_pending&&(mode!="serial"||send_frame==0||frame[send_frame-1].seen);
  d->io_mem_req=read||write;d->io_mem_we=!read;d->io_mem_addr=0;d->io_mem_wdata=0;d->io_mem_be=0;
  if(read)d->io_mem_addr=reader_addr+reader_offset;
  else if(write){d->io_mem_addr=im[send_frame*5]+send_offset;for(unsigned b=0;b<4&&send_offset+b<im[send_frame*5+1];b++){d->io_mem_be|=1u<<b;d->io_mem_wdata|=U32(images[im[send_frame*5+2]+send_offset+b])<<(8*b);}}
 }
 void observe(){
  need(!d->error&&!d->memory_fault&&!d->cancel,"CNN error/cancel");
  if(d->debug_program_valid&&d->debug_program_ready){unsigned n=d->debug_program_index;need(n==expanded&&n<nt,"expanded command index");for(unsigned w=0;w<16;w++)need(d->debug_program_command[w]==cmd[n*16+w],"expanded command contents node "+std::to_string(n)+" word "+std::to_string(w));expanded++;}
  if(send_wait)send_wait--;if(reader_wait)reader_wait--;
  if(d->frame_valid&&d->frame_ready){frame[send_frame].commit=cycle;event("input_commit",-1,-1,send_frame);send_frame++;send_offset=0;send_wait=pace;commit_pending=false;}
  if(d->io_mem_req&&d->io_mem_gnt){
   need(!d->io_mem_error,"IO grant fault");
   if(d->io_mem_we){
    need(send_frame<nf,"input beyond batch");if(!send_offset){frame[send_frame].begin=cycle;event("input_begin",-1,-1,send_frame);}
    if(d->operator_work)io_work++;
    for(unsigned b=0;b<4;b++)if((d->io_mem_be>>b)&1)shadow[d->io_mem_addr+b]=uint8_t(d->io_mem_wdata>>(8*b));
    if(send_offset+4>=im[send_frame*5+1])commit_pending=true;else{send_offset+=4;send_wait=pace;}
   }else reader_pending=true;
  }
  if(reader_active&&!d->result_accept)need(d->result_valid&&d->result_frame==im[reader_frame*5+4]&&d->result_addr==reader_addr&&d->result_bytes==reader_n,"held result descriptor changed");
  if(d->result_valid&&!reader_active){
   unsigned f=0;while(f<nf&&im[f*5+4]!=d->result_frame)++f;need(f<nf,"unexpected result frame");unsigned n=(steps-1)*nf+f;
   need(!frame[f].seen&&d->result_error==0&&d->result_addr==node[n*4]&&d->result_bytes==node[n*4+1],"result descriptor mismatch");
   reader_active=true;reader_done=false;reader_pending=false;reader_frame=f;reader_addr=d->result_addr;reader_n=d->result_bytes;reader_offset=0;reader_wait=mode=="stress"?30000:40;
  }
  if(d->io_mem_rvalid){
   need(reader_pending&&!d->io_mem_error,"unsolicited IO response");unsigned n=(steps-1)*nf+reader_frame;
   size_t target=0;for(unsigned f=0;f<reader_frame;f++)target+=node[((steps-1)*nf+f)*4+1];
   for(unsigned b=0;b<4&&reader_offset+b<reader_n;b++){uint8_t value=uint8_t(d->io_mem_rdata>>(8*b));need(value==expected[node[n*4+2]+reader_offset+b],"final SRAM result mismatch");outputs[target+reader_offset+b]=value;}
   reader_pending=false;reader_offset+=4;if(reader_offset>=reader_n)reader_done=true;
  }
  if(d->result_valid&&d->result_ready){need(reader_done,"premature result ACK");frame[reader_frame].seen=true;frame[reader_frame].result=cycle;results++;event("result_ack",-1,-1,reader_frame);}
  if(d->result_accept){reader_active=false;reader_done=false;}
  U32 active_frames=0,work_frames=0,work_kinds=0;unsigned k3work=0;
  for(unsigned k=0;k<NU;k++){
   unsigned n=unit_node(k);bool active=(d->unit_active>>k)&1,work=(d->operator_work>>k)&1,valid=(d->mem_valid>>k)&1,ready=(d->mem_ready>>k)&1,response=(d->mem_response>>k)&1,write=(d->mem_write>>k)&1,byte=(d->mem_byte>>k)&1;
   if(active){need(n<nt,"active node bounds");active_frames|=1u<<(n%nf);}if(work){need(n<nt,"work node bounds");work_frames|=1u<<(n%nf);work_kinds|=1u<<kind(k);unit[k].work++;if(k<K3)k3work++;if(k<=DW)mac_per_node[n]+=k==DW?8:1;}
   if((d->operator_busy>>k)&1)unit[k].active++;
   std::array<U32,4> now={U32(write),U32(byte),d->mem_addr[k],d->mem_wdata[k]};
   if(held[k])need(valid&&fields[k]==now,"stalled CNN request changed");held[k]=valid&&!ready;fields[k]=now;if(held[k])unit[k].wait++;
   if(response){need(pending[k].valid,"unsolicited CNN response");if(!pending[k].write&&d->mem_rdata[k]!=pending[k].expected)need(false,"SRAM read response/shadow mismatch unit "+std::to_string(k)+" address "+std::to_string(pending[k].addr));pending[k].valid=false;}
   if(valid&&ready){
    need(active&&!pending[k].valid,"invalid/multiple outstanding request");need(frame[n%nf].commit!=UINT64_MAX,"CNN accessed an uncommitted input");unsigned a=d->mem_addr[k],len=byte?1:4;need(U64(a)+len<=shadow.size()&&(byte||a%4==0),"SRAM address/alignment");
    pending[k]={true,write,a,len,d->mem_wdata[k],0};
    if(write){
     unsigned base=node[n*4],size=node[n*4+1],off=node[n*4+2];need(a>=base&&U64(a)+len<=U64(base)+size,"output range");
     for(unsigned b=0;b<len;b++){size_t pos=size_t(off)+a-base+b;need(pos<expected.size()&&!written[pos],"duplicate/outside output byte");uint8_t value=uint8_t(d->mem_wdata[k]>>(8*b));if(value!=expected[pos]){std::ostringstream e;e<<"arithmetic mismatch node="<<n<<" byte="<<a-base+b<<" got="<<unsigned(value)<<" expected="<<unsigned(expected[pos]);need(false,e.str());}written[pos]=1;shadow[a+b]=value;checks++;writes_per_node[n]++;}
     unit[k].write_bytes+=len;
    }else{U32 value=word(shadow,a,len);pending[k].expected=byte?U32(int32_t(int8_t(value))):value;unit[k].read_bytes+=len;}
   }
   if((d->unit_start>>k)&1){need(n<nt&&launch_cycle[n]==UINT64_MAX,"duplicate launch");need(cmd[n*16]==kind(k),"RTL/C++ pool configuration mismatch");unsigned f=n%nf;need(frame[f].commit!=UINT64_MAX&&n/nf==frame[f].next&&!frame[f].active,"frame dependency/order");frame[f].active=true;if(frame[f].first==UINT64_MAX)frame[f].first=cycle;launch_cycle[n]=cycle;unit[k].tasks++;event("launch",k,n,f);}
   if((d->completion_pulse>>k)&1){
    need(n<nt&&finish_cycle[n]==UINT64_MAX&&!pending[k].valid&&!valid,"completion before drained response");need(writes_per_node[n]==node[n*4+1],"incomplete output coverage");
    unsigned f=n%nf;frame[f].active=false;frame[f].next++;finish_cycle[n]=cycle;completed++;event("done",k,n,f);
    const U32* c=&cmd[n*16];U64 wantmac=0;if(c[0]==0||c[0]==5||c[0]==3){unsigned kernel=c[0]==0?3:c[0]==5?1:7;unsigned stride=c[0]==3?1:c[10];unsigned channels=c[6],co=c[0]==3?channels:c[9];wantmac=U64((c[7]-kernel)/stride+1)*((c[8]-kernel)/stride+1)*co*kernel*kernel*((c[0]==3||c[11])?1:channels);}
    need(mac_per_node[n]==wantmac,"MAC count mismatch node "+std::to_string(n));
    double wall=seconds();progress<<"{\"cycle\":"<<cycle<<",\"completed\":"<<completed<<",\"node\":"<<n<<",\"frame\":"<<im[f*5+4]<<",\"wall_seconds\":"<<wall<<"}\n";progress.flush();events.flush();
    std::cout<<"DONE "<<completed<<'/'<<nt<<" node="<<n<<" op="<<c[0]<<" cycle="<<cycle<<" wall="<<wall<<"s\n"<<std::flush;
   }
  }
  if(pop(active_frames)>1)multi_frame++;if(pop(work_frames)>1)multi_work++;if(pop(work_kinds)>1)cross_work++;if(k3work>1)multi_k3++;
  peak_frames=std::max(peak_frames,pop(active_frames));peak_mac=std::max(peak_mac,k3work);
  if(send_frame>0&&send_frame<nf&&frame[send_frame].begin!=UINT64_MAX&&!commit_pending){if(d->operator_work)input_work++;if(d->operator_work&((1u<<(DW+1))-1))input_mac++;}
  for(unsigned f=0;f<nf;f++)if(frame[f].commit!=UINT64_MAX&&!frame[f].active&&frame[f].next<steps){unsigned op=cmd[(frame[f].next*nf+f)*16];bool free=false;for(unsigned k=0;k<NU;k++)if(kind(k)==op&&!((d->unit_active>>k)&1)&&!((d->operator_busy>>k)&1))free=true;(free?scan_wait:capacity_wait)[op]++;}
  allocs+=pop(d->buffer_allocate);releases+=pop(d->buffer_release);need((d->buffer_release&d->external_hold)==0,"release before external ACK");
  if(d->compute_done&&!compute_cycle)compute_cycle=cycle;
  if(!captured_mac&&pop(work_frames)>1&&pop(d->operator_work&((1u<<(DW+1))-1))>1){macwave.begin(out/"mac_detail.vcd",cycle,256);captured_mac=true;}
  if(!captured_pipeline&&pop(work_kinds)>1&&pop(work_frames)>1){pipelinewave.begin(out/"pipeline_detail.vcd",cycle,256);captured_pipeline=true;}
  macwave.sample(cycle,*d);pipelinewave.sample(cycle,*d);
 }
 void verify_cpu_word(unsigned a,U32 want){d->dmem_re=1;d->dmem_addr=a;tick();need(d->dmem_rdata==want,"final SRAM guard/readonly mismatch address "+std::to_string(a));d->dmem_re=0;tick();}
 void run(){
  initialise();while(!d->done){need(cycle<maxcycles,"cycle watchdog");drive();tick(true);}
  d->io_mem_req=0;d->frame_valid=0;d->result_ready=0;d->dmem_re=0;checking=false;
  need(completed==nt&&expanded==nt&&checks==expected.size()&&allocs==nt&&releases==nt&&results==nf,"batch totals");for(auto& p:pending)need(!p.valid,"undrained request");
  for(unsigned f=0;f<nf;f++)need(frame[f].seen&&frame[f].first>frame[f].commit&&frame[f].result>frame[f].first,"frame lifecycle");
  if(nf>1&&mode!="serial")need(multi_work&&cross_work,"missing real multi-frame compute overlap");if(mode=="serial")need(multi_frame==0,"serial baseline overlapped frames");
  double simulation=seconds();
  // Check actual SRAM readonly and tail guards through port A after timing ends.
  for(unsigned a=0;a<info[6];a+=4)verify_cpu_word(a,word(shadow,a,4));
  for(unsigned s=0;s<16;s++){unsigned base=info[8+2*s],size=info[9+2*s];need(size>=64&&U64(base)+size<=memsize,"guard plan");for(unsigned a=base+size-64;a<base+size;a+=4)verify_cpu_word(a,0xa5a5a5a5u);}
  std::ofstream output(out/"outputs.bin",std::ios::binary);output.write(reinterpret_cast<const char*>(outputs.data()),outputs.size());output.close();
  std::ofstream m(out/"metrics.json");U64 macs=0;for(auto v:mac_per_node)macs+=v;
  m<<"{\"status\":\"PASS\",\"mode\":\""<<mode<<"\",\"cycles\":"<<cycle<<",\"compute_done_cycle\":"<<compute_cycle<<",\"commands\":"<<completed<<",\"expanded_commands\":"<<expanded<<",\"checked_bytes\":"<<checks<<",\"macs\":"<<macs<<",\"allocations\":"<<allocs<<",\"releases\":"<<releases<<",\"results\":"<<results<<",\"simulation_seconds\":"<<simulation<<",\"multi_frame_cycles\":"<<multi_frame<<",\"multi_frame_work_cycles\":"<<multi_work<<",\"cross_operator_work_cycles\":"<<cross_work<<",\"multi_k3_mac_cycles\":"<<multi_k3<<",\"peak_active_frames\":"<<peak_frames<<",\"peak_simultaneous_k3_mac\":"<<peak_mac<<",\"input_mac_cycles\":"<<input_mac<<",\"input_compute_cycles\":"<<input_work<<",\"input_write_compute_cycles\":"<<io_work<<",\"frames\":[";
  for(unsigned f=0;f<nf;f++){if(f)m<<',';m<<"{\"frame\":"<<im[f*5+4]<<",\"input_begin\":"<<frame[f].begin<<",\"input_commit\":"<<frame[f].commit<<",\"first_launch\":"<<frame[f].first<<",\"read_complete\":"<<frame[f].result<<'}';}
  m<<"],\"units\":[";for(unsigned k=0;k<NU;k++){if(k)m<<',';auto& u=unit[k];m<<"{\"unit\":"<<k<<",\"kind\":"<<kind(k)<<",\"tasks\":"<<u.tasks<<",\"active_cycles\":"<<u.active<<",\"work_cycles\":"<<u.work<<",\"read_bytes\":"<<u.read_bytes<<",\"write_bytes\":"<<u.write_bytes<<",\"arbitration_wait_cycles\":"<<u.wait<<'}';}
  m<<"],\"capacity_wait_by_opcode\":[";for(unsigned k=0;k<6;k++){if(k)m<<',';m<<capacity_wait[k];}m<<"],\"scan_wait_by_opcode\":[";for(unsigned k=0;k<6;k++){if(k)m<<',';m<<scan_wait[k];}m<<"],\"pool\":{\"K3\":"<<K3<<",\"K1\":"<<K1<<",\"Post\":"<<POSTS<<",\"Add\":1,\"DW7\":1,\"Pad\":1}}\n";
  std::cout<<"PASS SELF_FULL frames="<<nf<<" tasks="<<completed<<" cycles="<<cycle<<" checked="<<checks<<" macs="<<macs<<" simulation="<<simulation<<"s\n"<<std::flush;
 }
};
int main(int argc,char** argv){
 try{if(argc<4)throw std::runtime_error("usage: simulator DATA OUT overlap|serial|preloaded|stress [pace] [maxcycles]");Bench b(argv[1],argv[2],argv[3],argc>4?std::stoul(argv[4]):80,argc>5?std::stoull(argv[5]):10000000000ULL);b.run();return 0;}
 catch(const std::exception& e){std::cerr<<"FAIL SELF_FULL "<<e.what()<<'\n'<<std::flush;return 1;}
}
