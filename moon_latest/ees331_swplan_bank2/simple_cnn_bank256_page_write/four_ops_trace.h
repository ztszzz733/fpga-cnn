#pragma once
#include <array>
#include <fstream>
#include <cstdint>

struct FourOpsTrace {
   static constexpr char tags[]="abcdefghijklmnopqrstuvwxyzABCDEFGHIJK";
   static constexpr unsigned signal_count=37;
   std::array<unsigned,signal_count> previous{};
   std::ofstream out;
   bool initial=true;
   unsigned first_cycle=0;
   void open(unsigned cycle) {
     first_cycle=cycle;
     out.open("four_ops.vcd");
     out<<"$timescale 1ns $end\n$scope module four_ops $end\n";
     const char* units[]={"K3_0","K3_1","K1_0","K1_1"};
     const char* signals[]={"STATE","BUSY","MAC","READ","WRITE","WRITE_256_ACCEPT","DONE"};
     for(unsigned u=0;u<4;++u)
       for(unsigned s=0;s<7;++s)
         out<<"$var wire "<<(s==0?4:1)<<" "<<tags[u*7+s]<<" "<<units[u]<<"_"<<signals[s]<<" $end\n";
     out<<"$var wire 3 "<<tags[28]<<" PAGER_STATE $end\n";
     const char* names[]={"PAGE_LEN","PAGE_ACK","BANK_WRITE256","WAIT_OUTPUT_SLOT"};
     for(unsigned k=0;k<2;++k)
       for(unsigned s=0;s<4;++s)
         out<<"$var wire "<<(s==0?6:1)<<" "<<tags[29+k*4+s]<<" "<<units[2+k]<<"_"<<names[s]<<" $end\n";
     out<<"$upscope $end\n$enddefinitions $end\n";
   }
   void sample(const Vburst_bank_test& d,unsigned cycle) {
     if(!out.is_open())return;
     std::array<unsigned,signal_count> now{};
     for(unsigned u=0;u<4;++u) {
       now[u*7]=(d.operator_phase>>(4*u))&15;
       now[u*7+1]=(d.unit_busy>>u)&1;
       now[u*7+2]=(d.unit_work>>u)&1;
       now[u*7+3]=(d.read_active>>u)&1;
       now[u*7+4]=(d.write_active>>u)&1;
       now[u*7+5]=((d.mem_write_beat&d.cnn_wide)>>u)&1;
       now[u*7+6]=(d.unit_done>>u)&1;
     }
     now[28]=d.pager_phase;
     for(unsigned k=0;k<2;++k){
       const unsigned u=k+2,index=29+k*4;
       now[index]=((d.mem_write_beat>>u)&1)?(d.cnn_burst_len>>(6*u))&63:0;
       now[index+1]=((d.cnn_response&d.write_active)>>u)&1;
       now[index+2]=(d.bank_wide_commit>>u)&1;
       now[index+3]=(d.k1_full_stall>>k)&1;
     }
     if(!initial && now==previous)return;
     out<<'#'<<uint64_t(cycle-first_cycle)*10<<'\n';
     for(unsigned i=0;i<signal_count;++i)if(initial || now[i]!=previous[i]){
       const unsigned width=i<28 ? (i%7==0?4:1) : i==28 ? 3 : (i-29)%4==0 ? 6 : 1;
       if(width>1){
         out<<'b';
         for(unsigned b=width;b>0;--b)out<<((now[i]>>(b-1))&1);
         out<<' '<<tags[i]<<'\n';
       }else out<<now[i]<<tags[i]<<'\n';
     }
     previous=now;
     initial=false;
   }
   void finish(unsigned cycle) {
     if(!out.is_open())return;
     out<<'#'<<uint64_t(cycle-first_cycle+1)*10<<'\n';
     out.close();
   }
};

