// Actual edge sampling of the existing simulation, plus a focused GTKWave FST.
#include "fstapi.h"
#include <array>
#include <algorithm>
#include <fstream>
#include <iostream>
#include <map>
#include <string>
#include <vector>
enum {CLK,RX,RECV,PV,PR,PD,PF,COMPUTE,VALID,READY,RESPONSE,WRITE,BYTE,ADDR,DATA,DONE,FDONE,PE,N};
const std::array<std::string,N> names={"clk","uart_rx","rx_receiving","pixel_valid","pixel_ready","pixel_data","pixel_frame","compute_fire","cnn_valid","cnn_ready","cnn_response","cnn_write","cnn_byte","cnn_addr","cnn_wdata","frame_done","frames_done","pixel_eof"};
constexpr uint64_t END=226777100000ULL, BIN=250000000ULL;
struct Bin {uint64_t rx_ps=0,compute=0,writes=0,overlap=0;};
struct C {
 fstWriterContext* w;std::vector<int> index;std::vector<fstHandle> map;
 std::array<uint64_t,N> val{},before{};uint64_t now=0;
 std::vector<Bin> bins=std::vector<Bin>(END/BIN+1);
 std::ofstream detail,writes,events;std::array<uint64_t,2> totals{},computes{};
 std::array<bool,2> firstwrite{};
};
bool detailTime(uint64_t t){return (t>=858000000 && t<=858300000) || (t>=114244650000ULL && t<=114244950000ULL);}
void flush(C& c){
 if(!c.before[CLK] && c.val[CLK]){
  unsigned frame=c.before[PF];auto& b=c.bins[std::min(c.now/BIN,uint64_t(c.bins.size()-1))];
  if(c.before[PV] && c.before[PR] && c.before[PE])c.events<<c.now<<",pixel_eof_handshake,"<<frame<<",1\n";
  if(c.val[COMPUTE]){b.compute++;if(c.val[RECV])b.overlap++;if(frame<2)c.computes[frame]++;}
  auto mask=c.before[VALID]&c.before[READY]&c.before[WRITE];
  for(unsigned ch=0;ch<2;ch++)if(mask&(1<<ch)){
   b.writes++;if(frame<2)c.totals[frame]++;
   uint32_t addr=c.before[ADDR]>>(32*ch),data=c.before[DATA]>>(32*ch);
   c.writes<<c.now<<","<<frame<<","<<ch<<","<<addr<<","<<data<<"\n";
   if(frame<2 && !c.firstwrite[frame]){c.firstwrite[frame]=true;c.events<<c.now<<",first_write,"<<frame<<","<<addr<<"\n";}
  }
 }
 if(!c.before[DONE] && c.val[DONE])c.events<<c.now<<",frame_done,"<<c.val[FDONE]-1<<","<<c.val[FDONE]<<"\n";
 if(c.before[PE]!=c.val[PE])c.events<<c.now<<",pixel_eof_level,"<<c.val[PF]<<","<<c.val[PE]<<"\n";
}
void change(void* p,uint64_t t,fstHandle h,const unsigned char* raw){
 auto& c=*static_cast<C*>(p);if(t>END||h>=c.index.size()||c.index[h]<0)return;
 if(t!=c.now){
  flush(c);
  for(uint64_t start:{858000000ULL,114244650000ULL})if(c.now<start && t>=start)
   for(int j=0;j<N;j++)c.detail<<start<<","<<names[j]<<","<<c.val[j]<<"\n";
  if(c.val[RECV])for(auto a=c.now;a<t;){auto end=std::min(t,(a/BIN+1)*BIN);c.bins[a/BIN].rx_ps+=end-a;a=end;}
  c.before=c.val;c.now=t;fstWriterEmitTimeChange(c.w,t);
 }
 int i=c.index[h];uint64_t v=0;for(auto s=raw;*s;s++)v=(v<<1)|(*s=='1');c.val[i]=v;
 fstWriterEmitValueChange(c.w,c.map[h],raw);
 if(detailTime(t))c.detail<<t<<","<<names[i]<<","<<v<<"\n";
}
int main(int argc,char**argv){
 if(argc!=3)return 2;std::string out=argv[2];auto* r=fstReaderOpen(argv[1]);if(!r)return 3;
 C c;c.w=fstWriterCreate((out+"/first_two.fst").c_str(),1);c.index.resize(fstReaderGetMaxHandle(r)+1,-1);c.map.resize(c.index.size());
 c.detail.open(out+"/two_frame_detail.csv");c.detail<<"time_ps,signal,value\n";
 c.writes.open(out+"/two_frame_writes.csv");c.writes<<"time_ps,frame,channel,address,data\n";
 c.events.open(out+"/two_frame_events.csv");c.events<<"time_ps,event,frame,value\n";
 fstWriterSetTimescale(c.w,-12);fstWriterSetScope(c.w,FST_ST_VCD_MODULE,"stream_top",nullptr);
 std::vector<std::string> scope;int count=0;
 while(auto* h=fstReaderIterateHier(r)){
  if(h->htyp==FST_HT_SCOPE)scope.emplace_back(h->u.scope.name);
  else if(h->htyp==FST_HT_UPSCOPE)scope.pop_back();
  else if(h->htyp==FST_HT_VAR&&scope==std::vector<std::string>{"tb_soc_stream","dut"}){
   std::string full=h->u.var.name,base=full.substr(0,full.find(' '));auto it=std::find(names.begin(),names.end(),base);if(it==names.end())continue;
   auto handle=h->u.var.handle;c.index[handle]=it-names.begin();c.map[handle]=fstWriterCreateVar(c.w,FST_VT_VCD_WIRE,FST_VD_IMPLICIT,h->u.var.length,full.c_str(),0);fstReaderSetFacProcessMask(r,handle);count++;
  }
 }
 if(count!=N){std::cerr<<"missing signals "<<count;return 4;}
 fstWriterSetUpscope(c.w);fstWriterEmitTimeChange(c.w,0);fstReaderSetLimitTimeRange(r,0,END);fstReaderIterBlocks(r,change,&c,nullptr);flush(c);
 fstWriterEmitTimeChange(c.w,END);fstWriterClose(c.w);fstReaderClose(r);
 std::ofstream bins(out+"/two_frame_activity.csv");bins<<"start_ps,end_ps,rx_ps,compute_cycles,write_bytes,rx_compute_cycles\n";
 for(size_t i=0;i<c.bins.size();i++){auto& b=c.bins[i];bins<<i*BIN<<","<<std::min((i+1)*BIN,END)<<","<<b.rx_ps<<","<<b.compute<<","<<b.writes<<","<<b.overlap<<"\n";}
 for(int i=0;i<2;i++){std::cout<<"frame "<<i<<" writes="<<c.totals[i]<<" compute="<<c.computes[i]<<"\n";if(c.totals[i]!=136242||c.computes[i]!=272484)return 5;}
 return 0;
}
