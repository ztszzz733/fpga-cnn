`timescale 1ns/1ps
module tb_network_result_handoff;
 logic clk=0;always #5 clk=~clk;
 logic rst_n=0,clear=0,cancel=0,program_accept=0,program_allocate_valid=1,reserve_commit=0;
 logic program_result_valid=1,result_ready=0;
 logic [9:0] program_index=0,candidate_node=0;
 logic [2:0] program_allocate_slot=0,program_use_valid=0;
 logic [31:0] program_result_frame=10,program_result_addr=4096,program_result_bytes=16;
 logic [1023:0] program_hold_mask=0,completed_mask=0;
 logic [8:0] program_use_slots=0;logic [29:0] program_use_owners=0;
 wire buffer_ready;wire [7:0] buffer_live,buffer_release,buffer_allocate,external_hold,result_error;
 wire [79:0] buffer_owners;
 wire result_valid,result_accept,outputs_pending,configuration_error;
 wire [31:0] result_frame,result_addr,result_bytes;
 network_buffer_leases leases(.*);
 network_result_handoff handoff(.*);
 task tick;@(posedge clk);#1;endtask
 task reserve(input logic [9:0] node);
  candidate_node=node;#1;assert(buffer_ready)else $fatal(1,"reservation blocked");
  reserve_commit=1;tick();reserve_commit=0;
 endtask
 initial begin
  repeat(2)tick();rst_n=1;tick();
  program_accept=1;tick();
  program_index=1;program_allocate_slot=4;program_result_frame=20;program_result_addr=8192;tick();
  // Ordinary intermediate allocation in slot1 must still be released normally.
  program_index=2;program_allocate_slot=1;program_result_valid=0;tick();
  program_accept=0;reserve(0);reserve(1);reserve(2);
  result_ready=1;repeat(3)tick();
  assert(!result_valid && !result_accept && external_hold==8'h11)else $fatal(1,"early ready consumed unfinished result");
  result_ready=0;completed_mask[1]=1;completed_mask[2]=1;tick();
  assert(result_valid && result_frame==20 && result_addr==8192 && result_bytes==16 && !result_error)else $fatal(1,"out-of-order descriptor");
  assert(buffer_live==8'h11 && buffer_release==0)else $fatal(1,"intermediate/final retention");
  completed_mask[0]=1;
  repeat(12)begin tick();assert(result_valid && result_frame==20 && result_addr==8192 && buffer_live==8'h11 && buffer_release==0)else $fatal(1,"stalled descriptor/data ownership changed");end
  result_ready=1;tick();assert(result_accept && buffer_release==8'h10 && external_hold==1)else $fatal(1,"ack wrong slot");
  result_ready=0;tick();assert(result_valid && result_frame==10 && buffer_live==1)else $fatal(1,"second descriptor");
  result_ready=1;tick();assert(result_accept && buffer_release==1)else $fatal(1,"second ack");
  result_ready=0;tick();assert(!outputs_pending && !buffer_live && !result_valid)else $fatal(1,"not drained");
  // Clear while a descriptor is held; no stale acceptance may escape.
  completed_mask=0;reserve(0);completed_mask[0]=1;tick();assert(result_valid)else $fatal(1,"clear setup");
  clear=1;result_ready=1;#1;assert(!result_valid)else $fatal(1,"valid during clear");tick();
  assert(!result_accept && !buffer_live && !outputs_pending)else $fatal(1,"clear did not discard");
  clear=0;result_ready=0;completed_mask=0;reserve(1);completed_mask[1]=1;tick();
  cancel=1;#1;assert(!result_valid)else $fatal(1,"valid during fault cancel");tick();
  assert(!result_accept && !buffer_live && !outputs_pending)else $fatal(1,"cancel did not discard");
  cancel=0;program_accept=1;program_result_valid=1;program_allocate_valid=0;tick();
  assert(configuration_error)else $fatal(1,"missing output allocation accepted");
  program_accept=0;clear=1;tick();clear=0;
  program_accept=1;program_allocate_valid=1;program_result_bytes=0;tick();
  assert(configuration_error)else $fatal(1,"zero length accepted");
  program_accept=0;clear=1;tick();clear=0;
  program_accept=1;program_result_addr=32'hfffffff8;program_result_bytes=16;tick();
  assert(configuration_error)else $fatal(1,"address overflow accepted");
  $display("PASS result handoff: early ready, out-of-order completion, stable stalled descriptor, intermediate release, two acknowledgements, clear/cancel, malformed configuration");$finish;
 end
endmodule
