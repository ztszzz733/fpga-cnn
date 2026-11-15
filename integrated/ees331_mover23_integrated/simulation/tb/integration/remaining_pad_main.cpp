#include "Vremaining_pad_top.h"
#include "verilated.h"
#include <vector>
#include <array>
#include <random>
#include <fstream>
#include <iostream>
#include <stdexcept>
using U=uint32_t;using L=uint64_t;
void need(bool c,const char*s){if(!c)throw std::runtime_error(s);}
struct Stats{L cycles=0,requests=0,reads=0,writes=0,read_bytes=0,write_bytes=0;};
Stats run(bool fast,U w,U h,U c,U off=0,bool immediate=false,int alias=0,int abort=0,int invalid=0,bool warm=false,bool latch=false){
 static Vremaining_pad_top d;
 U src=1024+off,dst=524288+off;if(alias)dst=src+(alias==1?(c%4?1:8):0);
 U n=(w+2)*(h+2)*c;std::vector<uint8_t> mem(1048576,0xa5),seen(n),reference;
 std::mt19937 rng(w+h+c+off+(warm?999:0));for(U i=0;i<w*h*c;i++)mem[src+i]=rng();U fill=137;
 auto original=mem;reference=mem;
 U step=c%4?1:4;
 for(U y=0;y<h+2;y++)for(U x=0;x<w+2;x++)for(U k=0;k<c;k+=step){
  std::array<uint8_t,4> a{};bool border=!x||!y||x==w+1||y==h+1;
  for(U b=0;b<step;b++)a[b]=border?fill:reference[src+((y-1)*w+x-1)*c+k+b];
  for(U b=0;b<step;b++)reference[dst+(y*(w+2)+x)*c+k+b]=a[b];
 }
 auto cfg=[&]{d.source=src;d.destination=dst;d.width=w;d.height=h;d.channels=c;d.zero_point=fill;};
 auto tick=[&]{d.clk=1;d.eval();d.clk=0;d.eval();};
 d.optimized=fast;d.rst_n=warm;d.start=0;d.clear=0;d.ready=0;d.response=0;cfg();tick();tick();d.rst_n=1;tick();
 switch(invalid){case 1:d.width=0;break;case 2:d.height=0;break;case 3:d.channels=0;break;case 4:d.width=113;break;case 5:d.height=113;break;case 6:d.channels=513;break;case 7:d.source=src+1;d.channels=4;break;}
 d.start=1;tick();d.start=0;if(latch){d.width=0;d.source=0;d.zero_point=0;}
 bool pending=false,pwrite=false,holding=false,restarted=false;U pa=0,pn=0,pdata=0,delay=0,seq=0;std::array<U,4> held{};Stats s;L written=0;
 auto reply=[&]{d.rdata=0;if(pwrite){for(U b=0;b<pn;b++){need(!seen[pa-dst+b],"duplicate pad write");seen[pa-dst+b]=1;mem[pa+b]=pdata>>(8*b);written++;}}else for(U b=0;b<pn;b++)d.rdata|=U(mem[pa+b])<<(8*b);};
 for(L cycle=0;cycle<10000000;cycle++){
  if(abort&&!restarted&&((abort==1&&pending&&!pwrite)||(abort==2&&pending&&pwrite)||(abort==3&&d.phase==11))){
   d.clear=1;d.ready=0;d.response=0;tick();tick();pending=holding=false;d.clear=0;tick();mem=original;std::fill(seen.begin(),seen.end(),0);written=0;s={};cfg();d.start=1;tick();d.start=0;restarted=true;
  }
  bool resp=pending&&delay==0;d.response=resp;d.ready=!pending&&cycle%7>=2;d.rdata=0;if(resp)reply();d.eval();
  std::array<U,4> now={d.write,d.byte_access,d.addr,d.wdata};if(holding)need(d.valid&&held==now,"unstable pad request");holding=d.valid&&!d.ready;held=now;
  if(d.done){need(!pending&&!resp,"early pad done");need(!invalid,"bad pad descriptor accepted");break;}
  if(d.error){need(invalid&&s.requests==0,"unexpected pad error/access");return s;}
  if(d.valid&&d.ready){
   need(!pending&&!invalid,"pad outstanding/illegal access");pa=d.addr;pn=d.byte_access?1:4;pwrite=d.write;pdata=d.wdata;need(pn==1||pa%4==0,"unaligned pad word");
   if(pwrite){need(pa>=dst&&pa+pn<=dst+n,"pad write overrun");s.writes++;s.write_bytes+=pn;}
   else{need(pa>=src&&pa+pn<=src+w*h*c,"pad read overrun");s.reads++;s.read_bytes+=pn;}
   s.requests++;delay=seq++%7;pending=true;if(immediate){d.response=1;reply();d.eval();pending=false;}
  }else if(resp)pending=false;else if(pending)delay--;
  tick();s.cycles++;
 }
 need(d.done,"pad watchdog");need(!abort||restarted,"pad clear not tested");need(written==n,"pad coverage");
 for(U i=0;i<n;i++)need(mem[dst+i]==reference[dst+i],"pad numeric/alias mismatch");
 for(U i=1;i<=16;i++)need(mem[dst-i]==reference[dst-i]&&mem[dst+n+i-1]==reference[dst+n+i-1],"pad guard");return s;
}
int main(int argc,char**argv){try{
 need(argc==2,"metrics path");std::ofstream f(argv[1]);f<<"{\"status\":\"PASS\",\"cases\":[";U id=0;
 for(auto wh:std::vector<std::array<U,2>>{{3,2},{4,3},{7,5},{112,112}})for(U c:{1,3,4,7,16,512})for(U off:{0,1,2,3}){
  if((c%4==0&&off)||(wh[0]==112&&(c!=3||off)))continue;
  auto a=run(false,wh[0],wh[1],c,off),b=run(true,wh[0],wh[1],c,off);if(id)f<<',';
  f<<"{\"id\":"<<id++<<",\"width\":"<<wh[0]<<",\"height\":"<<wh[1]<<",\"channels\":"<<c<<",\"offset\":"<<off<<",\"old_cycles\":"<<a.cycles<<",\"new_cycles\":"<<b.cycles<<",\"old_requests\":"<<a.requests<<",\"new_requests\":"<<b.requests<<",\"old_reads\":"<<a.reads<<",\"new_reads\":"<<b.reads<<",\"old_read_bytes\":"<<a.read_bytes<<",\"new_read_bytes\":"<<b.read_bytes<<'}';
 }
 for(U c:{1,3,4,7,16})for(int alias:{1,2}){run(false,4,3,c,0,false,alias);run(true,4,3,c,0,false,alias);}
 for(U off:{0,1,2,3})run(true,5,3,3,off,true);
 for(int a:{1,2,3})run(true,7,5,3,0,false,0,a);
 for(int bad=1;bad<=7;bad++)run(true,3,2,3,0,false,0,0,bad);
 run(true,7,5,3);run(true,7,5,3,0,false,0,0,0,true);run(true,7,5,3,0,false,0,0,0,false,true);
 f<<"],\"alias_cases\":10,\"immediate_cases\":4,\"clear_restarts\":3,\"invalid_cases\":7,\"warm_reuse\":true}\n";
 std::cout<<"PASS pad rows cases="<<id<<std::endl;return 0;
 }catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<std::endl;return 1;}}
