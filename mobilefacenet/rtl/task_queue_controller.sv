`timescale 1ns/1ps
// Queue-only entry: CONTROL OP_TYPE must be 15. INPUT_ADDR=base, FEATURE_SIZE=count.
// A batch of up to PREFETCH_DEPTH descriptors is fetched before execution.
// One operator executes at a time; no speculative data writes or reordered tasks.
module task_queue_controller #(parameter PREFETCH_DEPTH=4)(
    input wire clk,rst_n,soft_reset,start,input wire [3:0] op_type,
    input wire [31:0] input_addr,feature_size,
    input wire exec_busy,exec_done,exec_error,mem_idle,
    output wire exec_start,output wire [3:0] task_op,
    output wire [31:0] task_input,task_output,task_weight,task_bias,task_size,task_channels,task_param,
    output wire active,done,error,fetch_phase,
    output wire fetch_valid,input wire fetch_ready,output wire [31:0] fetch_addr,
    input wire fetch_rsp_valid,input wire [31:0] fetch_rsp_data,
    output reg [31:0] queue_base,output wire [63:0] queue_end,
    output reg [31:0] completed,fetched,output wire [31:0] buffered,
    output wire [3:0] debug_state
);
    localparam IDLE=0,VALIDATE=1,FILL=2,DISPATCH=3,RUN=4,RELEASE=5,DONE=6,ERROR=7;
    reg [3:0] state;
    reg [31:0] total;
    reg failed;
    wire [255:0] reader_data,head_data;
    wire reader_idle,reader_valid,reader_ready,head_valid,head_ready;
    wire accept_start=state==IDLE && start && mem_idle && !exec_busy && !soft_reset;
    wire begin_queue=accept_start && op_type==15;
    wire flush=soft_reset || begin_queue;
    assign active=state!=IDLE;
    assign done=state==DONE;
    assign error=state==ERROR;
    assign fetch_phase=state==FILL;
    assign debug_state=state;
    assign queue_end={32'd0,queue_base}+({32'd0,total}<<5);
    wire legal_queue=queue_base[4:0]==0 && total!=0 && queue_end<=64'h100000000;
    // Word 0: version=1 in [15:8], opcode in [7:0], reserved [31:16]=0.
    wire legal_header=head_data[31:8]==24'd1 && head_data[7:0]<=1;
    assign head_ready=state==DISPATCH && legal_header && !exec_busy && mem_idle && !soft_reset;
    // The FIFO is the sole source of execution commands and layer parameters.
    assign exec_start=head_valid && head_ready;
    assign task_op=head_data[3:0];
    assign task_input=head_data[63:32];
    assign task_output=head_data[95:64];
    assign task_weight=head_data[127:96];
    assign task_bias=head_data[159:128];
    assign task_size=head_data[191:160];
    assign task_channels=head_data[223:192];
    assign task_param=head_data[255:224];
    task_descriptor_reader reader(
        .clk(clk),.rst_n(rst_n),.clear(flush),
        .start(fetch_phase && reader_idle && reader_ready && fetched<total),
        .base_address(queue_base+(fetched<<5)),.idle(reader_idle),
        .cmd_valid(fetch_valid),.cmd_ready(fetch_ready),.cmd_addr(fetch_addr),
        .rsp_valid(fetch_rsp_valid),.rsp_data(fetch_rsp_data),
        .descriptor_valid(reader_valid),.descriptor_ready(reader_ready),.descriptor(reader_data));
    task_descriptor_fifo #(.DEPTH(PREFETCH_DEPTH)) fifo(
        .clk(clk),.rst_n(rst_n),.clear(flush),.in_valid(reader_valid),.in_ready(reader_ready),.in_data(reader_data),
        .out_valid(head_valid),.out_ready(head_ready),.out_data(head_data),.level(buffered));
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin state<=IDLE;queue_base<=0;total<=0;completed<=0;fetched<=0;failed<=0;end
        else if(soft_reset) begin state<=IDLE;completed<=0;fetched<=0;failed<=0;end
        else case(state)
            IDLE:if(accept_start) begin
                completed<=0;fetched<=0;failed<=0;
                if(begin_queue) begin
                    queue_base<=input_addr;total<=feature_size;state<=VALIDATE;
                end else state<=ERROR; // Reject former direct mode without RAM or array activity.
            end
            VALIDATE:state<=legal_queue ? FILL : ERROR;
            FILL:if(reader_valid && reader_ready) begin
                fetched<=fetched+1;
                if(buffered==PREFETCH_DEPTH-1 || fetched+1==total) state<=DISPATCH;
            end
            DISPATCH:if(head_valid) begin
                if(!legal_header) state<=ERROR;
                else if(head_ready) state<=RUN;
            end
            RUN:if(exec_error || exec_done) begin failed<=exec_error;state<=RELEASE;end
            RELEASE:if(!exec_busy && mem_idle) begin
                if(failed) state<=ERROR;
                else begin
                    completed<=completed+1;
                    if(completed+1==total) state<=DONE;
                    else state<=head_valid ? DISPATCH : FILL;
                end
            end
            DONE:state<=IDLE;
            ERROR:state<=IDLE;
            default:state<=ERROR;
        endcase
    end
endmodule
