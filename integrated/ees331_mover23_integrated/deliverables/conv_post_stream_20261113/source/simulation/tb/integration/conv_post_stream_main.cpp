#include "Vconv_post_stream_top.h"
#include "verilated.h"
#include "verilated_vcd_c.h"
#include <algorithm>
#include <array>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <memory>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>
using U=uint32_t;using L=uint64_t;using I=__int128;
void need(bool x,const std::string& s){if(!x)throw std::runtime_error(s);}
struct Spec{U k,w,h,ci,co,st=1,off=0;bool dw=false;U consumers=1;bool add=false;U nch=0;bool alias=false;U stalls=0;};
struct Stats{L cycles=0,read_bytes=0,write_bytes=0,requests=0,raw_reads=0,raw_writes=0,final_bytes=0,first_final=0,conv_finish=0,overlap=0,full=0,pushes=0,pops=0;U reason=0,macs=0;std::vector<uint8_t> output;};
struct Pending{bool pending=false,write=false,holding=false;U addr=0,data=0,bytes=0,delay=0,seq=0;std::array<U,4> held{};};
Stats run(Spec s,bool requested,const std::string& trace="",int restart=0,bool mutate=false,int invalid=0){
 auto ctx=std::make_unique<VerilatedContext>();ctx->traceEverOn(!trace.empty());
 auto dp=std::make_unique<Vconv_post_stream_top>(ctx.get());auto &d=*dp;
 std::unique_ptr<VerilatedVcdC> fst;std::ofstream csv;
 if(!trace.empty()){fst=std::make_unique<VerilatedVcdC>();d.trace(fst.get(),1);fst->open((trace+".vcd").c_str());csv.open(trace+".csv");csv<<"cycle,stream_active,conv_work,post_work,raw_push,raw_pop,fifo_level,conv_finished,final_write_ack,conv_read_ack,param_read_ack\n";}
 const U ib=4096+s.off,wb=262144+s.off,pb=524288,rb=1048576,ob=s.alias?ib:2097152+s.off,sb=3145728;
 const U ow=(s.w-s.k)/s.st+1,oh=(s.h-s.k)/s.st+1,n=ow*oh*s.co,nch=s.nch?s.nch:s.co;
 std::vector<uint8_t> mem(4*1024*1024,0xa5),seen(mem.size()),gold(n),raw;
 std::vector<uint8_t> x(s.w*s.h*s.ci);std::vector<int8_t> weights(s.co*s.k*s.k*(s.dw?1:s.ci));
 std::vector<std::array<int32_t,5>> params(nch);std::mt19937 rng(95271+s.ci+s.w*31+s.off);
 for(auto& v:x)v=rng()%256;for(auto& v:weights)v=int(rng()%256)-128;
 for(U y=0;y<oh;y++)for(U xx=0;xx<ow;xx++)for(U o=0;o<s.co;o++){
  int64_t a=0;
  for(U ky=0;ky<s.k;ky++)for(U kx=0;kx<s.k;kx++)for(U c=0;c<(s.dw?1:s.ci);c++)
   a+=int64_t(x[((y*s.st+ky)*s.w+xx*s.st+kx)*s.ci+(s.dw?o:c)])*weights[((o*s.k+ky)*s.k+kx)*(s.dw?1:s.ci)+c];
  for(U b=0;b<4;b++)raw.push_back((U(a)>>(b*8))&255);
 }
 const std::array<int32_t,8> mult={1,1,3,-7,131071,2147483647,-2147483647,79};
 const std::array<U,8> shifts={0,8,12,15,31,63,31,19};
 auto store=[&](U a,U v){for(U b=0;b<4;b++)mem[a+b]=(v>>(b*8))&255;};
 for(U c=0;c<nch;c++){
  U cfg=shifts[c%8]|((rng()%256)<<8)|((rng()%256)<<16)|((rng()%256)<<24);
  U lo=c%4==0?0:(rng()%64),hi=c%4==0?255:(192+rng()%64);
  params[c]={int32_t(rng()%2049)-1024,mult[c%8],int32_t(rng()%17)-8,int32_t(cfg),int32_t(lo|(hi<<8))};
  for(U j=0;j<5;j++)store(pb+20*c+4*j,U(params[c][j]));
 }
 for(U i=0;i<x.size();i++)mem[ib+i]=x[i];for(U i=0;i<weights.size();i++)mem[wb+i]=uint8_t(weights[i]);
 for(U i=0;i<n;i++)mem[sb+i]=rng()%256;
 for(U j=0;j<n;j++){
  auto p=params[j%nch];U cfg=U(p[3]),sh=cfg&63;
  I a=s.add?I(raw[j])-((cfg>>8)&255):I(int32_t(U(raw[4*j])|(U(raw[4*j+1])<<8)|(U(raw[4*j+2])<<16)|(U(raw[4*j+3])<<24)))+p[0];
  I value=a*p[1];if(s.add)value+=(I(mem[sb+j])-((cfg>>16)&255))*p[2];
  bool neg=value<0;I mag=neg?-value:value;if(sh)mag+=I(1)<<(sh-1);I rounded=mag>>sh;if(neg)rounded=-rounded;
  rounded+=(cfg>>24)&255;U lo=U(p[4])&255,hi=(U(p[4])>>8)&255;
  gold[j]=rounded<lo?lo:(rounded>hi?hi:U(rounded));
 }
 auto cfg=[&]{d.k1=s.k==1;d.request_stream=requested;d.consumer_count=s.consumers;d.post_add=s.add;d.depthwise=s.dw;
  d.input_base=ib;d.weight_base=wb;d.raw_base=rb;d.output_base=ob;d.parameter_base=pb;d.src_b=sb;
  d.width=s.w;d.height=s.h;d.in_channels=s.ci;d.out_channels=s.co;d.stride=s.st;d.post_count=n;d.post_channels=nch;};
 auto tick=[&]{d.clk=1;d.eval();if(fst)fst->dump(ctx->time());ctx->timeInc(5000);d.clk=0;d.eval();if(fst)fst->dump(ctx->time());ctx->timeInc(5000);};
 d.rst_n=0;d.clear=0;d.start=0;d.mem_ready=0;d.mem_response=0;d.mem_rdata=0;cfg();tick();tick();d.rst_n=1;tick();
 if(invalid==1)d.stride=3;
 if(invalid==2)store(pb+16,0x000001ff); // low255 > high1
 if(invalid==3)store(pb+12,64); // unsupported shift
 d.start=1;tick();d.start=0;
 if(mutate){d.input_base=0;d.raw_base=0;d.width=0;d.post_count=0;d.post_channels=0;d.parameter_base=0;d.request_stream=!requested;}
 Stats result;std::array<Pending,2> q{};bool restarted=false,had_done=false;
 auto commit=[&](int port,Pending &p){
  need(p.addr+p.bytes<=mem.size(),"memory overrun");
  if(p.write){
   bool is_final=port==1 && p.addr>=ob && p.addr+p.bytes<=ob+n;
   bool is_raw=port==0 && p.addr>=rb && p.addr+p.bytes<=rb+raw.size();
   need(is_final||is_raw,"write range");
   if(is_final){for(U b=0;b<p.bytes;b++){need(!seen[p.addr+b],"duplicate final byte");seen[p.addr+b]=1;}result.final_bytes+=p.bytes;if(!result.first_final)result.first_final=result.cycles;}
   else result.raw_writes+=p.bytes;
   for(U b=0;b<p.bytes;b++)mem[p.addr+b]=(p.data>>(b*8))&255;
  }
 };
 for(L cycle=0;cycle<10000000;cycle++){
  if(restart && !restarted && ((restart==1&&q[0].pending)||(restart==2&&d.fifo_level==8)||(restart==3&&q[1].pending&&q[1].write))){
   d.clear=1;d.mem_response=0;d.mem_ready=0;tick();need(d.mem_valid==0,"clear did not cancel");tick();d.clear=0;tick();
   q={};result={};std::fill(seen.begin(),seen.end(),0);std::fill(mem.begin()+rb,mem.begin()+rb+raw.size(),0xa5);
   std::fill(mem.begin()+ob,mem.begin()+ob+n,0xa5);cfg();d.start=1;tick();d.start=0;restarted=true;
  }
  U responses=0,readies=0;L rd=0;
  for(int p=0;p<2;p++){
   bool resp=q[p].pending&&q[p].delay==0;
   if(resp){responses|=1<<p;if(!q[p].write)for(U b=0;b<q[p].bytes;b++)rd|=L(mem[q[p].addr+b])<<(p*32+b*8);}
   bool allow=s.stalls==2 || (s.stalls==1?(cycle%29>=23):(cycle%7>=2));
   if(!q[p].pending&&allow)readies|=1<<p;
  }
  d.mem_response=responses;d.mem_ready=readies;d.mem_rdata=rd;d.clk=0;d.eval();
  bool final_ack=(responses&2)&&q[1].write;
  if(csv)csv<<result.cycles<<','<<U(d.stream_active)<<','<<U(d.conv_work)<<','<<U(d.post_work)<<','<<U(d.raw_push)<<','<<U(d.raw_pop)<<','<<U(d.fifo_level)<<','<<U(d.conv_finished)<<','<<final_ack<<','<<bool((responses&1)&&!q[0].write)<<','<<bool((responses&2)&&!q[1].write)<<'\n';
  result.reason=d.decision_reason;result.macs=d.conv_mac_count;
  if(d.conv_finished&&!result.conv_finish)result.conv_finish=result.cycles;
  if(d.post_work&&!d.conv_finished)result.overlap++;
  if(d.fifo_level==8)result.full++;
  result.pushes+=d.raw_push;result.pops+=d.raw_pop;
  if(d.error){need(invalid!=0,"unexpected RTL error");need(!d.mem_valid,"error left memory valid");if(fst)fst->close();return result;}
  if(d.done){need(!invalid,"invalid accepted");need(!q[0].pending&&!q[1].pending,"done before response");had_done=true;break;}
  for(int p=0;p<2;p++){
   U a=U(d.mem_addr>>(32*p)),data=U(d.mem_wdata>>(32*p)),wr=(d.mem_write>>p)&1,by=(d.mem_byte>>p)&1;
   bool v=(d.mem_valid>>p)&1,accept=v&&((readies>>p)&1),returned=(responses>>p)&1;
   std::array<U,4> now={a,data,wr,by};
   if(q[p].holding)need(v&&now==q[p].held,"request changed while stalled");
   q[p].holding=v&&!((readies>>p)&1);q[p].held=now;
   if(accept){
    need(!q[p].pending,"multiple outstanding on port");U bytes=by?1:4;need(bytes==1||a%4==0,"unaligned word");
    bool legal=wr?((p==0&&a>=rb&&a+bytes<=rb+raw.size())||(p==1&&a>=ob&&a+bytes<=ob+n)):
     ((p==0&&((a>=ib&&a+bytes<=ib+x.size())||(a>=wb&&a+bytes<=wb+weights.size())))||
      (p==1&&((a>=pb&&a+bytes<=pb+20*nch)||(a>=rb&&a+bytes<=rb+raw.size())||(s.add&&a>=sb&&a+bytes<=sb+n))));
    need(legal,"request outside described tensor");result.requests++;if(wr)result.write_bytes+=bytes;else{result.read_bytes+=bytes;if(a>=rb&&a<rb+raw.size())result.raw_reads+=bytes;}
    q[p].pending=true;q[p].write=wr;q[p].addr=a;q[p].data=data;q[p].bytes=bytes;
    q[p].delay=s.stalls==1?(p==1?35:11):(s.stalls==2?0:q[p].seq++%5);
    if(s.stalls==2){ // same-cycle ready/response path
     d.mem_response|=1<<p;d.mem_rdata&=~(L(0xffffffff)<<(32*p));
     if(wr)commit(p,q[p]);else for(U b=0;b<bytes;b++)d.mem_rdata|=L(mem[a+b])<<(32*p+8*b);
     d.eval();q[p].pending=false;
    }
   }else if(returned){if(q[p].write)commit(p,q[p]);q[p].pending=false;}
   else if(q[p].pending)q[p].delay--;
  }
  tick();result.cycles++;
 }
 need(had_done,"watchdog");need(!restart||restarted,"restart condition not reached");
 need(result.final_bytes==n,"final byte coverage");result.output.assign(mem.begin()+ob,mem.begin()+ob+n);need(result.output==gold,"numeric mismatch");
 if(result.reason==0){
  need(result.raw_reads==0&&result.raw_writes==0,"direct path touched raw memory");need(result.pushes==n&&result.pops==n,"FIFO lost/duplicated token");
  need(d.forwarded_count==n,"forwarded counter");for(U j=0;j<raw.size();j++)need(mem[rb+j]==0xa5,"raw canary changed");
 }else{need(result.raw_writes==4*L(n),"fallback did not preserve intermediate");need(std::equal(raw.begin(),raw.end(),mem.begin()+rb),"raw convolution mismatch");}
 need(result.macs==L(ow)*oh*s.co*s.k*s.k*(s.dw?1:s.ci),"MAC count mismatch");
 for(U b=1;b<=16;b++)if(!s.alias)need(mem[ob-b]==0xa5&&mem[ob+n+b-1]==0xa5,"final guard damaged");
 if(fst)fst->close();return result;
}
void emit(std::ofstream& f,const Stats& a){f<<"{\"cycles\":"<<a.cycles<<",\"read_bytes\":"<<a.read_bytes<<",\"write_bytes\":"<<a.write_bytes<<",\"requests\":"<<a.requests<<",\"raw_read_bytes\":"<<a.raw_reads<<",\"raw_write_bytes\":"<<a.raw_writes<<",\"first_final_ack\":"<<a.first_final<<",\"conv_finished\":"<<a.conv_finish<<",\"post_before_conv_done\":"<<a.overlap<<",\"fifo_full_cycles\":"<<a.full<<",\"reason\":"<<a.reason<<'}';}
int main(int argc,char** argv){try{
 need(argc==2,"run directory required");std::string dir=argv[1];std::ofstream f(dir+"/metrics.json");f<<"{\"status\":\"PASS\",\"cases\":[";unsigned id=0;
 std::vector<Spec> specs;
 for(U k:{1,3})for(U ci:{1,3,7,32,64})for(U stride:{1,2})for(U off:{0,1})specs.push_back({k,7,5,ci,9,stride,off});
 for(U k:{1,3})for(U ci:{128,256,512})specs.push_back({k,5,5,ci,3,1,3});
 specs.push_back({3,7,7,8,8,1,0,true});specs.push_back({3,7,7,8,8,2,1,true});
 specs.push_back({1,11,9,64,64});specs.push_back({1,11,9,128,128});specs.push_back({1,3,1,3,1});
 specs.push_back({3,3,3,3,1});specs.push_back({1,5,3,7,5,1,0,false,1,false,0,false,1});
 specs.push_back({3,5,5,3,5,1,0,false,1,false,0,false,1});
 specs.push_back({1,5,3,3,5,1,0,false,1,false,0,false,2});specs.push_back({3,5,5,3,5,1,0,false,1,false,0,false,2});
 L overlaps=0,full=0;
 for(auto s:specs){
  auto a=run(s,false),b=run(s,true);need(a.output==b.output,"mode mismatch");need(b.reason==0,"eligible refused");
  U n=((s.w-s.k)/s.st+1)*((s.h-s.k)/s.st+1)*s.co;
  need(a.raw_reads==4*L(n),"baseline raw read coverage");
  need(a.read_bytes+a.write_bytes==b.read_bytes+b.write_bytes+8*L(n),"saved byte mismatch");
  overlaps+=b.overlap;full+=b.full;
  if(id)f<<',';f<<"{\"id\":"<<id<<",\"kernel\":"<<s.k<<",\"width\":"<<s.w<<",\"height\":"<<s.h<<",\"ci\":"<<s.ci<<",\"co\":"<<s.co<<",\"stride\":"<<s.st<<",\"elements\":"<<n<<",\"memory\":";emit(f,a);f<<",\"direct\":";emit(f,b);f<<'}';
  std::cout<<"PASS pair "<<id++<<" k="<<s.k<<" cycles "<<a.cycles<<" -> "<<b.cycles<<std::endl;
 }
 need(overlaps>0&&full>0,"overlap/backpressure not exercised");
 for(U reason:{2,3,4,5}){
  Spec s{1,7,5,3,5};if(reason==2)s.consumers=2;if(reason==3)s.add=true;if(reason==4)s.nch=1;if(reason==5)s.alias=true;
  auto a=run(s,false),b=run(s,true);need(b.reason==reason,"fallback reason");need(a.output==b.output&&a.cycles==b.cycles,"fallback changed behavior");
 }
 for(U k:{1,3})for(int restart:{1,2,3})run({k,7,7,16,9,1,0,false,1,false,0,false,1},true,"",restart);
 for(U k:{1,3}){run({k,7,7,3,5},true,"",0,true);for(int invalid:{1,2,3})run({k,7,7,3,5},true,"",0,false,invalid);}
 for(U k:{1,3})for(bool stream:{false,true})run({k,7,7,8,9},stream,dir+"/"+(k==1?"pw8":"k3")+(stream?"_direct":"_memory"));
 f<<"],\"fallback_checks\":4,\"restart_checks\":6,\"descriptor_latch_checks\":2,\"invalid_checks\":6,\"trace_checks\":4,\"post_before_conv_done_cycles\":"<<overlaps<<",\"fifo_full_cycles\":"<<full<<"}\n";
 std::cout<<"PASS all "<<id<<" paired numerical cases + fallback/restart/latch/error"<<std::endl;return 0;
}catch(const std::exception& e){std::cerr<<"FAIL "<<e.what()<<std::endl;return 1;}}
