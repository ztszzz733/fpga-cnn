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
     out<<"$var wire 1 "<<tags[29]<<" K3_0_PAIR_MAC $end\n";
     out<<"$var wire 1 "<<tags[30]<<" K3_1_PAIR_MAC $end\n";
     out<<"$var wire 1 "<<tags[31]<<" K3_0_QUAD_MAC $end\n";
     out<<"$var wire 1 "<<tags[32]<<" K3_1_QUAD_MAC $end\n";
     for(unsigned u=0;u<4;++u)
       out<<"$var wire 1 "<<tags[33+u]<<" "<<units[u]<<"_READ_256_ACCEPT $end\n";
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
     const auto pair=d.unit_work&d.k3_pair_mode&~d.k3_quad_mode;
     const auto quad=d.unit_work&d.k3_quad_mode;
     now[29]=pair&1;
     now[30]=(pair>>1)&1;
     now[31]=quad&1;
     now[32]=(quad>>1)&1;
     const auto wide_reads=d.cnn_valid&d.cnn_ready&d.cnn_wide&~d.cnn_write;
     for(unsigned u=0;u<4;++u)now[33+u]=(wide_reads>>u)&1;
     if(!initial && now==previous)return;
     out<<'#'<<uint64_t(cycle-first_cycle)*10<<'\n';
     for(unsigned i=0;i<signal_count;++i)if(initial || now[i]!=previous[i]){
       if(i==28 || (i<28 && i%7==0)){
         const unsigned width=i==28?3:4;
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

