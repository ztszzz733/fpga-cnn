#include "Vshared_post_mmio_top.h"
#include "verilated.h"
#include "shared_post_reference.hpp"
#include <fstream>
#include <iostream>
#include <algorithm>
int main(int argc,char**argv){try{
 need(argc==2,"run directory required");std::string dir=argv[1];std::ofstream log(dir+"/metrics.json");log<<"{\"status\":\"PASS\",\"cases\":[";
 for(U scenario=0;scenario<3;scenario++){
  VerilatedContext ctx;Vshared_post_mmio_top d(&ctx);std::vector<uint8_t> mem(8*1024*1024,0xa5);Memory<Vshared_post_mmio_top,12> bus(d,mem);
  bus.heavy=scenario==2;bus.immediate=scenario==1;
  std::array<TensorJob,4> first,second;
  for(U f=0;f<4;f++){
   std::vector<uint8_t> input(7*7*3);for(U i=0;i<input.size();i++)input[i]=(i*17+f*39+5)%256;
   first[f]=make_job(mem,0,3,7,7,3,4,1,false,0,true,&input);
   second[f]=make_job(mem,1,1,5,5,4,3,1,false,0,true,&first[f].gold);
   std::copy(input.begin(),input.end(),mem.begin()+0x100000+f*0x10000);
  }
  L cycle=0,dual=0,wait=0;std::array<bool,4> seen{};U results=0;
  auto tick=[&]{
   bus.present(cycle);need(!d.error,"CNN/MMIO error");
   if(d.cnn_cancel)bus.cancel();else bus.advance();
   dual+=d.owned==3;wait+=d.waiting!=0;d.clk=1;d.eval();ctx.timeInc(5000);d.clk=0;d.eval();ctx.timeInc(5000);cycle++;
  };
  d.rst_n=0;d.cnn_mmio_addr=0;d.cnn_mmio_wdata=0;d.cnn_mmio_re=0;d.cnn_mmio_we=0;d.cnn_mem_fault=0;bus.cancel();tick();tick();d.rst_n=1;tick();
  auto wr=[&](U a,U v){d.cnn_mmio_addr=a;d.cnn_mmio_wdata=v;d.cnn_mmio_we=1;tick();d.cnn_mmio_we=0;tick();};
  auto rd=[&](U a){d.cnn_mmio_addr=a;d.cnn_mmio_re=1;bus.present(cycle);d.eval();U value=d.cnn_mmio_rdata;need(d.cnn_mmio_ready,"MMIO stalled");tick();d.cnn_mmio_re=0;tick();return value;};
  wr(8,1);wr(0x0c,4);
  bool fused=scenario!=1;std::ifstream plan(dir+(fused?"/templates_fused.mem":"/templates_stored.mem"));need(bool(plan),"missing software plan");
  U steps=fused?2:4;
  for(U row=0;row<steps;row++){wr(0x14,row);wr(0x18,0);for(U w=0;w<20;w++){U value;need(bool(plan>>std::hex>>value),"short software plan");wr(0x1c,value);}wr(8,4);}
  for(U f=0;f<4;f++){wr(0x20,f);wr(0x24,0x100000+f*0x10000);wr(0x28,0x200000+f*0x10000);wr(0x2c,100+f);wr(8,8);}
  wr(8,2);for(U f=0;f<4;f++){wr(0x20,f);wr(0x2c,100+f);wr(8,16);}
  L submitted=cycle;
  for(U spins=0;spins<100000;spins++){
   U status=rd(4);
   if(status&(1u<<5)){
    U frame=rd(0x30),addr=rd(0x34),n=rd(0x38),epoch=rd(0x54);need(frame>=100&&frame<104,"result frame ID");U f=frame-100;
    need(!seen[f] && addr==0x200000+f*0x10000+12288 && n==75,"result descriptor/lifetime");
    need(std::equal(second[f].gold.begin(),second[f].gold.end(),mem.begin()+addr),"two-layer final mismatch");
    need(std::equal(first[f].gold.begin(),first[f].gold.end(),mem.begin()+0x200000+f*0x10000+4096),"first layer incomplete before second layer");
    if(fused){for(U i=0;i<first[f].raw.size();i++)need(mem[0x200000+f*0x10000+i]==0xa5,"fused first raw stored");for(U i=0;i<second[f].raw.size();i++)need(mem[0x200000+f*0x10000+8192+i]==0xa5,"fused second raw stored");}
    seen[f]=true;results++;wr(0x4c,frame);wr(0x50,epoch);wr(8,32);
   }
   if(d.done)break;
  }
  need(d.done&&!d.busy&&!d.error&&!bus.pending()&&results==4,"CNN did not drain results");need(d.completed_count==4*steps,"fused task completion accounting");
  if(fused)need(dual>0,"shared CNN dispatcher never used two posts");
  if(scenario)log<<',';log<<"{\"scenario\":"<<scenario<<",\"fused\":"<<(fused?"true":"false")<<",\"frames\":4,\"commands\":"<<4*steps<<",\"cycles_after_submission\":"<<cycle-submitted<<",\"dual_post_cycles\":"<<dual<<",\"waiting_cycles\":"<<wait<<",\"read_bytes\":"<<bus.reads<<",\"write_bytes\":"<<bus.writes<<"}";
  std::cout<<"PASS MMIO case "<<scenario<<" steps="<<steps<<" frames=4 cycles="<<cycle-submitted<<std::endl;
 }
 log<<"]}\n";return 0;
}catch(const std::exception& e){std::cerr<<"FAIL "<<e.what()<<std::endl;return 1;}}
