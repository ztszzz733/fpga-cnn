#include "Vhybrid_soc_harness.h"
#include "verilated.h"
#include <fstream>
#include <iostream>
#include <iomanip>
#include <stdexcept>
#include <string>
#include <cstdint>

static Vhybrid_soc_harness dut;
static uint64_t cycles=0,overlap_cycles=0,contention_cycles=0;
static std::ofstream wave;
static void advance_to(uint64_t target) {
    while(dut.eventsPending() && dut.nextTimeSlot()<=target) {
        auto t=dut.nextTimeSlot();Verilated::timeInc(t-Verilated::time());dut.eval();
    }
    Verilated::timeInc(target-Verilated::time());
}
static void value(uint64_t v,unsigned width,unsigned id) {
    static uint64_t prev[128]={};static bool seen[128]={};
    if(seen[id] && prev[id]==v)return;
    seen[id]=true;prev[id]=v;wave<<'b';
    for(int i=width-1;i>=0;i--)wave<<((v>>i)&1);
    wave<<' '<<char('!'+id)<<'\n';
}
#define SIGNALS(X) \
 X(clk,1) X(rst_n,1) X(phase,32) X(status,32) X(cpu_pc,32) \
 X(mmio_re,1) X(mmio_we,1) X(mmio_ready,1) X(mmio_addr,32) X(mmio_wdata,32) X(mmio_rdata,32) \
 X(cmd_busy,1) X(cmd_done,1) X(cmd_error,1) X(config_state,2) X(nv_irq,1) X(fault,1) \
 X(read_state,3) X(write_state,3) X(read_beats,32) X(write_beats,32) \
 X(vec_busy,1) X(vec_done,1) X(vec_jobs,32) X(vec_code,32) X(vec_state,3) X(vec_pending,32) \
 X(vec_reads,32) X(vec_writes,32) X(vec_stalls,32) \
 X(cnn_valid,11) X(cnn_ready,11) X(cnn_response,11) X(cnn_write,11) \
 X(vec_addr,32) X(vec_wdata,32) X(vec_rdata,32) X(uart_tx,1) X(load_req,1)
static void sample(unsigned half) {
    wave<<'#'<<cycles*10+half*5<<'\n';unsigned id=0;
#define SAMPLE(n,w) value(dut.n,w,id++);
    SIGNALS(SAMPLE)
#undef SAMPLE
}
static void tick() {
    dut.clk=0;dut.eval();sample(0);
    if(dut.vec_busy && (dut.cnn_valid&3))++overlap_cycles;
    if((dut.cnn_valid&4) && (dut.cnn_valid&3))++contention_cycles;
    advance_to(cycles*10000+5000);dut.clk=1;dut.eval();sample(1);
    advance_to((cycles+1)*10000);++cycles;
    if(cycles>=500000)throw std::runtime_error("500000-cycle timeout, PC="+std::to_string(dut.cpu_pc)+" phase="+std::to_string(dut.phase));
}
int main(int argc,char**argv) {
    Verilated::commandArgs(argc,argv);
    try {
        wave.open("control.vcd");wave<<"$timescale 1ns $end\n$scope module hybrid_soc $end\n";
        unsigned id=0;
#define DECLARE(n,w) wave<<"$var wire "<<w<<' '<<char('!'+id++)<<' '<<#n<<" $end\n";
        SIGNALS(DECLARE)
#undef DECLARE
        wave<<"$upscope $end\n$enddefinitions $end\n";
        dut.rst_n=0;for(int i=0;i<40;i++)tick();dut.rst_n=1;
        while(!dut.status){tick();if(dut.fault)throw std::runtime_error("hardware fault, vector code="+std::to_string(dut.vec_code));}
        for(int i=0;i<8;i++)tick();
        if(dut.status!=0x600dcafe)throw std::runtime_error("CPU reported failure: "+std::to_string(dut.status));
        std::ofstream dump("sram.bin",std::ios::binary);
        for(unsigned a=0;a<0x40000;a+=4){dut.debug_addr=a;dut.eval();uint32_t v=dut.debug_data;for(int j=0;j<4;j++)dump.put(char(v>>(8*j)));}
        std::ofstream metrics("metrics.json");
        metrics<<"{\n\"cycles\":"<<cycles<<",\n\"hardware_ns_at_100MHz\":"<<cycles*10
          <<",\n\"vector_jobs\":"<<dut.vec_jobs<<",\n\"vector_stall_cycles\":"<<dut.vec_stalls
          <<",\n\"vector_busy_nvdla_request_cycles\":"<<overlap_cycles
          <<",\n\"both_request_cycles\":"<<contention_cycles
          <<",\n\"nvdla_read_beats\":"<<dut.read_beats<<",\n\"nvdla_write_beats\":"<<dut.write_beats<<"\n}\n";
        std::cout<<"PASS CPU firmware completed cycles="<<cycles<<" vector_jobs="<<dut.vec_jobs<<std::endl;
        return 0;
    } catch(const std::exception& e) {std::cerr<<"FAIL "<<e.what()<<std::endl;return 1;}
}
