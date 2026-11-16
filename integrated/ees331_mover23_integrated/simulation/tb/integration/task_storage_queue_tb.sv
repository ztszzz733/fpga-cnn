`timescale 1ns/1ps
module task_storage_queue_tb;
 logic clk=0;
 always #5 clk=~clk;
 logic rst_n=0,recover=0;
 logic [31:0] ddr_readonly_end=0;
 logic cmd_valid=0,cmd_direction=0;
 logic [31:0] cmd_epoch=0,cmd_frame_id=0,cmd_id=0;
 logic [31:0] cmd_ddr_offset=0,cmd_local_offset=0,cmd_bytes=0;
 wire cmd_ready,rsp_valid,busy,drained,fault;
 logic rsp_ready=0;
 wire [31:0] rsp_epoch,rsp_frame_id,rsp_id,rsp_kind,rsp_status;
 wire [31:0] accepted_count,completed_count,queue_wait_cycles;
 wire mover_cmd_valid,mover_rsp_ready;
 wire pending_valid;
 wire [31:0] pending_ddr_offset,pending_bytes;
 logic mover_issue_permit=1;
 logic mover_cmd_ready=0,mover_rsp_valid=0,mover_fault_locked=0;
 logic mover_drained=1,mover_busy=0;
 logic [31:0] mover_rsp_status=0,mover_rsp_bytes_done=0;
 wire [31:0] mover_cmd_src,mover_cmd_dst,mover_cmd_bytes,mover_cmd_flags;
 storage_plan_queue dut(.*);
 task automatic submit(input logic [31:0] id,
                       input logic direction,
                       input logic [31:0] ddr,loc,bytes);
  @(negedge clk);
  cmd_valid=1;cmd_epoch=32'h22;cmd_frame_id=32'h77;cmd_id=id;
  cmd_direction=direction;cmd_ddr_offset=ddr;
  cmd_local_offset=loc;cmd_bytes=bytes;
  if(!cmd_ready)$fatal(1,"command unexpectedly not ready");
  @(negedge clk);cmd_valid=0;
 endtask
 task automatic dispatch(input logic [31:0] src,dst,bytes,flags);
  @(negedge clk);
  if(!mover_cmd_valid || mover_cmd_src!=src || mover_cmd_dst!=dst ||
     mover_cmd_bytes!=bytes || mover_cmd_flags!=flags)
   $fatal(1,"MOVER descriptor mismatch: %h %h %h %h",mover_cmd_src,
          mover_cmd_dst,mover_cmd_bytes,mover_cmd_flags);
  mover_cmd_ready=1;
  @(negedge clk);mover_cmd_ready=0;mover_busy=1;mover_drained=0;
 endtask
 task automatic complete_mover(input logic [31:0] bytes);
  @(negedge clk);
  mover_rsp_valid=1;mover_rsp_status=0;mover_rsp_bytes_done=bytes;
  @(negedge clk);
  mover_rsp_valid=0;mover_busy=0;mover_drained=1;
 endtask
 task automatic consume(input logic [31:0] id,kind,status);
  @(negedge clk);
  if(!rsp_valid || rsp_id!=id || rsp_epoch!=32'h22 ||
     rsp_frame_id!=32'h77 || rsp_kind!=kind || rsp_status!=status)
   $fatal(1,"completion mismatch: expected id=%h kind=%h status=%h, got epoch=%h frame=%h id=%h kind=%h status=%h",
     id,kind,status,rsp_epoch,rsp_frame_id,rsp_id,rsp_kind,rsp_status);
  rsp_ready=1;
  @(negedge clk);rsp_ready=0;
 endtask
 initial begin
  repeat(3)@(negedge clk);
  rst_n=1;
  submit(10,0,0,16,16);
  submit(11,1,8,32,4);
  dispatch(0,32'h00010010,16,0);
  complete_mover(16);
  repeat(2)begin
   @(negedge clk);
   if(!rsp_valid || rsp_id!=10 || rsp_status!=0)
    $fatal(1,"backpressured completion changed");
  end
  dispatch(32'h00010020,8,4,1);
  complete_mover(4);
  consume(10,0,0);
  consume(11,2,0);
  submit(12,0,0,0,0);
  consume(12,0,2);
  if(accepted_count!=3 || completed_count!=3 || !drained)
   $fatal(1,"normal queue counters/drain wrong");

  submit(20,0,16,0,8);
  submit(21,0,24,8,8);
  dispatch(16,32'h00010000,8,0);
  @(negedge clk);
  mover_fault_locked=1;
  mover_rsp_status=7;
  repeat(2)@(negedge clk);
  if(!fault || drained || cmd_ready)$fatal(1,"fault did not lock queue");
  consume(20,0,7);
  consume(21,0,11);
  if(drained)$fatal(1,"late AXI response was not held in drain state");
  @(negedge clk);mover_rsp_valid=1;
  @(negedge clk);mover_rsp_valid=0;mover_busy=0;mover_drained=1;
  @(negedge clk);
  if(rsp_valid || !drained)$fatal(1,"late response duplicated a completion");
  mover_fault_locked=0;recover=1;
  @(negedge clk);recover=0;
  @(negedge clk);
  if(fault || accepted_count!=5 || completed_count!=5)
   $fatal(1,"recovery or identity counts wrong");
  $display("PASS plan command queue identity, backpressure, fault and drain");
  $finish;
 end
 initial begin
  #10000;
  $fatal(1,"test timeout");
 end
endmodule
