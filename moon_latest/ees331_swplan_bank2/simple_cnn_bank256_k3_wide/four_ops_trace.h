#pragma once
#include <array>
#include <fstream>
#include <cstdint>

struct FourOpsTrace {
   static constexpr char tags[]="abcdefghijklmnopqrstuvwxyzABC";
   static constexpr unsigned signal_count=29;
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
     out<<"$var wire 3 "<<tags[28]<<" PAGER_STATE $end\n$upscope $end\n$enddefinitions $end\n";
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
     if(!initial && now==previous)return;
     out<<'#'<<uint64_t(cycle-first_cycle)*10<<'\n';
     for(unsigned i=0;i<signal_count;++i)if(initial || now[i]!=previous[i]){
       if(i>=28 || i%7==0){
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

