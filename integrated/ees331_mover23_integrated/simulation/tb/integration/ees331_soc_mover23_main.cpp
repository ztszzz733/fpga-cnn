#include "Vees331_soc_mover23_sim_top.h"
#include "verilated.h"
#include "ees331_axi_mover_model.hpp"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <algorithm>
#include <memory>
#include <chrono>
namespace fs=std::filesystem;
using U32=uint32_t;using U64=uint64_t;
static void need(bool c,const std::string&s){if(!c)throw std::runtime_error(s);}
static std::vector<U32> hex(const fs::path&p){std::ifstream f(p);need(bool(f),"missing "+p.string());std::vector<U32>v;U32 x;while(f>>std::hex>>x)v.push_back(x);return v;}
static std::vector<uint8_t> bin(const fs::path&p){std::ifstream f(p,std::ios::binary);need(bool(f),"missing "+p.string());return {std::istreambuf_iterator<char>(f),{}};}
struct Bench{
 Vees331_soc_mover23_sim_top d;AxiDdr<Vees331_soc_mover23_sim_top> ram{d};
 fs::path data,out;unsigned k1_bank=0;std::vector<U32> im,info,cmd,meta,nodes;
 std::vector<uint8_t> initial,images,expected,seen,outputs;
 U64 cycle=0,mac_overlap=0,work_overlap=0,checked=0,gp_reads=0,gp_writes=0,cpu_ram_reads=0,cpu_ram_writes=0;
 std::array<U64,23> unit_starts{};
 U32 seq=0,started=0,finished=0,peak_frames=0;bool check=false;
 std::vector<bool> launched,completed;
 explicit Bench(fs::path a,fs::path b,unsigned bank=0):data(a),out(b),k1_bank(bank){
  need(k1_bank<3,"K1 bank must be 0, 1, or 2");
  im=hex(data/"image_info.hex");info=hex(data/"info.hex");cmd=hex(data/"template_commands.hex");meta=hex(data/"template_meta.hex");nodes=hex(data/"node_info.hex");
  initial=bin(data/"memory.bin");images=bin(data/"images.bin");expected=bin(data/"expected.bin");seen.resize(expected.size());
  need(info[0]>=1 && info[0]<=4 && info[1]<=256,"fixture geometry");launched.resize(info[2]);completed.resize(info[2]);ram.stress=true;
  std::copy(initial.begin(),initial.end(),ram.data.begin());
  d.M_AXI_GP0_AWID=0x123;d.M_AXI_GP0_WID=0x123;d.M_AXI_GP0_ARID=0x456;
  d.M_AXI_GP0_AWSIZE=d.M_AXI_GP0_ARSIZE=2;d.M_AXI_GP0_AWBURST=d.M_AXI_GP0_ARBURST=1;
  d.M_AXI_GP0_WSTRB=15;d.M_AXI_GP0_WLAST=1;
  d.FCLK_RESET0_N=0;for(int i=0;i<5;i++)tick();d.FCLK_RESET0_N=1;
  for(int i=0;i<1200;i++)tick();
 }
 U32 node(unsigned k){unsigned bit=k*10,w=bit/32,shift=bit%32;U64 v=d.debug_node[w];if(w<7)v|=U64(d.debug_node[w+1])<<32;return U32(v>>shift)&1023;}
 void monitor(){
  if(!check)return;
  need(!d.debug_error&&!d.debug_fault,"CNN/MOVER error at cycle "+std::to_string(cycle));
  U32 workframes=0,macframes=0,activeframes=0;
  for(unsigned k=0;k<23;k++){
   unsigned n=node(k),f=n%info[0];
   if((d.debug_unit_active>>k)&1)activeframes|=1u<<f;
   if((d.debug_work>>k)&1){workframes|=1u<<f;if(k<17)macframes|=1u<<f;}
   if((d.debug_unit_start>>k)&1){need(n<launched.size()&&!launched[n],"duplicate node start");launched[n]=true;started++;unit_starts[k]++;}
   if((d.debug_completion>>k)&1){need(n<completed.size()&&!completed[n],"duplicate node completion");completed[n]=true;finished++;}
   if(((d.debug_valid&d.debug_ready&d.debug_write)>>k)&1){
    need(n<info[2],"output node index");U32 a=d.debug_addr[k],bytes=(d.debug_byte>>k)&1?1:4;
    U32 base=nodes[n*4],size=nodes[n*4+1],off=nodes[n*4+2];
    need(a>=base && U64(a)+bytes<=U64(base)+size,"write outside declared output");
    for(unsigned j=0;j<bytes;j++){size_t p=off+a-base+j;need(p<expected.size()&&!seen[p],"output duplicate/range");
     need(uint8_t(d.debug_wdata[k]>>(8*j))==expected[p],"integer output mismatch node "+std::to_string(n));seen[p]=1;checked++;}
   }
  }
  auto pop=[](U32 x){unsigned n=0;for(;x;x&=x-1)n++;return n;};
  if(pop(workframes)>1)work_overlap++;if(pop(macframes)>1)mac_overlap++;peak_frames=std::max(peak_frames,pop(activeframes));
 }
 void tick(){
  need(cycle<20000000,"cycle watchdog");d.FCLK_CLK0=0;ram.drive();d.eval();
  if(d.FCLK_RESET0_N){
   if(d.debug_cpu_addr<16384){cpu_ram_reads+=d.debug_cpu_re;cpu_ram_writes+=d.debug_cpu_we;}
   monitor();ram.capture();
  }
  d.FCLK_CLK0=1;d.eval();d.FCLK_CLK0=0;d.eval();cycle++;
 }
 void wr(U32 off,U32 value){
  d.M_AXI_GP0_WDATA=value;d.M_AXI_GP0_WVALID=1;
  tick();tick(); // data before AW, with independent channel acceptance
  d.M_AXI_GP0_AWADDR=0x40000000+off;d.M_AXI_GP0_AWVALID=1;
  for(unsigned i=0;;i++){need(i<1000,"GP AW timeout");d.eval();bool h=d.M_AXI_GP0_AWREADY;tick();if(h)break;}
  d.M_AXI_GP0_AWVALID=0;
  for(unsigned i=0;;i++){need(i<1000,"GP W timeout");d.eval();bool h=d.M_AXI_GP0_WREADY;tick();if(h)break;}
  d.M_AXI_GP0_WVALID=0;
  for(unsigned i=0;!d.M_AXI_GP0_BVALID;i++){need(i<1000,"GP B timeout");tick();}
  need(d.M_AXI_GP0_BRESP==0&&d.M_AXI_GP0_BID==0x123,"GP write response");
  tick();tick();d.M_AXI_GP0_BREADY=1;tick();d.M_AXI_GP0_BREADY=0;gp_writes++;
 }
 U32 rd(U32 off){
  d.M_AXI_GP0_ARADDR=0x40000000+off;d.M_AXI_GP0_ARVALID=1;
  for(unsigned i=0;;i++){need(i<1000,"GP AR timeout");d.eval();bool h=d.M_AXI_GP0_ARREADY;tick();if(h)break;}
  d.M_AXI_GP0_ARVALID=0;
  for(unsigned i=0;!d.M_AXI_GP0_RVALID;i++){need(i<1000,"GP R timeout");tick();}
  need(d.M_AXI_GP0_RRESP==0&&d.M_AXI_GP0_RID==0x456&&d.M_AXI_GP0_RLAST,"GP read response");U32 v=d.M_AXI_GP0_RDATA;
  tick();tick();need(d.M_AXI_GP0_RDATA==v,"GP read changed under backpressure");
  d.M_AXI_GP0_RREADY=1;tick();d.M_AXI_GP0_RREADY=0;gp_reads++;return v;
 }
 std::array<U32,5> rpc(U32 op,U32 a=0,U32 b=0,U32 c=0,U32 e=0,bool allow_again=false){
  wr(16,op);wr(20,a);wr(24,b);wr(28,c);wr(32,e);wr(8,++seq);
  for(unsigned i=0;;i++){need(i<100000,"CPU command timeout op "+std::to_string(op));if(rd(12)==seq)break;}
  std::array<U32,5>r{};r[0]=rd(80);for(unsigned i=0;i<4;i++)r[i+1]=rd(84+4*i);
  need(r[0]==0||(allow_again&&r[0]==2),"CPU command "+std::to_string(op)+" returned "+std::to_string(r[0]));return r;
 }
 void cfg(U32 a,U32 v){rpc(2,a,v);}
 void run(){
  need(rd(100)==0x43505532,"real CPU boot");rpc(1,0x44524459);rpc(8);
  if(k1_bank){
   // Keep K3, Post, DW7, Add and Pad enabled; choose four of the twelve K1 units.
   U32 k1_mask=15u<<(4+4*k1_bank);
   cfg(0x10,((1u<<23)-1u & ~(4095u<<4))|k1_mask);
  }
  U32 model_end=im[0];for(unsigned f=0;f<info[0];f++)model_end=std::min(model_end,im[f*5]);
  rpc(9,0x10,model_end);rpc(9,0x14,1);
  for(unsigned s=0;s<info[1];s++){
   U32*m=&meta[s*18];std::array<U32,20>row{};for(unsigned w=0;w<16;w++)row[w]=cmd[s*16+w];
   std::vector<U32>cons;for(unsigned t=0;t<256;t++)if(t!=s&&((m[5+t/32]>>(t%32))&1))cons.push_back(t);
   need(cons.size()<=2,"compact consumer capacity");
   row[16]=m[0]|m[4]<<4|m[13]<<6|m[14]<<9|m[16]<<15|m[1]<<16|m[2]<<18;
   row[17]=m[3]|m[15]<<8;row[18]=U32(cons.size())<<16;if(!cons.empty())row[18]|=cons[0];if(cons.size()>1)row[18]|=cons[1]<<8;row[19]=m[17];
   cfg(0x14,s);cfg(0x18,0);for(auto w:row)cfg(0x1c,w);
   try {rpc(3,4);} catch(const std::exception& e) {throw std::runtime_error("template step "+std::to_string(s)+": "+e.what());}
  }
  for(unsigned f=0;f<info[0];f++){cfg(0x20,f);cfg(0x24,im[f*5]);cfg(0x28,im[f*5+3]);cfg(0x2c,im[f*5+4]);rpc(3,8);}
  cfg(0x0c,info[0]);check=true;rpc(4);
  for(unsigned f=0;f<info[0];f++){
   U32 a=im[f*5],n=im[f*5+1],off=im[f*5+2];
   // A PS upload writes only its not-yet-committed input. No intermediate data.
   for(unsigned j=0;j<n;j+=4){for(unsigned k=0;k<4&&j+k<n;k++)ram.data[a+j+k]=images[off+j+k];for(unsigned k=0;k<8;k++)tick();}
   rpc(5,f,im[f*5+4]);for(unsigned k=0;k<1000;k++)tick();
  }
  std::vector<std::vector<uint8_t>> results(info[0]);unsigned got=0;
  while(got<info[0]){
   auto r=rpc(6,0,0,0,0,true);if(r[0]==2){for(unsigned i=0;i<1000;i++)tick();continue;}
   U32 f=info[0];for(unsigned i=0;i<info[0];i++)if(im[i*5+4]==r[1])f=i;need(f<info[0]&&results[f].empty(),"result owner");
   U32 n=(info[1]-1)*info[0]+f;need(r[2]==nodes[n*4]&&r[3]==nodes[n*4+1],"result descriptor");
   need(r[4]==1,"result epoch");
   for(unsigned j=0;j<r[3];j++){uint8_t v=ram.data.at(r[2]+j);need(v==expected.at(nodes[n*4+2]+j),"DDR output mismatch after fence");results[f].push_back(v);}
   rpc(7,r[1],r[4]);got++;
  }
  auto status=rpc(10);need((status[1]&4)&&!(status[1]&8)&&status[2]==info[2],"final CNN status");
  need(started==info[2]&&finished==info[2]&&checked==expected.size(),"all jobs/output coverage");
  if(k1_bank){
   for(unsigned k=4;k<16;k++)
    need((unit_starts[k]>0)==(k>=4+4*k1_bank&&k<8+4*k1_bank),"K1 bank coverage mismatch");
  }
  need(cpu_ram_reads>0&&cpu_ram_writes>0,"new CPU RAM not exercised: reads="+std::to_string(cpu_ram_reads)+" writes="+std::to_string(cpu_ram_writes));
  need(d.debug_page_misses>0&&d.debug_mover_read_bytes>0&&d.debug_mover_write_bytes>0,
       "new MOVER path did not transfer data in both directions");
  if(info[0]>1)need(work_overlap>0&&mac_overlap>0&&peak_frames>=2,"no true cross-image compute");
  need(std::equal(initial.begin(),initial.begin()+model_end,ram.data.begin()),"readonly model modified");
  for(unsigned s=0;s<16;s++){U32 base=info[8+s*2],size=info[9+s*2];for(unsigned j=base+size-64;j<base+size;j++)need(ram.data[j]==0xa5,"guard overwritten");}
  for(auto&r:results)outputs.insert(outputs.end(),r.begin(),r.end());
  std::ofstream o(out/"outputs.bin",std::ios::binary);o.write(reinterpret_cast<const char*>(outputs.data()),outputs.size());o.close();
  check=false;rpc(8);auto reset=rpc(10);need(reset[4]==2&&!(reset[1]&8),"batch reset epoch");
  std::ofstream m(out/"metrics.json");m<<"{\"status\":\"PASS\",\"cycles\":"<<cycle<<",\"jobs\":"<<finished<<",\"checked_output_bytes\":"<<checked<<",\"results\":"<<info[0]<<",\"real_multiframe_work_cycles\":"<<work_overlap<<",\"real_multiframe_mac_cycles\":"<<mac_overlap<<",\"peak_active_frames\":"<<peak_frames<<",\"gp_reads\":"<<gp_reads<<",\"gp_writes\":"<<gp_writes<<",\"cpu_ram_reads\":"<<cpu_ram_reads<<",\"cpu_ram_writes\":"<<cpu_ram_writes<<",\"ddr_read_bytes\":"<<ram.read_bytes<<",\"ddr_write_bytes\":"<<ram.write_bytes<<",\"unit_starts\":[";for(unsigned k=0;k<23;k++){if(k)m<<",";m<<unit_starts[k];}m<<"]}\n";
  std::cout<<"PASS EES331 realCPU/23-CNN/tile-RAM/DATA-MOVER/DDR jobs="<<finished<<" checked="<<checked<<" cycles="<<cycle<<" overlap="<<work_overlap<<" misses="<<d.debug_page_misses<<" mover_read_bytes="<<d.debug_mover_read_bytes<<" mover_write_bytes="<<d.debug_mover_write_bytes<<"\n";
  std::cout<<"UNIT_STARTS";for(auto n:unit_starts)std::cout<<" "<<n;std::cout<<"\n";
 }
};
int main(int argc,char**argv){try{need(argc==3||argc==4,"usage simulator DATA OUT [K1_BANK]");fs::create_directories(argv[2]);unsigned bank=argc==4?unsigned(std::stoul(argv[3])):0;Bench b(argv[1],argv[2],bank);b.run();return 0;}catch(const std::exception&e){std::cerr<<"FAIL EES331_SOC "<<e.what()<<"\n";return 1;}}
