#include "Vcnn_paged_mover.h"
#include "verilated.h"
#include "ees331_axi_mover_model.hpp"
#include <array>
#include <iostream>
#include <fstream>
#include <stdexcept>
using U=uint32_t;using Q=uint64_t;
static void need(bool c,const char*s){if(!c)throw std::runtime_error(s);}
struct Sample{U ready,response;std::array<U,12>data;};
struct Bench{
 Vcnn_paged_mover d;AxiDdr<Vcnn_paged_mover>ram{d};Q cycle=0;
 Bench(){
  d.rst_n=0;d.cnn_valid=d.cnn_write=d.cnn_byte=d.cnn_cancel=0;
  d.cache_csr_addr=d.cache_csr_wdata=d.cache_csr_we=d.cache_csr_re=0;
  for(int i=0;i<12;i++)d.cnn_addr[i]=d.cnn_wdata[i]=0;
  ram.stress=true;for(U i=0;i<1024;i++)ram.data[0x10000+i]=uint8_t(i*37+i/4);
  for(int i=0;i<5;i++)step();d.rst_n=1;step();warm();
 }
 Sample step(){
  need(cycle<1000000,"watchdog");d.clk=0;ram.drive();d.eval();
  Sample s{};s.ready=d.cnn_ready;s.response=d.cnn_response;for(int i=0;i<12;i++)s.data[i]=d.cnn_rdata[i];
  if(d.rst_n)ram.capture();d.clk=1;d.eval();d.clk=0;d.eval();cycle++;
  need(!d.cnn_mem_fault,"cache fault");return s;
 }
 U expected(U a){U v=0;for(unsigned j=0;j<4;j++)v|=U(ram.data[a+j])<<(j*8);return v;}
 void warm(){
  d.cnn_valid=1;d.cnn_addr[0]=0x10000;
  for(;;){auto s=step();if(s.ready&1)break;}d.cnn_valid=0;
  for(;;){auto s=step();if(s.response&1){need(s.data[0]==expected(0x10000),"warm read data");break;}}
 }
 Q pressure(unsigned clients,unsigned reads){
  std::array<bool,12>pending{};std::array<U,12>sent{},received{},address{};
  Q begin=cycle,bytes_before=ram.read_bytes;unsigned done=0;
  while(done<clients*reads){
   d.cnn_valid=0;
   for(unsigned k=0;k<clients;k++)if(!pending[k]&&sent[k]<reads){d.cnn_valid|=1u<<k;d.cnn_addr[k]=0x10000+((sent[k]*4+k*16)&1023);}
   auto s=step();
   for(unsigned k=0;k<clients;k++){
    if((s.response>>k)&1){need(pending[k],"response without request");need(s.data[k]==expected(address[k]),"concurrent read data/owner");pending[k]=false;received[k]++;done++;}
    if(((s.ready&d.cnn_valid)>>k)&1){need(!pending[k],"double request");pending[k]=true;address[k]=d.cnn_addr[k];sent[k]++;}
   }
  }
  d.cnn_valid=0;need(ram.read_bytes==bytes_before,"pressure phase was not fully cached");
  for(unsigned k=0;k<clients;k++)need(sent[k]==reads&&received[k]==reads,"client coverage");
  return cycle-begin;
 }
 Q miss_blocks_hit(){
  d.cnn_valid=1;d.cnn_addr[0]=0x20000;
  for(;;){auto s=step();if(s.ready&1)break;}
  d.cnn_valid=2;d.cnn_addr[1]=0x10000;Q offered=cycle,accepted=0,returned=0;bool miss_done=false,hit_done=false;
  while(!miss_done||!hit_done){
   auto s=step();
   if(s.response&1){need(s.data[0]==0xa5a5a5a5,"miss data");miss_done=true;}
   if((s.ready&d.cnn_valid)&2){accepted=cycle-1;d.cnn_valid=0;need(miss_done,"resident hit accepted before global miss completed");}
   if(s.response&2){need(accepted&&s.data[1]==expected(0x10000),"resident hit response");returned=cycle-1;hit_done=true;}
  }
  need(accepted>offered&&returned>accepted,"head-of-line test");return accepted-offered;
 }
};
int main(int argc,char**argv){try{
 Bench b;constexpr unsigned n=512;auto single=b.pressure(1,n),four=b.pressure(4,n),blocked=b.miss_blocks_hit();
 std::ofstream f(argv[1]);f<<"{\"status\":\"PASS\",\"clock_reference_hz\":100000000,\"local_bytes\":401408,\"clients_in_dut\":12,\"requests_per_active_client\":"<<n<<",\"one_client_cycles\":"<<single<<",\"four_clients_cycles\":"<<four<<",\"one_client_MBps\":"<<double(n)*4*100/single<<",\"four_clients_MBps\":"<<double(n)*4*4*100/four<<",\"cached_hit_blocked_by_other_client_miss_cycles\":"<<blocked<<"}\n";
 std::cout<<"PASS read pressure: one client "<<single<<" cycles / "<<double(n)*4*100/single<<" MB/s; four clients "<<four<<" cycles / "<<double(n)*16*100/four<<" MB/s; resident hit blocked "<<blocked<<" cycles by another client's page miss\n";
}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<"\n";return 1;}}
