// Converts a strided tile into ordered one-dimensional DATA MOVER commands.
// All DDR row starts must be 8-byte aligned; local starts may be unaligned.
module tile_row_dma #(
 parameter integer MAX_ROWS=4096
)(
 input  logic        clk,rst_n,enable,
 input  logic        start_valid,
 output wire         start_ready,
 input  logic        start_write,
 input  logic [31:0] start_ddr,start_local,start_row_bytes,
 input  logic [31:0] start_rows,start_ddr_stride,start_local_stride,
 input  logic [31:0] cfg_ddr_bytes,cfg_local_bytes,
 output wire         cmd_valid,
 input  logic        cmd_ready,
 output wire [31:0]  cmd_src,cmd_dst,cmd_bytes,cmd_flags,
 input  logic        rsp_valid,
 output wire         rsp_ready,
 input  logic [31:0] rsp_status,
 output wire         done_valid,
 input  logic        done_ready,
 output logic [31:0] done_status,done_rows
);
 typedef enum logic [2:0] {IDLE,CHECK,ISSUE,WAIT_RSP,DONE} state_t;
 state_t state;
 logic write_q;
 logic [31:0] ddr_q,local_q,row_bytes_q,rows_q,ddr_stride_q,local_stride_q;
 logic [31:0] check_ddr,check_local,checked_rows;
 wire [32:0] check_ddr_end={1'b0,check_ddr}+{1'b0,row_bytes_q};
 wire [32:0] check_local_end={1'b0,check_local}+{1'b0,row_bytes_q};
 wire [32:0] next_ddr={1'b0,check_ddr}+{1'b0,ddr_stride_q};
 wire [32:0] next_local={1'b0,check_local}+{1'b0,local_stride_q};
 wire invalid=start_rows==0 || start_row_bytes==0 ||
              start_rows>MAX_ROWS ||
              start_ddr_stride<start_row_bytes || start_local_stride<start_row_bytes;
 wire unaligned=start_ddr[2:0]!=0 || start_ddr_stride[2:0]!=0;
 assign start_ready=rst_n && enable && state==IDLE;
 assign cmd_valid=state==ISSUE;
 assign cmd_src=write_q?local_q:ddr_q;
 assign cmd_dst=write_q?ddr_q:local_q;
 assign cmd_bytes=row_bytes_q;
 assign cmd_flags={31'b0,write_q};
 assign rsp_ready=state==WAIT_RSP;
 assign done_valid=state==DONE;
 always_ff @(posedge clk) begin
  if(!rst_n) begin
   state<=IDLE;write_q<=0;ddr_q<=0;local_q<=0;
   row_bytes_q<=0;rows_q<=0;ddr_stride_q<=0;local_stride_q<=0;
   check_ddr<=0;check_local<=0;checked_rows<=0;
   done_status<=0;done_rows<=0;
  end else case(state)
   IDLE: if(start_valid && start_ready) begin
    done_rows<=0;done_status<=0;
    if(invalid) begin done_status<=1;state<=DONE;end
    else if(unaligned) begin done_status<=4;state<=DONE;end
    else begin
     write_q<=start_write;ddr_q<=start_ddr;local_q<=start_local;
     check_ddr<=start_ddr;check_local<=start_local;checked_rows<=0;
     row_bytes_q<=start_row_bytes;rows_q<=start_rows;
     ddr_stride_q<=start_ddr_stride;local_stride_q<=start_local_stride;
     state<=CHECK;
    end
   end
   CHECK: begin
    if(check_ddr_end>33'h100000000 || check_local_end>33'h100000000 ||
       check_ddr_end>{1'b0,cfg_ddr_bytes} || check_local_end>{1'b0,cfg_local_bytes})
     begin done_status<=3;state<=DONE;end
    else if(checked_rows+1==rows_q) state<=ISSUE;
    else if(next_ddr[32] || next_local[32])
     begin done_status<=3;state<=DONE;end
    else begin
     check_ddr<=next_ddr[31:0];check_local<=next_local[31:0];
     checked_rows<=checked_rows+1;
    end
   end
   ISSUE: if(cmd_ready) state<=WAIT_RSP;
   WAIT_RSP: if(rsp_valid) begin
    if(rsp_status!=0) begin done_status<=rsp_status;state<=DONE;end
    else begin
     done_rows<=done_rows+1;
     if(done_rows+1==rows_q) state<=DONE;
     else begin ddr_q<=ddr_q+ddr_stride_q;local_q<=local_q+local_stride_q;state<=ISSUE;end
    end
   end
   DONE: if(done_ready) state<=IDLE;
   default: state<=IDLE;
  endcase
 end
endmodule
