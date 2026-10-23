#include "Vpost_pipe_unit_top.h"
#include "verilated.h"
#include <vector>
#include <array>
#include <random>
#include <iostream>
#include <fstream>
#include <stdexcept>
#include <cstdint>
using U=uint32_t;using L=uint64_t;using I=__int128_t;
void need(bool c,const char* s){if(!c)throw std::runtime_error(s);}
struct Stats{L cycles=0,requests=0,word_writes=0,byte_writes=0,read_pipeline_overlap=0;};
Stats run(bool fast,bool add,U nch,U n,U off,bool heavy=false,bool immediate=false,int abort=0,int invalid=0,bool latch=false){
 Vpost_pipe_unit_top d;std::vector<uint8_t> mem(131072,0xa5),gold(n),seen(n,0);
 U pa=1024+(add?off:0),pb=16384+off,pp=32768,po=65536+off;
 std::mt19937 rng(807+nch+n+off);std::vector<int32_t> bias(nch),ma(nch),mb(nch);
 std::vector<U> shift(nch),za(nch),zb(nch),zo(nch),lo(nch),hi(nch);
 auto put=[&](U a,U v){for(U b=0;b<4;b++)mem[a+b]=v>>(8*b);};
 std::array<int32_t,8> extreme={INT32_MIN,INT32_MAX,-1,0,1,-1234567,1234567,7};
 for(U c=0;c<nch;c++){
  bias[c]=c%3?int32_t(rng()):extreme[c%8];ma[c]=c%3?int32_t(rng()):extreme[(c+1)%8];mb[c]=int32_t(rng());
  shift[c]=c%64;za[c]=rng()%256;zb[c]=rng()%256;zo[c]=rng()%256;lo[c]=c%3?0:51;hi[c]=c%3?255:201;
  // Known rounding ties with both signs, and sum-before-round residual cases.
  if(c%8==5){bias[c]=0;ma[c]=1;mb[c]=1;shift[c]=1;za[c]=127;zb[c]=127;zo[c]=128;}
  put(pp+c*20,U(bias[c]));put(pp+c*20+4,U(ma[c]));put(pp+c*20+8,U(mb[c]));
  put(pp+c*20+12,(zo[c]<<24)|(zb[c]<<16)|(za[c]<<8)|shift[c]);put(pp+c*20+16,(hi[c]<<8)|lo[c]);
 }
 for(U i=0;i<n;i++){
  U c=i%nch;int32_t a=i%3?int32_t(rng()):extreme[i%8],b=rng()%256;
  if(c%8==5)a=i%2?-3:3;
  if(add){a=U(a)&255;mem[pa+i]=a;mem[pb+i]=b;}else put(pa+i*4,U(a));
  I p=add?(I(a)-za[c])*ma[c]+(I(b)-zb[c])*mb[c]:(I(a)+bias[c])*ma[c];
  I q=p;if(shift[c]){I mag=p<0?-p:p;mag=(mag+(I(1)<<(shift[c]-1)))>>shift[c];q=p<0?-mag:mag;}
  q+=zo[c];gold[i]=q<lo[c]?lo[c]:(q>hi[c]?hi[c]:U(q));
 }
 if(invalid==6)put(pp+12,64);if(invalid==7)put(pp+16,0x0102);
 auto cfg=[&]{d.src_a=pa;d.src_b=pb;d.destination=po;d.parameter_base=pp;d.count=n;d.channels=nch;d.mode_add=add;};
 auto tick=[&]{d.clk=1;d.eval();d.clk=0;d.eval();};
 d.optimized=fast;d.rst_n=0;d.clear=0;d.start=0;d.ready=0;d.response=0;cfg();tick();tick();d.rst_n=1;tick();
 switch(invalid){case 1:d.count=0;break;case 2:d.channels=0;break;case 3:d.channels=513;break;case 4:d.parameter_base=pp+1;break;case 5:d.src_a=pa+1;break;default:break;}
 d.start=1;tick();d.start=0;if(latch){d.src_a=0;d.channels=0;d.count=0;d.mode_add=!add;}
 bool pending=false,pwrite=false,holding=false,restarted=false;U addr=0,len=0,data=0,delay=0,seq=0,written=0;std::array<U,4> held{};Stats st;
 auto reply=[&]{
  d.rdata=0;
  if(pwrite)for(U b=0;b<len;b++){need(!seen[addr-po+b],"duplicate output");seen[addr-po+b]=1;mem[addr+b]=data>>(8*b);written++;}
  else for(U b=0;b<len;b++)d.rdata|=U(mem[addr+b])<<(8*b);
 };
 for(L cyc=0;cyc<1000000;cyc++){
  if(abort&&!restarted&&((abort==1&&pending&&!pwrite)||(abort==2&&pending&&pwrite)||(abort==3&&d.pipe_active))){
   d.clear=1;d.ready=0;d.response=0;tick();tick();pending=holding=false;d.clear=0;tick();cfg();d.start=1;tick();d.start=0;
   std::fill(mem.begin()+po,mem.begin()+po+n,0xa5);std::fill(seen.begin(),seen.end(),0);written=0;st={};restarted=true;
  }
  bool resp=pending&&delay==0;d.response=resp;d.ready=!pending&&(heavy?cyc%13>=10:cyc%7>=2);d.rdata=0;if(resp)reply();d.eval();
  std::array<U,4> now={d.write,d.byte_access,d.addr,d.wdata};if(holding)need(d.valid&&now==held,"unstable request");holding=d.valid&&!d.ready;held=now;
  if(d.done){need(!pending&&!resp,"early done");need(!invalid,"invalid accepted");break;}
  if(d.error){need(invalid,"unexpected error");need(written==0,"invalid wrote output");if(invalid<=5)need(st.requests==0,"invalid accessed memory");return st;}
  if(resp&&!pwrite&&d.pipe_active)st.read_pipeline_overlap++;
  bool accept=d.valid&&d.ready;
  if(accept){
   need(!pending,"multiple outstanding");addr=d.addr;len=d.byte_access?1:4;data=d.wdata;pwrite=d.write;need(len==1||addr%4==0,"unaligned word");
   if(pwrite){need(addr>=po&&addr+len<=po+n,"write outside output");if(len==4)st.word_writes++;else st.byte_writes++;}
   else need((addr>=pp&&addr+len<=pp+nch*20)||(addr>=pa&&addr+len<=pa+n*(add?1:4))||(add&&addr>=pb&&addr+len<=pb+n),"read outside input/params");
   st.requests++;delay=heavy?seq++%29:seq++%5;pending=true;
   if(immediate){d.response=1;reply();d.eval();pending=false;}
  }else if(resp)pending=false;else if(pending)delay--;
  tick();st.cycles++;
 }
 need(d.done,"watchdog");need(!abort||restarted,"clear not exercised");need(written==n,"coverage");
 for(U i=0;i<n;i++)if(mem[po+i]!=gold[i]){std::cerr<<"mismatch add="<<add<<" i="<<i<<" got="<<U(mem[po+i])<<" expected="<<U(gold[i])<<'\n';need(false,"numeric mismatch");}
 for(U i=1;i<=16;i++)need(mem[po-i]==0xa5&&mem[po+n+i-1]==0xa5,"guard corruption");return st;
}
int main(int argc,char**argv){try{
 need(argc==2,"JSON path required");std::ofstream o(argv[1]);o<<"{\"status\":\"PASS\",\"cases\":[";U id=0;
 for(bool add:{false,true})for(U c:{1,3,7,64,512})for(U off:{0,1,2,3}){
  U n=c*3+7;std::cout<<"CASE "<<id<<std::endl;auto a=run(false,add,c,n,off),b=run(true,add,c,n,off);
  if(id)o<<',';o<<"{\"id\":"<<id++<<",\"add\":"<<add<<",\"channels\":"<<c<<",\"count\":"<<n<<",\"offset\":"<<off<<",\"old_cycles\":"<<a.cycles<<",\"new_cycles\":"<<b.cycles<<",\"old_requests\":"<<a.requests<<",\"new_requests\":"<<b.requests<<",\"word_writes\":"<<b.word_writes<<",\"byte_writes\":"<<b.byte_writes<<",\"read_pipeline_overlap\":"<<b.read_pipeline_overlap<<'}';
 }
 for(bool add:{false,true})for(U n:{1,2,3,4,5,6,7,8,9})run(true,add,7,n,n%4,true,true);
 for(int abort:{1,2,3})run(true,true,64,256,1,true,false,abort);
 for(int invalid=1;invalid<=7;invalid++)run(true,false,7,24,0,false,false,0,invalid);
 run(true,false,64,512,0,true,false,0,0,true);run(true,true,64,512,0,true,false,0,0,true);
 o<<"],\"immediate_tail_cases\":18,\"clear_restarts\":3,\"invalid_cases\":7,\"descriptor_latching_cases\":2}\n";
 std::cout<<"PASS post numeric/protocol\n";return 0;
 }catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
