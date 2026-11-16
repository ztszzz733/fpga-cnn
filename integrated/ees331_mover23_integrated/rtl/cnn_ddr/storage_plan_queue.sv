// Plan LOAD/STORE queue. One shared DATA MOVER remains in flight at a time.
// The accepted-command credit covers the completion FIFO as well, so a
// backpressured plan response cannot overflow or lose a command identity.
module storage_plan_queue #(
 parameter integer DEPTH=4,
 parameter logic [31:0] DDR_BASE=32'h10000000,
 parameter logic [31:0] DDR_BYTES=32'h01000000,
 parameter logic [31:0] LOCAL_PHYS_BASE=32'h00010000,
 parameter logic [31:0] LOCAL_BYTES=32'h00052000,
 parameter logic [31:0] RAM_BYTES=32'h00062000
)(
 input logic clk,rst_n,recover,
 input logic [31:0] ddr_readonly_end,
 input logic cmd_valid,
 output wire cmd_ready,
 input logic [31:0] cmd_epoch,cmd_frame_id,cmd_id,
 input logic cmd_direction,
 input logic [31:0] cmd_ddr_offset,cmd_local_offset,cmd_bytes,
 output wire rsp_valid,
 input logic rsp_ready,
 output wire [31:0] rsp_epoch,rsp_frame_id,rsp_id,rsp_kind,rsp_status,
 output wire busy,drained,fault,
 output wire [31:0] accepted_count,completed_count,queue_wait_cycles,
 output wire pending_valid,
 output wire [31:0] pending_ddr_offset,pending_bytes,
 input logic mover_issue_permit,
 output wire mover_cmd_valid,
 input logic mover_cmd_ready,
 output wire [31:0] mover_cmd_src,mover_cmd_dst,mover_cmd_bytes,mover_cmd_flags,
 input logic mover_rsp_valid,
 output wire mover_rsp_ready,
 input logic [31:0] mover_rsp_status,mover_rsp_bytes_done,
 input logic mover_fault_locked,mover_drained,mover_busy
);
 localparam integer PW=(DEPTH<=2)?1:$clog2(DEPTH);
 localparam integer CW=$clog2(DEPTH+1);
 localparam logic [31:0] STATUS_ZERO=32'd2;
 localparam logic [31:0] STATUS_RANGE=32'd3;
 localparam logic [31:0] STATUS_ALIGN=32'd4;
 localparam logic [31:0] STATUS_TIMEOUT=32'd7;
 localparam logic [31:0] STATUS_READONLY=32'd8;
 localparam logic [31:0] STATUS_ABORTED=32'd11;
 localparam logic [31:0] STATUS_SHORT=32'd12;
 typedef struct packed {
  logic [31:0] epoch,frame_id,id,ddr_offset,local_offset,bytes,status;
  logic direction;
 } command_t;
 typedef struct packed {
  logic [31:0] epoch,frame_id,id,kind,status;
 } response_t;
 command_t command_mem[0:DEPTH-1];
 response_t response_mem[0:DEPTH-1];
 command_t active_command;
 logic [PW-1:0] command_read,command_write,response_read,response_write;
 logic [CW-1:0] command_count,response_count,outstanding;
 logic active,active_reported,fault_q;
 logic [31:0] accepted_q,completed_q,wait_q;
 wire [32:0] ddr_end={1'b0,cmd_ddr_offset}+{1'b0,cmd_bytes};
 wire [32:0] local_end={1'b0,cmd_local_offset}+{1'b0,cmd_bytes};
 wire [33:0] physical_end={2'b0,DDR_BASE}+{2'b0,cmd_ddr_offset}+{2'b0,cmd_bytes};
 logic [31:0] precheck_status;
 always_comb begin
  precheck_status=0;
  if(cmd_bytes==0)precheck_status=STATUS_ZERO;
  else if(ddr_end>{1'b0,DDR_BYTES} || local_end>{1'b0,LOCAL_BYTES} ||
          {1'b0,LOCAL_PHYS_BASE}+local_end>{1'b0,RAM_BYTES} ||
          physical_end>34'h100000000)precheck_status=STATUS_RANGE;
  else if(cmd_ddr_offset[2:0]!=0)precheck_status=STATUS_ALIGN;
  else if(cmd_direction && cmd_ddr_offset<ddr_readonly_end)
   precheck_status=STATUS_READONLY;
 end
 function automatic logic [PW-1:0] next_ptr(input logic [PW-1:0] pointer);
  return pointer==PW'(DEPTH-1) ? '0 : pointer+1'b1;
 endfunction
 wire command_take=cmd_valid && cmd_ready;
 wire response_take=rsp_valid && rsp_ready;
 wire command_head_valid=command_count!=0;
 wire command_head_bad=command_mem[command_read].status!=0;
 wire dispatch=mover_cmd_valid && mover_cmd_ready;
 wire active_done=active && mover_rsp_valid;
 wire active_fault_report=active && !active_reported && mover_fault_locked &&
                          !mover_rsp_valid;
 wire reject_head=command_head_valid &&
  ((!active && command_head_bad) ||
   ((fault_q || mover_fault_locked) && !active_done &&
    !(active && !active_reported)));
 wire command_pop=dispatch || reject_head;
 wire response_push=active_done && !active_reported ||
                    active_fault_report || reject_head;
 response_t pushed_response;
 always_comb begin
  pushed_response='0;
  if(active_done || active_fault_report)begin
   pushed_response.epoch=active_command.epoch;
   pushed_response.frame_id=active_command.frame_id;
   pushed_response.id=active_command.id;
   pushed_response.kind=active_command.direction ? 32'd2 : 32'd0;
   if(active_fault_report)pushed_response.status=
     mover_rsp_status!=0 ? mover_rsp_status : STATUS_TIMEOUT;
   else if(mover_rsp_status!=0)pushed_response.status=mover_rsp_status;
   else if(mover_rsp_bytes_done!=active_command.bytes)
    pushed_response.status=STATUS_SHORT;
  end else if(reject_head)begin
   pushed_response.epoch=command_mem[command_read].epoch;
   pushed_response.frame_id=command_mem[command_read].frame_id;
   pushed_response.id=command_mem[command_read].id;
   pushed_response.kind=command_mem[command_read].direction ? 32'd2 : 32'd0;
   pushed_response.status=command_head_bad ?
    command_mem[command_read].status : STATUS_ABORTED;
  end
 end
 assign cmd_ready=rst_n && !recover && !fault_q && !mover_fault_locked &&
                  outstanding<CW'(DEPTH);
 assign pending_valid=rst_n && !active && command_head_valid &&
                      !command_head_bad && !fault_q && !mover_fault_locked;
 assign pending_ddr_offset=command_mem[command_read].ddr_offset;
 assign pending_bytes=command_mem[command_read].bytes;
 assign mover_cmd_valid=pending_valid && mover_issue_permit;
 assign mover_cmd_src=command_mem[command_read].direction ?
                      LOCAL_PHYS_BASE+command_mem[command_read].local_offset :
                      command_mem[command_read].ddr_offset;
 assign mover_cmd_dst=command_mem[command_read].direction ?
                      command_mem[command_read].ddr_offset :
                      LOCAL_PHYS_BASE+command_mem[command_read].local_offset;
 assign mover_cmd_bytes=command_mem[command_read].bytes;
 assign mover_cmd_flags={31'b0,command_mem[command_read].direction};
 assign mover_rsp_ready=1'b1;
 assign rsp_valid=response_count!=0;
 assign rsp_epoch=response_mem[response_read].epoch;
 assign rsp_frame_id=response_mem[response_read].frame_id;
 assign rsp_id=response_mem[response_read].id;
 assign rsp_kind=response_mem[response_read].kind;
 assign rsp_status=response_mem[response_read].status;
 assign fault=fault_q || mover_fault_locked;
 assign busy=outstanding!=0 || mover_busy || active;
 assign drained=outstanding==0 && !active && mover_drained && !mover_busy;
 assign accepted_count=accepted_q;
 assign completed_count=completed_q;
 assign queue_wait_cycles=wait_q;
 always_ff @(posedge clk)begin
  if(!rst_n)begin
   command_read<='0;command_write<='0;command_count<='0;
   response_read<='0;response_write<='0;response_count<='0;
   outstanding<='0;active<=0;active_reported<=0;fault_q<=0;
   active_command<='0;accepted_q<=0;completed_q<=0;wait_q<=0;
  end else begin
   if(mover_fault_locked)fault_q<=1;
   if(cmd_valid && !cmd_ready)wait_q<=wait_q+1'b1;
   if(command_take)begin
    command_mem[command_write].epoch<=cmd_epoch;
    command_mem[command_write].frame_id<=cmd_frame_id;
    command_mem[command_write].id<=cmd_id;
    command_mem[command_write].direction<=cmd_direction;
    command_mem[command_write].ddr_offset<=cmd_ddr_offset;
    command_mem[command_write].local_offset<=cmd_local_offset;
    command_mem[command_write].bytes<=cmd_bytes;
    command_mem[command_write].status<=precheck_status;
    command_write<=next_ptr(command_write);
    accepted_q<=accepted_q+1'b1;
   end
   if(command_pop)command_read<=next_ptr(command_read);
   case({command_take,command_pop})
    2'b10:command_count<=command_count+1'b1;
    2'b01:command_count<=command_count-1'b1;
    default:;
   endcase
   if(dispatch)begin
    active_command<=command_mem[command_read];
    active<=1;active_reported<=0;
   end
   if(active_fault_report)begin
    active_reported<=1;
    fault_q<=1;
   end
   if(active_done)begin
    active<=0;
    if(mover_rsp_status!=0 || mover_rsp_bytes_done!=active_command.bytes)
     fault_q<=1;
   end
   if(response_push)begin
    response_mem[response_write]<=pushed_response;
    response_write<=next_ptr(response_write);
   end
   if(response_take)begin
    response_read<=next_ptr(response_read);
    completed_q<=completed_q+1'b1;
   end
   case({response_push,response_take})
    2'b10:response_count<=response_count+1'b1;
    2'b01:response_count<=response_count-1'b1;
    default:;
   endcase
   case({command_take,response_take})
    2'b10:outstanding<=outstanding+1'b1;
    2'b01:outstanding<=outstanding-1'b1;
    default:;
   endcase
   // The mover clears its old fault on this same clock edge.
   if(recover && drained)fault_q<=0;
  end
 end
`ifndef SYNTHESIS
 initial begin
  assert(DEPTH>=2 && LOCAL_PHYS_BASE+LOCAL_BYTES<=RAM_BYTES)
   else $fatal(1,"plan queue geometry");
  assert(DDR_BASE[2:0]==0 &&
         {1'b0,DDR_BASE}+{1'b0,DDR_BYTES}<=33'h100000000)
   else $fatal(1,"plan queue DDR aperture");
 end
 always_ff @(posedge clk)if(rst_n)begin
  assert(outstanding<=CW'(DEPTH) && command_count<=CW'(DEPTH) &&
         response_count<=CW'(DEPTH))else $fatal(1,"plan queue overflow");
  assert(!response_push || response_count<CW'(DEPTH) || response_take)
   else $fatal(1,"plan response overflow");
 end
`endif
endmodule
