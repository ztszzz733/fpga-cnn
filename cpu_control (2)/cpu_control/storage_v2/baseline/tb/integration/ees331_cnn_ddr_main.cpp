// Actual compact CNN, cache and AXI3 RTL. The PS/DDR test model never uses golden
// outputs as memory responses. Golden bytes only check real CNN writes/results.
#include "Vees331_cnn_ddr_sim_top.h"
#include "verilated.h"
#include "ees331_axi_ddr_model.hpp"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <memory>
#include <chrono>
#include <algorithm>
namespace fs=std::filesystem;
using U32=uint32_t;using U64=uint64_t;using Bytes=std::vector<uint8_t>;
constexpr unsigned NU=10,K3=2,DW=6,POST=7,ADD=8,PAD=9;
std::vector<U32> hexwords(const fs::path& p){std::ifstream f(p);if(!f)throw std::runtime_error("open "+p.string());std::vector<U32>a;U32 x;while(f>>std::hex>>x)a.push_back(x);return a;}
Bytes bytes(const fs::path& p){std::ifstream f(p,std::ios::binary|std::ios::ate);if(!f)throw std::runtime_error("open "+p.string());Bytes b(size_t(f.tellg()));f.seekg(0);f.read(reinterpret_cast<char*>(b.data()),b.size());return b;}
unsigned pop(U32 x){unsigned n=0;while(x){x&=x-1;++n;}return n;}
struct Pending{bool valid=false,write=false;U32 addr=0,expected=0;};
struct Frame{U64 commit=UINT64_MAX,first=UINT64_MAX,result=UINT64_MAX;unsigned next=0;bool active=false,seen=false;};
class Bench{
public:
 std::unique_ptr<VerilatedContext> ctx=std::make_unique<VerilatedContext>();
 std::unique_ptr<Vees331_cnn_ddr_sim_top> d=std::make_unique<Vees331_cnn_ddr_sim_top>(ctx.get());
 AxiDdr<Vees331_cnn_ddr_sim_top> bus{*d};
 fs::path data,out;std::string mode;
 std::vector<U32> info,im,cmd,tm,meta,node;
 Bytes initial,shadow,expected,images,written,outputs;
 std::vector<U64> write_count,mac_count,launched,finished;
 std::array<Pending,NU> pending{};std::array<Frame,4> frame{};
 std::array<bool,NU> held{};std::array<std::array<U32,4>,NU> held_payload{};
 std::array<U64,NU> wait{},work{},active{},reads{},writes{};
 unsigned nf=0,steps=0,nt=0,send_frame=0,send_offset=0,pace=80,send_wait=0;
 unsigned result_phase=0,result_f=0,result_wait=0;U32 result_a=0,result_n=0;
 U64 cycle=0,absolute=0,checks=0,completed=0,allocs=0,releases=0,results=0,compute_cycle=0;
 U64 multi_active=0,multi_work=0,cross_work=0,input_work=0;unsigned peak_frames=0;
 bool check=false,commit_pending=false;
 std::ofstream events,progress;
 std::chrono::steady_clock::time_point started=std::chrono::steady_clock::now();
 Bench(fs::path a,fs::path b,std::string m,unsigned p):data(a),out(b),mode(m),pace(p){
  info=hexwords(data/"info.hex");im=hexwords(data/"image_info.hex");cmd=hexwords(data/"commands.hex");tm=hexwords(data/"template_commands.hex");meta=hexwords(data/"template_meta.hex");node=hexwords(data/"node_info.hex");
  initial=bytes(data/"memory.bin");expected=bytes(data/"expected.bin");images=bytes(data/"images.bin");
  need(info.size()==40,"info header");nf=info[0];steps=info[1];nt=info[2];
  need(nf>=1&&nf<=4&&steps<=256&&nt==nf*steps&&initial.size()==info[4]&&expected.size()==info[5],"fixture dimensions");
  need(cmd.size()==nt*16&&tm.size()==steps*16&&meta.size()==steps*18&&node.size()==nt*4&&im.size()==nf*5,"fixture tables");
  shadow=initial;shadow.resize(16777216,0xa5);bus.data=shadow;written.resize(expected.size());
  write_count.resize(nt);mac_count.resize(nt);launched.resize(nt,UINT64_MAX);finished.resize(nt,UINT64_MAX);
  size_t n=0;for(unsigned f=0;f<nf;f++)n+=node[((steps-1)*nf+f)*4+1];outputs.resize(n);
  bus.stress=mode=="stress";fs::create_directories(out);events.open(out/"events.csv");events<<"cycle,event,unit,node,frame\n";progress.open(out/"progress.jsonl");
  d->clk=0;d->rst_n=0;d->clear=0;d->start=0;d->template_valid=0;d->address_valid=0;d->frame_valid=0;d->result_ready=0;
  d->cache_csr_re=0;d->cache_csr_we=0;d->cache_csr_addr=0;d->cache_csr_wdata=0;
  d->image_count=nf;d->unit_enable=1023;send_wait=pace;
 }
 void need(bool c,const std::string&s){if(!c)throw std::runtime_error(s+" cycle="+std::to_string(cycle)+" completed="+std::to_string(completed));}
 double seconds(){return std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count();}
 U32 word(const Bytes&b,unsigned a,unsigned n){U32 v=0;for(unsigned k=0;k<n;k++)v|=U32(b.at(a+k))<<(8*k);return v;}
 unsigned kind(unsigned k){return k<K3?0:k<DW?5:k==DW?3:k==POST?1:k==ADD?2:4;}
 unsigned uid(unsigned k){unsigned bit=k*10;U64 v=d->unit_node[bit/32];if(bit%32+10>32)v|=U64(d->unit_node[bit/32+1])<<32;return unsigned((v>>(bit%32))&1023);}
 void event(const char*s,int u,int n,unsigned f){events<<cycle<<','<<s<<','<<u<<','<<n<<','<<im[f*5+4]<<'\n';}
 void tick(){
  bus.drive();d->clk=0;d->eval();if(check)observe();if(d->rst_n)bus.capture();
  d->clk=1;d->eval();ctx->timeInc(10);++absolute;if(check)++cycle;
  need(!ctx->gotFinish(),"unexpected RTL finish");
 }
 void csr_write(U32 a,U32 v){d->cache_csr_addr=a;d->cache_csr_wdata=v;d->cache_csr_we=1;tick();d->cache_csr_we=0;tick();}
 U32 csr_read(U32 a){d->cache_csr_addr=a;d->cache_csr_re=1;d->clk=0;d->eval();U32 v=d->cache_csr_rdata;d->cache_csr_re=0;return v;}
 void fence_all(){csr_write(8,0);csr_write(12,16777216);csr_write(4,1);for(unsigned t=0;;t++){need(t<20000000,"cache fence timeout");if(!(csr_read(0)&2))break;tick();}need(!(csr_read(0)&12),"cache fence error");}
 void init(){
  for(unsigned i=0;i<4;i++)tick();d->rst_n=1;tick();for(unsigned n=0;!(csr_read(0)&1);n++){need(n<100000,"cache init");tick();}
  if(mode=="preloaded")for(unsigned f=0;f<nf;f++)for(unsigned b=0;b<im[f*5+1];b++)bus.data[im[f*5]+b]=shadow[im[f*5]+b]=images[im[f*5+2]+b];
  // Protect weights/parameters; inputs are located after the final model byte.
  csr_write(0x10,im[0]);csr_write(0x14,1);
  for(unsigned s=0;s<steps;s++){
   need(d->configuration_ready,"template configuration ready");d->template_valid=1;d->template_index=s;
   for(unsigned w=0;w<16;w++)d->template_command[w]=tm[s*16+w];
   const U32*a=&meta[s*18];d->template_source_modes=a[0];d->template_dep_valid=a[1];d->template_dep0=a[2];d->template_dep1=a[3];d->template_allocate_slot=a[4];
   std::vector<unsigned> consumers;for(unsigned c=0;c<steps;c++)if(c!=s&&((a[5+c/32]>>(c%32))&1))consumers.push_back(c);
   need(consumers.size()<=2,"more than two terminal consumers");d->template_consumer_count=consumers.size();d->template_consumer0=consumers.empty()?0:consumers[0];d->template_consumer1=consumers.size()<2?0:consumers[1];
   d->template_use_valid=a[13];d->template_use_slots=a[14];d->template_use_owners=a[15];d->template_result_valid=a[16];d->template_result_bytes=a[17];tick();need(!d->error,"template rejected");
  }
  d->template_valid=0;
  for(unsigned f=0;f<nf;f++){d->address_valid=1;d->address_slot=f;d->image_base=im[f*5];d->workspace_base=im[f*5+3];d->address_frame=im[f*5+4];tick();}
  d->address_valid=0;d->start=1;tick();d->start=0;check=true;started=std::chrono::steady_clock::now();
 }
 void drive(){
  d->cache_csr_we=0;d->cache_csr_re=1;d->cache_csr_addr=0;d->frame_valid=0;d->result_ready=0;
  if(send_wait)--send_wait;
  if(send_frame<nf){
   if(mode=="preloaded")commit_pending=true;
   else if(!commit_pending&&!send_wait&&(mode!="serial"||send_frame==0||frame[send_frame-1].seen)){
    for(unsigned b=0;b<4&&send_offset+b<im[send_frame*5+1];b++){
     unsigned a=im[send_frame*5]+send_offset+b;bus.data[a]=shadow[a]=images[im[send_frame*5+2]+send_offset+b];
    }
    if(d->operator_work)input_work++;send_offset+=4;send_wait=pace;
    if(send_offset>=im[send_frame*5+1])commit_pending=true;
   }
   d->frame_valid=commit_pending;d->frame_slot=send_frame;d->frame_id=im[send_frame*5+4];
  }
  // Fence the held result through the actual cache CSR before PS reads DDR.
  if(result_phase==1){d->cache_csr_we=1;d->cache_csr_addr=8;d->cache_csr_wdata=result_a;++result_phase;}
  else if(result_phase==2){d->cache_csr_we=1;d->cache_csr_addr=12;d->cache_csr_wdata=result_n;++result_phase;}
  else if(result_phase==3){d->cache_csr_we=1;d->cache_csr_addr=4;d->cache_csr_wdata=1;++result_phase;}
  else if(result_phase==4){++result_phase;}
  else if(result_phase==6){if(result_wait)--result_wait;else d->result_ready=1;}
 }
 void observe(){
  need(!d->error&&!d->memory_fault&&!d->cancel,"CNN/cache error code="+std::to_string(d->error_code));
  if(d->frame_valid&&d->frame_ready){frame[send_frame].commit=cycle;event("input_commit",-1,-1,send_frame);++send_frame;send_offset=0;commit_pending=false;send_wait=pace;}
  if(d->result_valid&&result_phase==0){
   unsigned f=0;while(f<nf&&im[f*5+4]!=d->result_frame)++f;need(f<nf&&!frame[f].seen,"result descriptor frame");unsigned n=(steps-1)*nf+f;
   need(d->result_addr==node[n*4]&&d->result_bytes==node[n*4+1]&&d->result_error==0,"result address/length");result_f=f;result_a=d->result_addr;result_n=d->result_bytes;result_phase=1;
  }
  if(result_phase&&result_phase<7)need(d->result_valid&&d->result_frame==im[result_f*5+4]&&d->result_addr==result_a&&d->result_bytes==result_n,"held result changed");
  if(result_phase==5&&!(d->cache_csr_rdata&2)){
   need(!(d->cache_csr_rdata&12),"result fence failed");unsigned n=(steps-1)*nf+result_f;size_t target=0;for(unsigned f=0;f<result_f;f++)target+=node[((steps-1)*nf+f)*4+1];
   for(unsigned b=0;b<result_n;b++){uint8_t v=bus.data[result_a+b];need(v==expected[node[n*4+2]+b],"final physical DDR readback mismatch");outputs[target+b]=v;}
   event("result_ddr_read",-1,n,result_f);result_phase=6;result_wait=mode=="stress"?30000:40;
  }
  if(d->result_valid&&d->result_ready){need(result_phase==6,"ACK before DDR read");frame[result_f].seen=true;frame[result_f].result=cycle;++results;event("result_ack",-1,-1,result_f);result_phase=7;}
  if(d->result_accept)result_phase=0;
  U32 af=0,wf=0,wk=0;
  for(unsigned k=0;k<NU;k++){
   unsigned n=uid(k);bool a=(d->unit_active>>k)&1,w=(d->operator_work>>k)&1,v=(d->mem_valid>>k)&1,r=(d->mem_ready>>k)&1,resp=(d->mem_response>>k)&1,wr=(d->mem_write>>k)&1,by=(d->mem_byte>>k)&1;
   if(a){need(n<nt,"active node bounds");af|=1u<<(n%nf);}
   if(w){need(n<nt,"work node bounds");wf|=1u<<(n%nf);wk|=1u<<kind(k);work[k]++;if(k<=DW)mac_count[n]+=k==DW?8:1;}
   if((d->operator_busy>>k)&1)active[k]++;
   std::array<U32,4> now={U32(wr),U32(by),d->mem_addr[k],d->mem_wdata[k]};need(!held[k]||(v&&now==held_payload[k]),"CNN stalled payload changed");held[k]=v&&!r;held_payload[k]=now;if(held[k])wait[k]++;
   if(resp){need(pending[k].valid,"unsolicited cache response");if(!pending[k].write)need(d->mem_rdata[k]==pending[k].expected,"cache read/shadow mismatch unit="+std::to_string(k)+" address="+std::to_string(pending[k].addr));pending[k].valid=false;}
   if(v&&r){
    need(a&&!pending[k].valid&&frame[n%nf].commit!=UINT64_MAX,"invalid request before frame commit");U32 addr=d->mem_addr[k],len=by?1:4;need(U64(addr)+len<=shadow.size()&&(by||!(addr&3)),"CNN memory bounds/alignment");
    pending[k]={true,wr,addr,0};
    if(wr){
     U32 base=node[n*4],size=node[n*4+1],off=node[n*4+2];need(addr>=base&&U64(addr)+len<=U64(base)+size,"operator output range");
     for(unsigned b=0;b<len;b++){size_t p=off+addr-base+b;need(p<expected.size()&&!written[p],"duplicate/outside output byte");uint8_t val=uint8_t(d->mem_wdata[k]>>(8*b));need(val==expected[p],"arithmetic mismatch node="+std::to_string(n)+" offset="+std::to_string(addr-base+b)+" got="+std::to_string(val)+" want="+std::to_string(expected[p]));written[p]=1;shadow[addr+b]=val;++checks;++write_count[n];}writes[k]+=len;
    }else{U32 val=word(shadow,addr,len);pending[k].expected=by?U32(int32_t(int8_t(val))):val;reads[k]+=len;}
   }
   if((d->unit_start>>k)&1){
    need(n<nt&&launched[n]==UINT64_MAX&&cmd[n*16]==kind(k),"duplicate/wrong launch");unsigned f=n%nf;need(frame[f].commit!=UINT64_MAX&&n/nf==frame[f].next&&!frame[f].active,"frame dependency order");
    for(unsigned j=0;j<16;j++)need(d->unit_command[k*16+j]==cmd[n*16+j],"relocated command mismatch node="+std::to_string(n)+" word="+std::to_string(j));
    frame[f].active=true;if(frame[f].first==UINT64_MAX)frame[f].first=cycle;launched[n]=cycle;event("launch",k,n,f);
   }
   if((d->completion_pulse>>k)&1){
    need(n<nt&&finished[n]==UINT64_MAX&&!pending[k].valid&&!v&&write_count[n]==node[n*4+1],"completion coverage/drain");unsigned f=n%nf;frame[f].active=false;frame[f].next++;finished[n]=cycle;++completed;event("done",k,n,f);
    const U32*c=&cmd[n*16];U64 mac=0;if(c[0]==0||c[0]==5||c[0]==3){unsigned ker=c[0]==0?3:c[0]==5?1:7,stride=c[0]==3?1:c[10],ch=c[6],co=c[0]==3?ch:c[9];mac=U64((c[7]-ker)/stride+1)*((c[8]-ker)/stride+1)*co*ker*ker*((c[0]==3||c[11])?1:ch);}
    need(mac_count[n]==mac,"MAC count node="+std::to_string(n));progress<<"{\"cycle\":"<<cycle<<",\"completed\":"<<completed<<",\"node\":"<<n<<",\"wall_seconds\":"<<seconds()<<"}\n";progress.flush();events.flush();
    std::cout<<"DONE "<<completed<<'/'<<nt<<" node="<<n<<" cycle="<<cycle<<" wall="<<seconds()<<"s\n"<<std::flush;
   }
  }
  if(pop(af)>1)++multi_active;if(pop(wf)>1)++multi_work;if(pop(wk)>1)++cross_work;peak_frames=std::max(peak_frames,pop(af));
  allocs+=pop(d->buffer_allocate);releases+=pop(d->buffer_release);need(!(d->buffer_release&d->external_hold),"released external result");if(d->compute_done&&!compute_cycle)compute_cycle=cycle;
 }
 void run(){
  init();while(!d->done){need(cycle<20000000000ULL,"cycle watchdog");drive();tick();}
  // done becomes true on the same edge that emits the final release pulse.
  // Observe that edge's registered notifications once before ending accounting.
  d->frame_valid=0;d->result_ready=0;d->cache_csr_we=0;tick();
  check=false;d->frame_valid=0;d->result_ready=0;d->cache_csr_we=0;d->cache_csr_re=0;
  const U64 batch_cycles=cycle;const double simulation=seconds();fence_all();
  need(completed==nt&&checks==expected.size()&&allocs==nt&&releases==nt&&results==nf,"batch totals checks="+std::to_string(checks)+" allocs="+std::to_string(allocs)+" releases="+std::to_string(releases)+" results="+std::to_string(results));for(auto&p:pending)need(!p.valid,"undrained client");
  for(unsigned f=0;f<nf;f++)need(frame[f].seen&&frame[f].first>frame[f].commit&&frame[f].result>frame[f].first,"frame lifecycle");
  if(mode=="serial")need(multi_active==0,"serial frames overlap");else need(multi_work&&peak_frames>1,"no real compute overlap");
  for(unsigned a=0;a<info[6];a++)need(bus.data[a]==shadow[a],"readonly/input DDR changed");
  for(unsigned s=0;s<16;s++){unsigned base=info[8+2*s],size=info[9+2*s];need(size>=64&&U64(base)+size<=info[3],"guard plan");for(unsigned a=base+size-64;a<base+size;a++)need(bus.data[a]==0xa5,"DDR tail guard overwritten");}
  // All physical memory now equals the independent cache-visible checker,
  // including overwritten intermediate buffers and untouched out-of-plan bytes.
  need(bus.data==shadow,"global physical DDR/shadow after fence");
  std::ofstream o(out/"outputs.bin",std::ios::binary);o.write(reinterpret_cast<const char*>(outputs.data()),outputs.size());o.close();
  U64 macs=0;for(auto n:mac_count)macs+=n;std::ofstream m(out/"metrics.json");
  m<<"{\"status\":\"PASS\",\"mode\":\""<<mode<<"\",\"cycles\":"<<batch_cycles<<",\"compute_done_cycle\":"<<compute_cycle<<",\"commands\":"<<completed<<",\"checked_bytes\":"<<checks<<",\"macs\":"<<macs<<",\"allocations\":"<<allocs<<",\"releases\":"<<releases<<",\"results\":"<<results<<",\"simulation_seconds\":"<<simulation<<",\"multi_frame_cycles\":"<<multi_active<<",\"multi_frame_work_cycles\":"<<multi_work<<",\"cross_operator_work_cycles\":"<<cross_work<<",\"peak_active_frames\":"<<peak_frames<<",\"input_write_compute_cycles\":"<<input_work<<",\"ddr_read_bursts\":"<<bus.read_bursts<<",\"ddr_write_bursts\":"<<bus.write_bursts<<",\"ddr_read_bytes\":"<<bus.read_bytes<<",\"ddr_write_bytes\":"<<bus.write_bytes<<",\"cache_hits\":"<<csr_read(0x20)<<",\"cache_misses\":"<<csr_read(0x24)<<",\"units\":[";
  for(unsigned k=0;k<NU;k++){if(k)m<<',';m<<"{\"unit\":"<<k<<",\"active_cycles\":"<<active[k]<<",\"work_cycles\":"<<work[k]<<",\"arbitration_wait_cycles\":"<<wait[k]<<",\"read_bytes\":"<<reads[k]<<",\"write_bytes\":"<<writes[k]<<'}';}m<<"]}\n";
  std::cout<<"PASS EES331_DDR tasks="<<completed<<" cycles="<<batch_cycles<<" checked="<<checks<<" macs="<<macs<<'\n';
 }
};
int main(int argc,char**argv){try{if(argc<4)throw std::runtime_error("DATA OUT MODE [PACE]");Bench b(argv[1],argv[2],argv[3],argc>4?std::stoul(argv[4]):80);b.run();return 0;}catch(const std::exception&e){std::cerr<<"FAIL EES331_DDR "<<e.what()<<'\n';return 1;}}
