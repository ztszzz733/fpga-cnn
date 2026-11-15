#include "Vtile_dma_system.h"
#include "verilated.h"
#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
using U=uint32_t;using Q=uint64_t;using Bytes=std::vector<uint8_t>;
static void need(bool ok,const std::string& what){if(!ok)throw std::runtime_error(what);}
static Bytes bytes(const std::filesystem::path&p){
 std::ifstream f(p,std::ios::binary);need(bool(f),"open "+p.string());
 return Bytes(std::istreambuf_iterator<char>(f),{});
}
struct Move{U s,d,n,dir;std::string phase,region;};
static std::vector<Move> moves(const std::filesystem::path&p){
 std::ifstream f(p);need(bool(f),"open moves");std::string line;std::getline(f,line);
 std::vector<Move> out;
 while(std::getline(f,line)){
  if(line.empty())continue;
  std::stringstream ss(line);std::vector<std::string> c;std::string v;
  while(std::getline(ss,v,','))c.push_back(v);
  need(c.size()==9,"moves columns");
  out.push_back({U(std::stoul(c[3])),U(std::stoul(c[4])),U(std::stoul(c[5])),U(std::stoul(c[6])),c[1],c[7]});
 }
 return out;
}
struct Group{U ddr,local,n,rows,ddr_stride,local_stride,dir;std::string region;};
static std::vector<Group> groups(const std::vector<Move>&m){
 std::vector<Group> out;
 for(size_t i=0;i<m.size();){
  size_t j=i+1;while(j<m.size()&&m[j].phase==m[i].phase&&m[j].region==m[i].region&&m[j].dir==m[i].dir&&m[j].n==m[i].n)j++;
  const bool wr=m[i].dir!=0;U ddr=wr?m[i].d:m[i].s,local=wr?m[i].s:m[i].d;
  U ds=j-i>1?(wr?m[i+1].d:m[i+1].s)-ddr:((m[i].n+7u)&~7u);
  U ls=j-i>1?(wr?m[i+1].s:m[i+1].d)-local:m[i].n;
  need(ds>=m[i].n && ds%8==0 && ls>=m[i].n,"row strides");
  for(size_t k=i;k<j;k++){
   need((wr?m[k].d:m[k].s)==ddr+U(k-i)*ds,"DDR row sequence");
   need((wr?m[k].s:m[k].d)==local+U(k-i)*ls,"local row sequence");
  }
  out.push_back({ddr,local,m[i].n,U(j-i),ds,ls,m[i].dir,m[i].region});i=j;
 }
 return out;
}
struct Bench{
 Vtile_dma_system d;Bytes ddr;Q cycles=0,read_beats=0,write_beats=0;
 bool ar=false,aw=false,wd=false;U ra=0,wa=0;unsigned rs=0,ws=0,rdly=0,bdly=0;Q wb=0;unsigned strobe=0;
 void tick(){
  d.clk=0;d.arready=!ar && cycles%4!=0;d.awready=!aw && cycles%3!=0;d.wready=!wd && cycles%5!=0;
  d.rvalid=ar && rdly==0;d.rlast=1;d.rid=0;d.rresp=0;d.rdata=0;
  if(d.rvalid)for(U i=0;i<(1u<<rs);i++)d.rdata|=Q(ddr.at(ra+i))<<(8*((ra+i)&7));
  d.bvalid=aw&&wd&&bdly==0;d.bid=0;d.bresp=0;
  d.eval();
  bool tar=d.arvalid&&d.arready,tr=d.rvalid&&d.rready,
       taw=d.awvalid&&d.awready,tw=d.wvalid&&d.wready,tb=d.bvalid&&d.bready;
  if(tar){
   need(d.arid==0&&d.arlen==0&&d.arburst==1,"AR shape");
   ra=d.araddr-0x10000000;rs=d.arsize;
   need((ra&((1u<<rs)-1))==0&&Q(ra)+(1u<<rs)<=ddr.size(),"AR bounds");
   need((d.araddr&4095)+(1u<<rs)<=4096,"AR 4KiB");
  }
  if(taw){
   need(d.awid==0&&d.awlen==0&&d.awburst==1,"AW shape");
   wa=d.awaddr-0x10000000;ws=d.awsize;
   need((wa&((1u<<ws)-1))==0&&Q(wa)+(1u<<ws)<=ddr.size(),"AW bounds");
   need((d.awaddr&4095)+(1u<<ws)<=4096,"AW 4KiB");
  }
  if(tw){wb=d.wdata;strobe=d.wstrb;need(d.wlast&&d.wid==0,"W shape");}
  d.clk=1;d.eval();cycles++;
  if(ar&&rdly)rdly--;if(aw&&wd&&bdly)bdly--;
  if(tr){ar=false;read_beats++;}if(tb){
   need(strobe==(((1u<<(1u<<ws))-1)<<(wa&7)),"write strobe");
   for(unsigned i=0;i<8;i++)if(strobe>>i&1)ddr.at((wa&~7u)+i)=wb>>(8*i);
   aw=false;wd=false;write_beats++;
  }
  if(tar){ar=true;rdly=2+cycles%5;}if(taw){aw=true;bdly=3+cycles%7;}if(tw)wd=true;
 }
 void reset(){d.rst_n=0;d.enable=1;d.recover=0;d.start_valid=0;d.done_ready=0;
  d.comp_req=0;d.cfg_ddr_base=0x10000000;d.cfg_ddr_bytes=65536;tick();d.rst_n=1;tick();}
 void write_word(U addr,U data,unsigned mask=15){
  d.comp_addr=addr;d.comp_wdata=data;d.comp_wstrb=mask;d.comp_we=1;d.comp_req=1;tick();
  need(!d.comp_error,"compute write");d.comp_req=0;
 }
 U read_word(U addr){d.comp_addr=addr;d.comp_we=0;d.comp_req=1;tick();
  need(!d.comp_error,"compute read");U x=d.comp_rdata;d.comp_req=0;return x;}
 void initialize(const Bytes&local){need(local.size()==32768,"local fixture size");
  for(U a=0;a<local.size();a+=4){U w=0;for(U k=0;k<4;k++)w|=U(local[a+k])<<(8*k);write_word(a,w);}
 }
 void check_local(const Bytes&expected){for(U a=0;a<expected.size();a+=4){
  U w=0;for(U k=0;k<4;k++)w|=U(expected[a+k])<<(8*k);
  need(read_word(a)==w,"local mismatch at "+std::to_string(a));
 }}
 void run(const Group&g,U status=0,bool conflict=false,bool drift=false){
  d.start_ddr=g.ddr;d.start_local=g.local;d.start_row_bytes=g.n;
  d.start_rows=g.rows;d.start_ddr_stride=g.ddr_stride;
  d.start_local_stride=g.local_stride;d.start_write=g.dir;
  d.start_valid=1;d.eval();need(d.start_ready,"row controller ready");tick();d.start_valid=0;
  if(drift){d.enable=0;d.cfg_ddr_base=0x20000000;d.cfg_ddr_bytes=0;}
  if(conflict){
   d.comp_addr=g.local&~3u;d.comp_req=1;d.comp_we=0;
   for(unsigned k=0;k<40;k++){tick();need(!d.done_valid,"same-word compute priority");}
   d.comp_req=0;
  }
  for(unsigned k=0;!d.done_valid;k++){need(k<500000,"tile DMA timeout");tick();}
  need(d.done_status==status,"row status "+g.region);
  need(d.done_rows==(status?0:g.rows),"completed row count");
  for(unsigned k=0;k<3;k++){tick();need(d.done_valid&&!d.start_ready,"held row response");}
  d.done_ready=1;tick();d.done_ready=0;
  if(drift){d.enable=1;d.cfg_ddr_base=0x10000000;d.cfg_ddr_bytes=65536;}
  need(!d.fault_locked&&d.drained,"idle after rows");
 }
};
int main(int argc,char**argv){try{
 need(argc==2,"case directory argument");std::filesystem::path root=argv[1];
 Bench b;b.reset();unsigned total_groups=0,total_rows=0;
 for(const char*name:{"short_row_2x2x2","tile_8x8x32"}){
  auto p=root/name;auto initial=bytes(p/"ddr_initial.bin");auto local=bytes(p/"local_initial.bin");
  auto expected_ddr=bytes(p/"ddr_expected.bin");auto golden=bytes(p/"golden_add_uint8.bin");
  auto list=moves(p/"moves.csv");auto gs=groups(list);need(initial.size()==65536,"DDR fixture size");
  b.ddr=initial;b.initialize(local);Bytes shadow=local;
  bool collision_done=false;size_t golden_pos=0;
  for(auto&g:gs)if(!g.dir){
   b.run(g,0,!collision_done && g.local==0,!collision_done && g.local==0);
   if(g.local==0)collision_done=true;
   for(U row=0;row<g.rows;row++)for(U i=0;i<g.n;i++)
    shadow.at(g.local+row*g.local_stride+i)=initial.at(g.ddr+row*g.ddr_stride+i);
   total_groups++;total_rows+=g.rows;
  }
  b.check_local(shadow);need(b.ddr==initial,"DDR changed during loads");
  // The CNN arithmetic is outside this fixture: inject its frozen golden
  // through the real compute port, then verify DMA writeback and guard bytes.
  for(auto&g:gs)if(g.dir){
   for(U row=0;row<g.rows;row++)for(U i=0;i<g.n;i++){
    need(golden_pos<golden.size(),"golden too short");U a=g.local+row*g.local_stride+i;
    U byte=golden[golden_pos++];b.write_word(a&~3u,byte<<(8*(a&3)),1u<<(a&3));shadow.at(a)=byte;
   }
   b.run(g);total_groups++;total_rows+=g.rows;
  }
  need(golden_pos==golden.size(),"golden too long");
  b.check_local(shadow);need(b.ddr==expected_ddr,"DDR output or guard mismatch");
  std::cout<<"PASS tile_dma_system "<<name<<" groups="<<gs.size()<<" rows="<<list.size()<<"\n";
 }
 // Invalid geometry must not reach AXI. The status stays visible until ack.
 Q before=b.read_beats+b.write_beats;
 b.run({4096,0,8,0,8,8,0,"zero_rows"},1);
 b.run({4097,0,8,1,8,8,0,"unaligned_ddr"},4);
 b.run({0xfffffff0,0,8,3,8,8,0,"late_overflow"},3);
 b.run({65520,0,8,3,8,8,0,"late_ddr_window"},3);
 b.run({4096,32752,8,3,8,8,0,"late_local_window"},3);
 b.run({4096,0,8,4097,8,8,0,"too_many_rows"},1);
 need(before==b.read_beats+b.write_beats,"invalid geometry issued bus access");
 std::cout<<"PASS tile_dma_system total_groups="<<total_groups<<" total_rows="<<total_rows
          <<" read_beats="<<b.read_beats<<" write_beats="<<b.write_beats
          <<" cycles="<<b.cycles<<"\n";
}catch(std::exception&e){std::cerr<<"FAIL tile_dma_system: "<<e.what()<<"\n";return 1;}}
