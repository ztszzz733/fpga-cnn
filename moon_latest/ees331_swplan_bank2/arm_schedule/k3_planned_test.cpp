#include "Vself_conv_spatial4_engine.h"
#include "verilated.h"
#include <algorithm>
#include <cstdint>
#include <deque>
#include <iostream>
#include <stdexcept>
#include <vector>
static void need(bool b,const char*s){if(!b)throw std::runtime_error(s);}
struct Bench{
 Vself_conv_spatial4_engine d;
 struct Reply{unsigned due;uint32_t data;};
 std::deque<Reply> q;
 std::vector<uint8_t> mem=std::vector<uint8_t>(131072,0xa5);
 unsigned cycle=0,rng=71,out_begin=0,out_end=0,reads=0,writes=0,cases=0;
 unsigned random(){rng=rng*1664525u+1013904223u;return rng;}
 void tick(){
  need(cycle++<3000000,"K3 watchdog");d.clk=0;
  d.ready=(random()%4)!=0;bool returned=!q.empty()&&q.front().due<=cycle;
  d.response=returned;d.rdata=returned?q.front().data:0;d.eval();
  if(returned)q.pop_front();
  if(d.valid&&d.ready){
   uint32_t a=d.addr,v=0;need(a+(d.byte_access?1:4)<=mem.size(),"K3 address escaped model");
   if(d.write){need(!d.byte_access&&a>=out_begin&&a+4<=out_end,"K3 output write escaped tensor");
    for(unsigned b=0;b<4;++b)mem[a+b]=uint8_t(d.wdata>>(b*8));++writes;
   }else{++reads;if(d.byte_access)v=uint32_t(int32_t(int8_t(mem[a])));
    else for(unsigned b=0;b<4;++b)v|=uint32_t(mem[a+b])<<(8*b);
   }
   unsigned due=cycle+1+random()%5;if(!q.empty())due=std::max(due,q.back().due+1);q.push_back({due,v});
  }
  d.clk=1;d.eval();d.clk=0;d.eval();
 }
 Bench(){d.rst_n=0;d.clear=0;d.start=0;tick();tick();d.rst_n=1;tick();}
 void run_case(unsigned w,unsigned h,unsigned ci,unsigned co,unsigned stride,bool dw,bool unaligned){
  d.clear=1;q.clear();tick();d.clear=0;tick();
  std::fill(mem.begin(),mem.end(),0xa5);
  unsigned ib=0x1000+unaligned,wb=0x8000+unaligned,ob=0x10000;
  unsigned ow=(w-3)/stride+1,oh=(h-3)/stride+1,per=9*(dw?1:ci),weights=per*co;
  for(unsigned i=0;i<w*h*ci;++i)mem[ib+i]=uint8_t((i*13+cases)%19);
  for(unsigned i=0;i<weights;++i)mem[wb+i]=uint8_t(int((i*7+cases)%15)-7);
  out_begin=ob;out_end=ob+ow*oh*co*4;
  std::vector<uint32_t> expected;
  for(unsigned y=0;y<oh;++y)for(unsigned x=0;x<ow;++x)for(unsigned oc=0;oc<co;++oc){
   int32_t sum=0;
   for(unsigned ky=0;ky<3;++ky)for(unsigned kx=0;kx<3;++kx)for(unsigned ic=0;ic<(dw?1:ci);++ic){
    unsigned ia=ib+((y*stride+ky)*w+x*stride+kx)*ci+(dw?oc:ic);
    unsigned wa=wb+(dw?oc*9+ky*3+kx:((oc*3+ky)*3+kx)*ci+ic);
    sum+=int32_t(mem[ia])*int32_t(int8_t(mem[wa]));
   }
   expected.push_back(uint32_t(sum));
  }
  bool reuse=dw||((ow>2||oh>2)&&weights<=4608);
  unsigned loaded=reuse?weights:per;
  uint32_t flags=0x80000000u|unsigned(dw)|(reuse?0x400u:0)|
   ((!unaligned&&ci%4==0)?0x100u:0)|((!unaligned&&loaded%4==0)?0x200u:0);
  d.depthwise=dw;d.input_base=ib;d.weight_base=wb;d.output_base=ob;
  d.width=w;d.height=h;d.in_channels=ci;d.out_channels=co;d.kernel=3;d.stride=stride;
  d.plan_flags=flags;d.plan_input_row_bytes=w*ci;d.plan_weight_per_channel=per;
  d.plan_input_extent=w*h*ci;d.plan_weight_extent=weights;
  d.start=1;tick();d.start=0;
  for(unsigned wait=0;!d.done;++wait){need(wait<200000&&!d.error,"K3 execution failed");tick();}
  need(q.empty(),"K3 done before bus drain");
  for(unsigned i=0;i<expected.size();++i){uint32_t actual=0;for(unsigned b=0;b<4;++b)actual|=uint32_t(mem[ob+i*4+b])<<(8*b);
   if(actual!=expected[i])throw std::runtime_error("K3 golden mismatch case="+std::to_string(cases)+" index="+std::to_string(i));}
  need(mem[out_end]==0xa5&&mem[ob-1]==0xa5,"K3 output guard modified");tick();++cases;
 }
 void run(){
  for(unsigned ci:{1u,3u,4u,5u,8u})for(bool dw:{false,true})for(unsigned stride:{1u,2u}){
   run_case(7,6,ci,dw?ci:3,stride,dw,false);
   run_case(3,3,ci,dw?ci:2,stride,dw,true);
  }
  // Bad version and incompatible aligned-word mode must stop before reads.
  for(unsigned bad=0;bad<2;++bad){d.clear=1;q.clear();tick();d.clear=0;tick();
   d.plan_flags=bad?0x80000100u:0;d.in_channels=3;d.input_base=0x1001;
   unsigned before=reads;d.start=1;tick();d.start=0;for(unsigned i=0;i<4;++i)tick();
   need(reads==before&&!d.busy,"invalid K3 plan reached memory");}
  std::cout<<"PASS K3 software plans: "<<cases<<" scalar-golden convolutions; regular/depthwise, strides 1/2, channel tails, unaligned buffers, partial tiles, halo and weight reuse; cycles="<<cycle<<"\n";
 }
};
int main(){try{Bench b;b.run();return 0;}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<"\n";return 1;}}
