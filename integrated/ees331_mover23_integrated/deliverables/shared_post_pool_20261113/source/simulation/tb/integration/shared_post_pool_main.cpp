#include "Vshared_post_pool_top.h"
#include "verilated.h"
#include "verilated_vcd_c.h"
#include "shared_post_reference.hpp"
#include <memory>
#include <fstream>
#include <iostream>
#include <algorithm>
int main(int argc,char** argv){try{
 need(argc==2,"run directory required");std::string dir=argv[1];std::ofstream metrics(dir+"/metrics.json");metrics<<"{\"status\":\"PASS\",\"batches\":[";
 for(U scenario=0;scenario<10;scenario++){
  auto ctx=std::make_unique<VerilatedContext>();ctx->traceEverOn(scenario==0);Vshared_post_pool_top d(ctx.get());
  std::unique_ptr<VerilatedVcdC> trace;std::ofstream csv;
  if(scenario==0){trace=std::make_unique<VerilatedVcdC>();d.trace(trace.get(),1);trace->open((dir+"/shared_pool.vcd").c_str());csv.open(dir+"/shared_pool.csv");csv<<"cycle,busy,done,mac,waiting,owned,owner0,owner1,fifo0,fifo1,push,pop,post_retire,final_ack\n";}
  std::vector<uint8_t> mem(8*1024*1024,0xa5);std::array<TensorJob,8> jobs;std::array<bool,8> fused{};
  for(U c=0;c<8;c++){
   U k=c<2?3:1,ci=scenario==5?64:(c%3==0?3:(c%3==1?7:16)),co=scenario==5?64:(c%2==0?9:8),stride=scenario==4?2:1;
   bool dw=c==1 && scenario==3;if(dw)co=ci;fused[c]=!(scenario==2 && (c==0||c==3));
   jobs[c]=make_job(mem,c,k,scenario==5?11:7,scenario==5?9:7,ci,co,stride,dw,scenario%4,fused[c]);
   for(U w=0;w<16;w++)d.unit_command[c*16+w]=jobs[c].conv[w];
  }
  // Two legacy post tasks are also present in scenarios2/8, and reuse the
  // exact same physical post processors before/after the fused owners.
  std::array<std::vector<uint8_t>,2> legacy_gold;std::array<U,2> legacy_out{};
  for(U p=0;p<2;p++){
   U base=0x600000+p*0x20000,src=base,par=base+0x8000,out=base+0x10000;std::vector<uint8_t> raw;
   for(U i=0;i<33;i++){U v=U(int32_t(i*371)-5000);word(mem,src+i*4,v);for(U b=0;b<4;b++)raw.push_back((v>>(b*8))&255);}
   legacy_gold[p]=quant(raw,3,par,mem,p+72);legacy_out[p]=out;
   Command a{};a[0]=1;a[1]=src;a[3]=out;a[4]=par;a[5]=33;a[6]=3;
   for(U w=0;w<16;w++)d.unit_command[(8+p)*16+w]=a[w];
  }
  Memory<Vshared_post_pool_top,10> bus(d,mem);bus.immediate=scenario==6;bus.heavy=scenario==0||scenario==7;
  if(scenario==8){bus.cut_port=8;bus.cut_until=3000;}
  auto tick=[&]{d.clk=1;d.eval();if(trace)trace->dump(ctx->time());ctx->timeInc(5000);d.clk=0;d.eval();if(trace)trace->dump(ctx->time());ctx->timeInc(5000);};
  d.rst_n=0;d.clear=0;d.unit_start=0;d.post_enable=scenario==1?1:3;bus.cancel();tick();tick();d.rst_n=1;tick();
  U expected=(scenario==2||scenario==8)?1023:255,completed=0;std::array<U,8> grants{};std::array<bool,2> previous_owned{};std::array<U,2> previous_owner{};
  L max_wait=0,dual=0,wait_mac=0,full=0;bool restarted=false,done=false;L total=0;
  for(L t=0;t<3000000;t++){
   bus.present(t);
   d.unit_start=t==0?expected:0;
   if(scenario==9 && t<300)d.post_enable=0;else d.post_enable=scenario==1?1:3;
   d.eval();
   if(scenario==7 && !restarted && ((d.fifo_level&15)==8 || ((d.fifo_level>>4)&15)==8)){
    d.clear=1;bus.cancel();tick();tick();d.clear=0;bus.cancel();tick();
    std::fill(bus.seen.begin(),bus.seen.end(),0);for(U c=0;c<8;c++)std::fill(mem.begin()+jobs[c].post[3],mem.begin()+jobs[c].post[3]+jobs[c].n,0xa5);
    completed=0;grants={};previous_owned={};restarted=true;d.unit_start=expected;d.eval();
   }
   need(!d.unit_error,"pool error");
   if(csv)csv<<t<<','<<d.unit_busy<<','<<d.unit_done<<','<<(d.unit_work&255)<<','<<U(d.waiting)<<','<<U(d.owned)<<','<<(d.owner_id&7)<<','<<((d.owner_id>>3)&7)<<','<<(d.fifo_level&15)<<','<<((d.fifo_level>>4)&15)<<','<<U(d.fifo_push)<<','<<U(d.fifo_pop)<<','<<U(d.post_retire)<<','<<U(d.final_write_ack)<<'\n';
   for(U p=0;p<2;p++){
    bool own=(d.owned>>p)&1;U owner=(d.owner_id>>(3*p))&7;
    if(own&&previous_owned[p])need(owner==previous_owner[p],"post owner changed before draining");
    if(own&&!previous_owned[p]){need(fused[owner],"stored job stole direct link");grants[owner]++;}
    previous_owned[p]=own;previous_owner[p]=owner;
    if(scenario==1)need(!(d.owned&2),"disabled post was allocated");
    need(((d.fifo_level>>(4*p))&15)<=8,"FIFO overflow");
   }
   max_wait=std::max(max_wait,L(__builtin_popcount(U(d.waiting))));dual+=d.owned==3;wait_mac+=d.waiting && (d.unit_work&255);full+=((d.fifo_level&15)==8)||(((d.fifo_level>>4)&15)==8);
   need(!(completed&d.unit_done),"duplicate done pulse");completed|=d.unit_done;
   if((completed&expected)==expected){need(!bus.pending(),"done before final write response");done=true;total=t;break;}
   bus.advance();tick();
  }
  need(done,"pool watchdog");if(scenario==7)need(restarted,"clear under full FIFO not exercised");
  for(U c=0;c<8;c++){
   U addr=fused[c]?jobs[c].post[3]:jobs[c].conv[3];auto& gold=fused[c]?jobs[c].gold:jobs[c].raw;
   need(std::equal(gold.begin(),gold.end(),mem.begin()+addr),"numeric mismatch unit "+std::to_string(c));
   for(U b=0;b<gold.size();b++)need(bus.seen[addr+b]==1,"output byte coverage");
   if(fused[c]){need(grants[c]==1,"missing/duplicate post ownership");U raw=c*0x80000+0x40000;for(U i=0;i<jobs[c].raw.size();i++)need(mem[raw+i]==0xa5,"fused job wrote intermediate SRAM");}
  }
  if(scenario==2||scenario==8)for(U p=0;p<2;p++)need(std::equal(legacy_gold[p].begin(),legacy_gold[p].end(),mem.begin()+legacy_out[p]),"legacy post corrupted by stream");
  if(scenario==0)need(max_wait>=4 && dual && full && wait_mac,"queue/parallel/backpressure not exercised");
  if(trace)trace->close();if(scenario)metrics<<',';
  metrics<<"{\"scenario\":"<<scenario<<",\"cycles\":"<<total<<",\"completed\":"<<completed<<",\"max_waiting\":"<<max_wait<<",\"dual_post_cycles\":"<<dual<<",\"waiting_with_mac_cycles\":"<<wait_mac<<",\"fifo_full_cycles\":"<<full<<",\"read_bytes\":"<<bus.reads<<",\"write_bytes\":"<<bus.writes<<'}';
  std::cout<<"PASS pool batch "<<scenario<<" cycles="<<total<<" queued="<<max_wait<<std::endl;
 }
 metrics<<"]}\n";return 0;
}catch(const std::exception& e){std::cerr<<"FAIL "<<e.what()<<std::endl;return 1;}}
