#include "Vbank_multi_top.h"
#include "verilated.h"
#include "ees331_axi_mover_model.hpp"
#include <array>
#include <deque>
#include <fstream>
#include <iostream>
#include <vector>
using U=uint32_t;using Q=uint64_t;
static void need(bool b,const char*s){if(!b)throw std::runtime_error(s);}
struct E{U value;};
int main(int argc,char**argv){try{
 Vbank_multi_top d;AxiDdr<Vbank_multi_top> ram(d);ram.stress=true;
 for(U a=0;a<6*1024*1024;a++)ram.data[a]=uint8_t(a*13+(a>>9)+7);
 std::vector<uint8_t> oracle=ram.data;
 d.rst_n=0;d.cnn_valid=d.cnn_write=d.cnn_byte=d.cnn_cancel=0;
 d.cache_csr_addr=d.cache_csr_wdata=d.cache_csr_re=d.cache_csr_we=0;
 auto tick=[&]{d.clk=0;ram.drive();d.eval();if(d.rst_n)ram.capture();d.clk=1;d.eval();d.clk=0;d.eval();};
 for(int i=0;i<5;i++)tick();d.rst_n=1;tick();
 // Establish four resident pages before measuring simultaneous compute-port
 // service. Otherwise the first stream can finish before the next miss fills.
 for(U f=0;f<4;f++){
  U a=0x10000+f*0x100000;d.cnn_addr[f]=a;d.cnn_wdata[f]=0;
  d.cnn_valid=1u<<f;bool accepted=false,returned=false;
  for(U n=0;n<20000&&!returned;n++){
   d.clk=0;ram.drive();d.eval();
   bool take=d.cnn_valid&d.cnn_ready;
   if(d.cnn_response>>f&1){U value=0;for(U b=0;b<4;b++)value|=U(oracle[a+b])<<(8*b);need(d.cnn_rdata[f]==value,"warm page read mismatch");returned=true;}
   ram.capture();d.clk=1;d.eval();d.clk=0;d.eval();
   if(take){accepted=true;d.cnn_valid=0;}
  }
  need(accepted&&returned,"warm page timeout");
 }
 std::array<U,4> issued{},replied{},peak{};std::array<std::deque<E>,4> q;
 std::array<bool,4> offered{};std::array<U,4> oa{},ov{};std::array<bool,4> ow{},ob{};
 Q cycles=0,accepted_cycles=0,multi_cycles=0,back_to_back=0;U previous=0;
 for(;cycles<12000000;cycles++){
  d.cnn_valid=d.cnn_write=d.cnn_byte=0;
  for(U f=0;f<4;f++){
   if(!offered[f]&&issued[f]<2304&&q[f].size()<4&&((cycles+f)%11!=0)){
    U n=issued[f];
    U page=n<128?0:1+((n-128)/8)%160;
    oa[f]=0x10000+f*0x100000+page*1024+((n%8)*4);ob[f]=n%19==0;
    if(ob[f])oa[f]+=n%4;
    ow[f]=n%5==0;ov[f]=0xa5f01e00u^(n*733+f*71);offered[f]=true;
   }
   if(offered[f]){
    d.cnn_valid|=1u<<f;if(ow[f])d.cnn_write|=1u<<f;if(ob[f])d.cnn_byte|=1u<<f;
    d.cnn_addr[f]=oa[f];d.cnn_wdata[f]=ov[f];
   }
  }
  d.clk=0;ram.drive();d.eval();need(!d.cnn_mem_fault,"bank fault");
  U accepts=d.cnn_valid&d.cnn_ready;
  if(accepts){accepted_cycles++;if((accepts&(accepts-1))!=0)multi_cycles++;if(accepts&previous)back_to_back++;}previous=accepts;
  for(U f=0;f<4;f++){
   if(d.cnn_response>>f&1){need(!q[f].empty(),"unsolicited response");need(U(d.cnn_rdata[f])==q[f].front().value,"response order/data mismatch");q[f].pop_front();replied[f]++;}
   if(accepts>>f&1){
    U a=oa[f],value=0;
    if(ow[f])for(U b=0;b<(ob[f]?1:4);b++)oracle[a+b]=uint8_t(ov[f]>>(8*b));
    else if(ob[f])value=U(int32_t(int8_t(oracle[a])));
    else for(U b=0;b<4;b++)value|=U(oracle[a+b])<<(8*b);
    q[f].push_back({value});peak[f]=std::max(peak[f],U(q[f].size()));need(q[f].size()<=4,"credit overflow");issued[f]++;offered[f]=false;
   }
  }
  ram.capture();d.clk=1;d.eval();d.clk=0;d.eval();
  bool finished=true;for(U f=0;f<4;f++)finished&=replied[f]==2304;
  if(finished)break;
 }
 std::cout<<"COUNTERS cycles="<<cycles<<" multi_bank="<<multi_cycles<<" consecutive="<<back_to_back<<std::endl;
 need(cycles<12000000,"watchdog");need(multi_cycles>0&&back_to_back>0,"bank parallel stream not exercised");
 // Fence the logical range and verify committed DDR bytes, not just replies.
 auto csr=[&](U a,U v){d.cache_csr_addr=a;d.cache_csr_wdata=v;d.cache_csr_we=1;tick();d.cache_csr_we=0;tick();};
 d.cnn_valid=0;csr(8,0);csr(12,6*1024*1024);csr(4,1);
 for(U i=0;i<1000000;i++){d.cache_csr_addr=0;d.cache_csr_re=1;d.eval();bool busy=d.cache_csr_rdata&2;d.cache_csr_re=0;if(!busy)break;tick();need(i<999999,"flush timeout");}
 for(U f=0;f<4;f++)for(U a=0x10000+f*0x100000;a<0x10000+f*0x100000+161*1024;a++)need(ram.data[a]==oracle[a],"DDR contents after flush mismatch");
 std::ofstream out(argv[1]);out<<"{\"status\":\"PASS\",\"clients\":4,\"requests_per_client\":2304,\"cycles\":"<<cycles<<",\"multi_bank_accept_cycles\":"<<multi_cycles<<",\"consecutive_accept_cycles\":"<<back_to_back<<",\"peak_pending\":[";
 for(U f=0;f<4;f++){if(f)out<<',';out<<peak[f];need(peak[f]>=2,"client never had multiple in flight");}out<<"],\"ddr_read_bytes\":"<<ram.read_bytes<<",\"ddr_write_bytes\":"<<ram.write_bytes<<",\"fenced_ddr_verified\":true}\n";
 std::cout<<"PASS four clients ordered replies, bank parallelism, byte/word writes, page crossings/evictions and DDR fence\n";return 0;
}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<"\n";return 1;}}
