#pragma once
#include <array>
#include <vector>
#include <random>
#include <stdexcept>
#include <cstdint>
#include <string>
using U=uint32_t;using L=uint64_t;using I=__int128;
inline void need(bool b,const std::string& s){if(!b)throw std::runtime_error(s);}
using Command=std::array<U,16>;
struct TensorJob{Command conv{},post{};std::vector<uint8_t> raw,gold;U input_bytes=0,weight_bytes=0,n=0;};
inline void word(std::vector<uint8_t>& m,U a,U v){for(U b=0;b<4;b++)m[a+b]=(v>>(8*b))&255;}
inline std::vector<uint8_t> quant(const std::vector<uint8_t>& raw,U co,U pp,std::vector<uint8_t>& m,U seed){
 std::mt19937 g(seed);std::vector<std::array<int32_t,5>> ps(co);
 for(U c=0;c<co;c++){
  ps[c]={int32_t(g()%2049)-1024,int32_t(c%3==0?-3:(c%3==1?1:7)),0,int32_t((c%4==0?0:(c%4==1?9:(c%4==2?13:31)))|(128u<<24)),int32_t(c%2?0xe020:0xff00)};
  for(U j=0;j<5;j++)word(m,pp+c*20+j*4,U(ps[c][j]));
 }
 std::vector<uint8_t> out(raw.size()/4);
 for(U i=0;i<out.size();i++){
  U v=U(raw[4*i])|(U(raw[4*i+1])<<8)|(U(raw[4*i+2])<<16)|(U(raw[4*i+3])<<24);auto p=ps[i%co];
  I x=(I(int32_t(v))+p[0])*p[1];bool neg=x<0;I a=neg?-x:x;U sh=U(p[3])&63;
  if(sh)a+=I(1)<<(sh-1);I r=a>>sh;if(neg)r=-r;r+=(U(p[3])>>24)&255;
  U lo=U(p[4])&255,hi=(U(p[4])>>8)&255;out[i]=r<lo?lo:(r>hi?hi:U(r));
 }
 return out;
}
inline TensorJob make_job(std::vector<uint8_t>& m,U id,U k,U w,U h,U ci,U co,U stride,bool dw,U off,bool fused,const std::vector<uint8_t>* incoming=nullptr){
 TensorJob j;U base=id*0x80000,ib=base+0x1000+off,wb=base+0x10000+off,pb=base+0x30000,rb=base+0x40000,ob=base+0x60000+off;
 std::mt19937 rng(86791+id*31+ci);std::vector<uint8_t> x(w*h*ci);std::vector<int8_t> weights(co*k*k*(dw?1:ci));
 if(incoming){need(incoming->size()==x.size(),"incoming shape");x=*incoming;}else for(auto& v:x)v=rng()%256;
 for(auto& v:weights)v=int(rng()%256)-128;
 for(U i=0;i<x.size();i++)m[ib+i]=x[i];for(U i=0;i<weights.size();i++)m[wb+i]=uint8_t(weights[i]);
 U ow=(w-k)/stride+1,oh=(h-k)/stride+1;j.n=ow*oh*co;j.input_bytes=x.size();j.weight_bytes=weights.size();
 for(U y=0;y<oh;y++)for(U xx=0;xx<ow;xx++)for(U o=0;o<co;o++){
  int64_t sum=0;for(U ky=0;ky<k;ky++)for(U kx=0;kx<k;kx++)for(U c=0;c<(dw?1:ci);c++)sum+=int64_t(x[((y*stride+ky)*w+xx*stride+kx)*ci+(dw?o:c)])*weights[((o*k+ky)*k+kx)*(dw?1:ci)+c];
  for(U b=0;b<4;b++)j.raw.push_back((U(sum)>>(b*8))&255);
 }
 j.gold=quant(j.raw,co,pb,m,id+713);
 j.conv[0]=fused?(k==3?6:7):(k==3?0:5);j.conv[1]=ib;j.conv[2]=wb;j.conv[3]=fused?ob:rb;
 j.conv[4]=pb;j.conv[5]=j.n;j.conv[6]=ci;j.conv[7]=w;j.conv[8]=h;j.conv[9]=co;j.conv[10]=stride;j.conv[11]=dw;j.conv[12]=0xe0000000;
 j.post[0]=1;j.post[1]=rb;j.post[3]=ob;j.post[4]=pb;j.post[5]=j.n;j.post[6]=co;return j;
}
template<class DUT,int N>struct Memory{
 DUT& d;std::vector<uint8_t>& bytes;
 struct P{bool active=false,write=false,held=false;U a=0,data=0,n=0,delay=0,seq=0;std::array<U,4> saved{};};
 std::array<P,N> ps{};L reads=0,writes=0,requests=0;std::vector<U> seen;
 bool immediate=false,heavy=false;U cut_port=999;L cut_until=0;
 Memory(DUT& dut,std::vector<uint8_t>& m):d(dut),bytes(m),seen(m.size()){}
 void cancel(){ps={};d.mem_ready=0;d.mem_response=0;for(int p=0;p<N;p++)d.mem_rdata[p]=0;}
 void present(L t){
  d.mem_ready=0;d.mem_response=0;
  for(int p=0;p<N;p++){
   d.mem_rdata[p]=0;auto& q=ps[p];
   if(q.active && q.delay==0){d.mem_response|=1u<<p;if(!q.write)for(U b=0;b<q.n;b++)d.mem_rdata[p]|=U(bytes[q.a+b])<<(8*b);}
   if(!q.active && (immediate || (heavy?(t+p)%23>=17:(t+p)%7>=2)) && !(U(p)==cut_port && t<cut_until))d.mem_ready|=1u<<p;
  }
  d.clk=0;d.eval();
 }
 void commit(int p){auto& q=ps[p];if(q.write){for(U b=0;b<q.n;b++){need(seen[q.a+b]++==0,"duplicate written byte");bytes[q.a+b]=(q.data>>(b*8))&255;}}}
 void advance(){
  for(int p=0;p<N;p++){
   auto& q=ps[p];bool v=(d.mem_valid>>p)&1,accept=v&&((d.mem_ready>>p)&1),resp=(d.mem_response>>p)&1;
   std::array<U,4> a={d.mem_addr[p],d.mem_wdata[p],U((d.mem_write>>p)&1),U((d.mem_byte>>p)&1)};
   if(q.held)need(v&&a==q.saved,"request changed under backpressure");q.held=v&&!((d.mem_ready>>p)&1);q.saved=a;
   if(accept){
    need(!q.active,"multiple outstanding");q.a=a[0];q.data=a[1];q.write=a[2];q.n=a[3]?1:4;
    need(q.a+q.n<=bytes.size(),"memory address outside real SRAM (virtual result leaked)");need(q.n==1||q.a%4==0,"unaligned word");
    requests++;if(q.write)writes+=q.n;else reads+=q.n;q.active=true;q.delay=heavy?(p>=8?23:7):(q.seq++%5);
    if(immediate){d.mem_response|=1u<<p;d.mem_rdata[p]=0;if(q.write)commit(p);else for(U b=0;b<q.n;b++)d.mem_rdata[p]|=U(bytes[q.a+b])<<(8*b);d.eval();q.active=false;}
   }else if(resp){commit(p);q.active=false;}else if(q.active)q.delay--;
  }
 }
 bool pending()const{for(auto& q:ps)if(q.active)return true;return false;}
};
