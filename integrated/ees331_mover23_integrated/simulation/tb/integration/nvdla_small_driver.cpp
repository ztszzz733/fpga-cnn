// Bounded host bus stimulus; all operator arithmetic runs in upstream RTL.
#include "Vnvdla_small_harness.h"
#include "verilated.h"
#include <fstream>
#include <iostream>
#include <iomanip>
#include <stdexcept>
#include <string>
#include <vector>
#include <cstdint>

static Vnvdla_small_harness dut;
static uint64_t cycles=0, load_end=0, config_end=0, irq_cycle=0;
static unsigned phase=0;
static std::ofstream wave;
#ifdef TIMED_RAM
static void advance_to(uint64_t target) {
    while(dut.eventsPending() && dut.nextTimeSlot()<=target) {
        auto next=dut.nextTimeSlot();Verilated::timeInc(next-Verilated::time());dut.eval();
    }
    Verilated::timeInc(target-Verilated::time());
}
#endif
static void value(uint64_t v, unsigned width, const char* id) {
    static uint64_t previous[128]={};static bool seen[128]={};
    auto key=static_cast<unsigned char>(id[0]);
    if(seen[key] && previous[key]==v)return;
    previous[key]=v;seen[key]=true;
    wave << 'b'; for(int i=int(width)-1;i>=0;--i) wave << ((v>>i)&1);
    wave << ' ' << id << '\n';
}
static void sample(unsigned half) {
    wave << '#' << cycles*10+half*5 << '\n';
    value(dut.clk,1,"!"); value(dut.rst_n,1,"\""); value(phase,3,"#");
    value(dut.mmio_re,1,"$");value(dut.mmio_we,1,"%");value(dut.mmio_ready,1,"&");
    value(dut.mmio_addr,32,"'");value(dut.mmio_wdata,32,"(");value(dut.mmio_rdata,32,")");
    value(dut.config_state,2,"*");value(dut.read_state,3,"+");value(dut.write_state,3,",");
    value(dut.irq,1,"-");value(dut.fault,1,".");value(dut.read_beats,32,"/");value(dut.write_beats,32,":");
    value(dut.cnn_valid,11,";");value(dut.cnn_ready,11,"<");value(dut.cnn_response,11,"=");value(dut.cnn_write,11,">");
    value(dut.host_re,1,"?");value(dut.host_we,1,"@");value(dut.host_addr,32,"A");
}
static void tick() {
    if(cycles>=2000000) throw std::runtime_error("2,000,000-cycle safety limit");
    dut.clk=0;dut.eval(); sample(0);
#ifdef TIMED_RAM
    advance_to(cycles*10000+5000);
#endif
    dut.clk=1;dut.eval(); sample(1);
#ifdef TIMED_RAM
    advance_to((cycles+1)*10000);
#endif
    ++cycles;
    if(dut.fault) throw std::runtime_error("adapter/SRAM fault at cycle "+std::to_string(cycles));
}
static uint32_t reg(bool write,uint32_t addr,uint32_t data=0) {
    dut.mmio_addr=0x40000000+addr;dut.mmio_wdata=data;
    dut.mmio_we=write;dut.mmio_re=!write;
    unsigned count=0;
    do { tick(); if(++count>10000) throw std::runtime_error("CSB timeout at register "+std::to_string(addr)); } while(!dut.mmio_ready);
    auto v=dut.mmio_rdata;dut.mmio_we=0;dut.mmio_re=0;tick();return v;
}
static uint32_t memory_read(uint32_t addr) {
    dut.host_addr=addr;dut.host_re=1;tick();auto v=dut.host_rdata;dut.host_re=0;return v;
}
static void memory_write(uint32_t addr,uint32_t data,uint8_t mask=15) {
    dut.host_addr=addr;dut.host_wdata=data;dut.host_strb=mask;dut.host_we=1;tick();dut.host_we=0;
}
int main(int argc,char** argv) {
    Verilated::commandArgs(argc,argv);
    try {
        if(argc!=2) throw std::runtime_error("usage: executable commands.txt");
        wave.open("control.vcd");wave << "$timescale 1ns $end\n$scope module nvdla_small $end\n";
        const char* names[]={"clk","rst_n","phase","mmio_re","mmio_we","mmio_ready","mmio_addr","mmio_wdata","mmio_rdata","config_state","read_state","write_state","irq","fault","read_beats","write_beats","cnn_valid","cnn_ready","cnn_response","cnn_write","host_re","host_we","host_addr"};
        const char* ids[]={"!","\"","#","$","%","&","'","(",")","*","+",",","-",".","/",":",";","<","=",">","?","@","A"};
        const int widths[]={1,1,3,1,1,1,32,32,32,2,3,3,1,1,32,32,11,11,11,11,1,1,32};
        for(unsigned i=0;i<23;i++) wave << "$var wire " << widths[i]<<' '<<ids[i]<<' '<<names[i]<<" $end\n";
        wave << "$upscope $end\n$enddefinitions $end\n";
        dut.rst_n=0;for(int i=0;i<40;i++)tick();dut.rst_n=1;for(int i=0;i<100;i++)tick();
        std::ifstream commands(argv[1]);if(!commands)throw std::runtime_error("missing commands");
        std::string op;uint32_t a,b,c;unsigned checks=0;
        while(commands>>op) {
            if(op=="Z") {
                commands>>std::hex>>a>>b;phase=1;
                for(uint32_t i=0;i<b;i+=4)memory_write(a+i,0);
            } else if(op=="L") {
                std::string file;commands>>std::hex>>a>>file;phase=1;
                std::ifstream f(file,std::ios::binary);if(!f)throw std::runtime_error("missing payload "+file);
                char byte;while(f.get(byte)) {memory_write(a&~3u,uint32_t(uint8_t(byte))<<((a&3)*8),1u<<(a&3));++a;}
            } else if(op=="W") {
                commands>>std::hex>>a>>b;if(phase==1)load_end=cycles;phase=2;reg(true,a,b);
            } else if(op=="P") {
                commands>>std::hex>>a>>b>>c;
                unsigned tries=0;while((reg(false,a)&c)!=b) if(++tries>10000)throw std::runtime_error("register poll timeout");
            } else if(op=="I") {
                commands>>std::hex>>a;config_end=cycles;phase=3;
                while(!dut.irq) tick();
                auto status=reg(false,0x100c);
                if((status&a)!=a)throw std::runtime_error("unexpected interrupt status");
                irq_cycle=cycles;std::cout<<"IRQ cycle="<<std::dec<<cycles<<" status=0x"<<std::hex<<status<<std::endl;
            } else if(op=="C") {
                commands>>std::hex>>a>>b>>c;phase=4;uint32_t crc=~0u;
                std::ofstream dump("output.bin",std::ios::binary);
                for(uint32_t i=0;i<b;i+=4) {
                    auto v=memory_read(a+i);
                    for(unsigned j=0;j<4 && i+j<b;j++) {
                        uint8_t byte=(v>>(8*j))&255;dump.put(char(byte));crc^=byte;
                        for(unsigned bit=0;bit<8;bit++)crc=(crc>>1)^((crc&1)?0xedb88320u:0u);
                    }
                }
                crc=~crc;
                std::cout<<"CRC expected="<<std::hex<<c<<" actual="<<crc<<std::endl;
                if(crc!=c)throw std::runtime_error("output CRC mismatch");++checks;
            } else throw std::runtime_error("unknown operation "+op);
        }
        phase=5;for(int i=0;i<10;i++)tick();
        if(!checks || !dut.read_beats || !dut.write_beats)throw std::runtime_error("vacuous test");
        std::ofstream metrics("metrics.json");
        metrics<<"{\"cycles\":"<<cycles<<",\"load_end_cycle\":"<<load_end<<",\"config_end_cycle\":"<<config_end<<",\"irq_cycle\":"<<irq_cycle<<",\"read_beats\":"<<dut.read_beats<<",\"write_beats\":"<<dut.write_beats<<",\"crc_checks\":"<<checks<<",\"hardware_ns_at_100MHz\":"<<cycles*10<<"}\n";
        std::cout<<"PASS cycles="<<std::dec<<cycles<<" reads="<<dut.read_beats<<" writes="<<dut.write_beats<<std::endl;
        dut.final();wave.close();return 0;
    } catch(const std::exception& e) {std::cerr<<"FAIL: "<<e.what()<<std::endl;wave.close();return 1;}
}
