#include "Vself_optimized_unit_top.h"
#include "verilated.h"
#include <vector>
#include <array>
#include <random>
#include <iostream>
#include <fstream>
#include <stdexcept>
#include <cstdint>
#include <string>
using U=uint32_t; using L=uint64_t;
struct Spec{U w,h,ci,co,stride,offset;U k=1;bool dw=false;U stall=0;};
struct Stats{L cycles,requests,bytes,macs,fire,full_streak,read_overlap,write_overlap,queue_full;};
void need(bool ok,const char* s){if(!ok)throw std::runtime_error(s);}
Stats run(bool fast,Spec s,int abort=0,bool latch=false,int invalid=0,bool immediate=false){
 Vself_optimized_unit_top d;std::vector<uint8_t> mem(131072,0xa5),gold,seen(131072);
 U ib=1024+s.offset,wb=32768+s.offset,ob=65536;
 std::mt19937 rng(733+s.ci+s.w*13+s.offset);std::vector<uint8_t> x(s.w*s.h*s.ci);std::vector<int8_t> weights(s.co*s.k*s.k*(s.dw?1:s.ci));
 for(auto &v:x)v=rng()%256;for(auto &v:weights)v=int(rng()%256)-128;
 if(x.size()>1){x[0]=255;x[1]=128;}if(weights.size()>1){weights[0]=-128;weights[1]=127;}
 for(U y=0;y+s.k<=s.h;y+=s.stride)for(U xx=0;xx+s.k<=s.w;xx+=s.stride)for(U o=0;o<s.co;o++){
  int64_t sum=0;
  for(U ky=0;ky<s.k;ky++)for(U kx=0;kx<s.k;kx++)for(U c=0;c<(s.dw?1:s.ci);c++){
   U ic=s.dw?o:c,wi=((o*s.k+ky)*s.k+kx)*(s.dw?1:s.ci)+c;
   sum+=int64_t(x[((y+ky)*s.w+xx+kx)*s.ci+ic])*weights[wi];
  }
  for(int b=0;b<4;b++)gold.push_back((U(sum)>>(8*b))&255);
 }
 for(U i=0;i<x.size();i++)mem[ib+i]=x[i];for(U i=0;i<weights.size();i++)mem[wb+i]=uint8_t(weights[i]);
 auto cfg=[&]{d.input_base=ib;d.weight_base=wb;d.output_base=ob;d.width=s.w;d.height=s.h;d.in_channels=s.ci;d.out_channels=s.co;d.kernel=s.k;d.stride=s.stride;d.depthwise=s.dw;};
 d.optimized=fast;d.rst_n=0;d.clear=0;d.start=0;d.ready=0;d.response=0;cfg();
 auto tick=[&]{d.clk=1;d.eval();d.clk=0;d.eval();};tick();tick();d.rst_n=1;tick();
 switch(invalid){case 1:d.out_channels=0;break;case 2:d.width=0;break;case 3:d.in_channels=513;break;case 4:d.kernel=7;break;case 5:d.depthwise=1;d.out_channels=s.ci+1;break;case 6:d.stride=3;break;case 7:d.output_base=ob+1;break;case 8:d.output_base=ib;break;case 9:d.input_base=0xfffffffe;break;case 10:d.weight_base=0xfffffffc;break;case 11:d.output_base=0xfffffff0;break;case 12:d.out_channels=513;break;case 13:d.height=65536;break;default:break;}
 d.start=1;tick();d.start=0;
 if(latch){d.input_base=0;d.weight_base=0;d.width=0;d.in_channels=0;d.stride=0;}
 bool pending=false,pwrite=false,holding=false,restarted=false;U pa=0,pn=0,pdata=0,delay=0,seq=0;
 std::array<U,4> held{};Stats st{};L streak=0;U written=0;
 for(L cycle=0;cycle<5000000;cycle++){
  if(abort && !restarted && ((pending&&((abort==1&&!pwrite)||(abort==2&&pwrite)))||(abort==3&&d.mac_fire))){
   d.clear=1;d.response=0;d.ready=0;tick();tick();pending=false;holding=false;d.clear=0;tick();cfg();d.start=1;tick();d.start=0;
   std::fill(mem.begin()+ob,mem.begin()+ob+gold.size(),0xa5);std::fill(seen.begin(),seen.end(),0);written=0;st={};streak=0;restarted=true;
  }
  bool response=pending&&delay==0;d.response=response;d.ready=!pending && (s.stall?cycle%13>=9:cycle%7>=2);d.rdata=0;
  if(response){
   if(pwrite){for(U b=0;b<pn;b++){need(!seen[pa+b],"duplicate write");seen[pa+b]=1;mem[pa+b]=(pdata>>(8*b))&255;written++;}}
   else for(U b=0;b<pn;b++)d.rdata|=U(mem[pa+b])<<(8*b);
  }
  d.clk=0;d.eval();std::array<U,4> now={d.write,d.byte_access,d.addr,d.wdata};
  if(holding)need(d.valid&&now==held,"request changed under backpressure");
  holding=d.valid&&!d.ready;held=now;
  bool accept=d.valid&&d.ready;
  if(d.done){need(!pending&&!d.response,"early done");need(!invalid,"illegal accepted");break;}
  if(d.error){need(invalid&&!st.requests,"unexpected error or illegal memory access");return st;}
  if(d.mac_fire){st.fire++;streak++;if(streak>st.full_streak)st.full_streak=streak;}else streak=0;
  if(d.mac_fire&&response){if(pwrite)st.write_overlap++;else st.read_overlap++;}
  if(d.queue_full)st.queue_full++;
  if(accept){
   need(!invalid,"invalid configuration accessed memory");need(!pending,"multiple outstanding");
   pa=d.addr;pn=d.byte_access?1:4;pwrite=d.write;pdata=d.wdata;
   need(pn==1||pa%4==0,"unaligned word");
   if(pwrite)need(pn==4 && pa>=ob && pa+pn<=ob+gold.size(),"write range");
   else{need((pa>=ib&&pa+pn<=ib+x.size())||(pa>=wb&&pa+pn<=wb+weights.size()),"read overrun");st.bytes+=pn;}
   st.requests++;delay=s.stall?(seq++%29):(seq++%5);pending=true;
   if(immediate){
    d.response=1;d.rdata=0;
    if(pwrite){for(U b=0;b<pn;b++){need(!seen[pa+b],"duplicate immediate write");seen[pa+b]=1;mem[pa+b]=(pdata>>(8*b))&255;written++;}}
    else for(U b=0;b<pn;b++)d.rdata|=U(mem[pa+b])<<(8*b);
    d.eval();pending=false;
   }
  }else if(response)pending=false;else if(pending)delay--;
  tick();st.cycles++;
 }
 need(d.done,"watchdog");need(!abort||restarted,"restart not exercised");
 need(written==gold.size(),"write coverage");for(U i=0;i<gold.size();i++)need(mem[ob+i]==gold[i],"numeric mismatch");
 for(U b=1;b<=32;b++)need(mem[ob-b]==0xa5&&mem[ob+gold.size()+b-1]==0xa5,"guard corruption");
 st.macs=d.mac_count;need(st.macs==L((s.w-s.k)/s.stride+1)*((s.h-s.k)/s.stride+1)*s.co*s.k*s.k*(s.dw?1:s.ci),"MAC count");
 return st;
}
int main(int argc,char** argv){
 try{
  need(argc==2,"output JSON required");std::ofstream log(argv[1]);log<<"{\"status\":\"PASS\",\"cases\":[";unsigned id=0;
  std::vector<Spec> specs;
#ifdef CNN_K3_TEST
  for(U ci:{1,3,7,32,64,512})for(U stride:{1,2})for(bool dw:{false,true})for(U off:{0,1})
   specs.push_back({5,5,ci,dw?ci:3,stride,off,3,dw});
  specs.push_back({3,3,3,2,1,1,3});
  specs.push_back({7,7,5,5,2,3,3,true,1});
#else
  for(U ci:{1,2,3,4,5,7,8,16,64,512})for(U stride:{1,2})for(U off:{0,1,3})specs.push_back({5,3,ci,3,stride,off});
  for(auto wh:std::vector<std::array<U,2>>{{1,1},{1,3},{3,1},{2,2}})specs.push_back({wh[0],wh[1],7,5,1,2});
  specs.push_back({4,4,64,64,1,0});
  specs.push_back({5,5,1,64,1,0,1,false,1});
  specs.push_back({3,3,3,512,2,1,1,false,1});
  specs.push_back({3,3,511,3,1,3});
#endif
  for(auto s:specs){std::cout<<"CASE "<<id<<std::endl;auto a=run(false,s),b=run(true,s);if(id)log<<',';log<<"{\"id\":"<<id++<<",\"ci\":"<<s.ci<<",\"width\":"<<s.w<<",\"stride\":"<<s.stride<<",\"offset\":"<<s.offset<<",\"old_cycles\":"<<a.cycles<<",\"new_cycles\":"<<b.cycles<<",\"old_requests\":"<<a.requests<<",\"new_requests\":"<<b.requests<<",\"old_bytes\":"<<a.bytes<<",\"new_bytes\":"<<b.bytes<<",\"macs\":"<<b.macs<<",\"consecutive_mac_cycles\":"<<b.full_streak<<",\"read_mac_overlap\":"<<b.read_overlap<<",\"write_mac_overlap\":"<<b.write_overlap<<",\"queue_full_cycles\":"<<b.queue_full<<'}';}
  for(int abort:{1,2,3})run(true,{3,3,5,3,1,1},abort);
  run(true,{3,3,7,5,2,3},0,true);for(int invalid=1;invalid<=13;invalid++)run(true,{3,3,4,4,1,0},0,false,invalid);
  run(true,{5,3,64,8,1,0},0,false,0,true);run(true,{5,3,7,3,2,1},0,false,0,true);
  log<<"],\"clear_restarts\":3,\"descriptor_latching\":true,\"invalid_configurations\":13,\"immediate_response_cases\":2}\n";
  std::cout<<"PASS optimized numerical cases="<<id<<" + restart/latch/error\n";return 0;
 }catch(const std::exception &e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}
}
