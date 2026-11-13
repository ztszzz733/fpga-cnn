`timescale 1ns/1ps
module tb_network_buffer_leases;
 logic clk=0;always #5 clk=~clk;
 logic rst_n=0,clear=0,cancel=0,program_accept=0,program_allocate_valid=0,reserve_commit=0;
 logic [9:0] program_index=0,candidate_node=0;
 logic [2:0] program_allocate_slot=0,program_use_valid=0;
 logic [1023:0] program_hold_mask=0,completed_mask=0;
 logic [8:0] program_use_slots=0;logic [29:0] program_use_owners=0;
 wire buffer_ready;wire [7:0] buffer_live,buffer_release,buffer_allocate;wire [79:0] buffer_owners;
 network_buffer_leases dut(.*,.external_hold(8'b0));
 task tick;@(posedge clk);#1;endtask
 initial begin
  repeat(2)tick();rst_n=1;tick();
  // Generation0 occupies slot0 until TWO independent consumers have drained.
  program_accept=1;program_index=0;program_allocate_valid=1;program_hold_mask=(1024'b1<<1)|(1024'b1<<2);tick();
  // A later producer wants the same physical slot; it must wait.
  program_index=3;program_hold_mask=(1024'b1<<4);tick();
  // A reader names the wrong generation, despite the slot being live.
  program_index=4;program_allocate_valid=0;program_use_valid=1;program_use_owners=3;tick();program_accept=0;
  candidate_node=0;#1;assert(buffer_ready)else $fatal(1,"initial free");reserve_commit=1;tick();reserve_commit=0;
  candidate_node=3;#1;assert(!buffer_ready)else $fatal(1,"occupied slot reused");
  candidate_node=4;#1;assert(!buffer_ready)else $fatal(1,"generation mismatch accepted");
  completed_mask[0]=1;completed_mask[2]=1;tick();assert(buffer_live==1 && buffer_release==0)else $fatal(1,"early residual release");
  completed_mask[1]=1;#1;assert(buffer_release==1)else $fatal(1,"all consumers not releasing");tick();assert(buffer_live==0)else $fatal(1,"not freed");
  candidate_node=3;#1;assert(buffer_ready)else $fatal(1,"cannot reuse");reserve_commit=1;tick();reserve_commit=0;
  candidate_node=4;#1;assert(buffer_ready && buffer_owners[9:0]==3)else $fatal(1,"new generation");
  completed_mask[4]=1;tick();assert(buffer_live==1)else $fatal(1,"producer not retained");
  completed_mask[3]=1;tick();assert(buffer_live==0)else $fatal(1,"second release");
  candidate_node=0;reserve_commit=1;tick();reserve_commit=0;cancel=1;tick();assert(buffer_live==0 && !buffer_ready)else $fatal(1,"cancel");
  $display("PASS live-slot backpressure, owner generation, out-of-order residual consumers, producer retention, reuse, cancel");$finish;
 end
endmodule
