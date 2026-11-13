`timescale 1ns/1ps
// Queue-only, out-of-order issue, two shared-array contexts + six scalar engines.
module mobilefacenet_overlap_top #(
    parameter [31:0] BASE_ADDR=32'h40000000,
    parameter TASK_PREFETCH_DEPTH=4, ENABLE_OVERLAP=1
)(
    input wire clk,rst_n,input wire [31:0] mmio_addr,mmio_wdata,
    input wire mmio_we,mmio_re,output wire [31:0] mmio_rdata,output wire mmio_ready,
    output wire [10:0] cnn_valid,cnn_write,cnn_byte,
    output wire [351:0] cnn_addr,cnn_wdata,
    input wire [10:0] cnn_ready,cnn_response,input wire [351:0] cnn_rdata,
    output wire cnn_cancel,
    output wire status_busy,status_done,status_error
);
    wire start,reset,core_busy,done,error,mem_idle,arb_idle;
    wire [31:0] ia,oa,wa,ba,fs,ch,lp;wire [3:0] op;
    wire queue_active,queue_done,queue_error,exec_start,exec_done,exec_error;
    wire [7:0] unit_start,unit_busy,unit_done,unit_error,unit_allocated;
    wire [1:0] context_start=unit_start[1:0],context_busy=unit_busy[1:0];
    wire [1:0] context_done=unit_done[1:0],context_error=unit_error[1:0],allocated=unit_allocated[1:0];
    wire [255:0] unit_task_ids;wire [31:0] dispatch_id;
    wire [2:0] row_base0,row_base1;wire [3:0] row_count0,row_count1,dispatch_rows;
    wire [31:0] queue_base,queue_completed,queue_fetched,queue_buffered,queue_dispatched,task_id0,task_id1;
    wire [63:0] queue_end;wire [3:0] queue_state;wire hazard_wait,resource_wait;
    wire [255:0] descriptor;
    wire [3:0] task_op=descriptor[3:0];
    wire [31:0] task_ia=descriptor[63:32],task_oa=descriptor[95:64],task_wa=descriptor[127:96],
        task_ba=descriptor[159:128],task_fs=descriptor[191:160],task_ch=descriptor[223:192],task_lp=descriptor[255:224];
    wire fetch_valid,fetch_ready,fetch_response;wire [31:0] fetch_addr;
    wire [10:0] client_valid,client_ready,client_write,client_byte,client_response;
    wire [351:0] client_addr,client_wdata;
    assign cnn_valid=reset ? 11'b0 : client_valid;
    assign cnn_write=client_write;assign cnn_byte=client_byte;
    assign cnn_addr=client_addr;assign cnn_wdata=client_wdata;
    assign client_ready=cnn_ready & {11{!reset}};
    assign client_response=cnn_response & {11{!reset}};
    assign cnn_cancel=reset;
    // Break the scheduler start -> reader flush -> valid -> idle loop. A start
    // requires a full quiet cycle. Responses account for all accepted accesses.
    reg memory_quiet;
    always @(posedge clk or negedge rst_n)
        if(!rst_n) memory_quiet<=1;
        else memory_quiet<=!(|cnn_valid) && !(|cnn_response);
    assign mem_idle=memory_quiet && !(|cnn_response);assign arb_idle=mem_idle;
    wire [1:0] ctx_clear,ctx_ce,ctx_load,ctx_dw,ctx_running;
    wire [4095:0] ctx_seeds;wire [127:0] ctx_ae,ctx_be,ctx_dww,ctx_dwv;
    wire [15:0] ctx_av,ctx_bv;wire [1023:0] ctx_dwi;
    wire [2047:0] sums0,sums1;wire [63:0] pe_fire_map;wire [7:0] pe_mask0,pe_mask1;
    wire array_running=|ctx_running;
    wire sx_busy=|context_busy;
    wire fetch_phase=client_valid[0];
    assign core_busy=queue_active || (|unit_busy) || !arb_idle;
    assign done=queue_done;assign error=queue_error;
    assign status_busy=core_busy;assign status_done=done;assign status_error=error;
    assign exec_done=|unit_done;assign exec_error=|unit_error;
    accelerator_regs #(.BASE_ADDR(BASE_ADDR)) regs(clk,rst_n,mmio_addr,mmio_wdata,mmio_we,mmio_re,
        mmio_rdata,mmio_ready,start,reset,op,core_busy || !mem_idle,done,error,ia,oa,wa,ba,fs,ch,lp);
    streaming_task_scheduler #(.PREFETCH_DEPTH(TASK_PREFETCH_DEPTH)) task_queue(
        clk,rst_n,reset,start,op,ia,fs,unit_busy,unit_done,unit_error,mem_idle && arb_idle,
        unit_start,exec_start,descriptor,queue_active,queue_done,queue_error,
        fetch_valid,fetch_ready,fetch_addr,fetch_response,cnn_rdata[0+:32],queue_base,queue_end,
        queue_completed,queue_fetched,queue_dispatched,queue_buffered,queue_state,unit_allocated,
        row_base0,row_base1,row_count0,row_count1,dispatch_rows,task_id0,task_id1,hazard_wait,resource_wait,dispatch_id,unit_task_ids);
    assign client_valid[0]=fetch_valid;assign client_write[0]=0;assign client_byte[0]=0;
    assign client_addr[0+:32]=fetch_addr;assign client_wdata[0+:32]=0;
    assign fetch_ready=client_ready[0];assign fetch_response=client_response[0];
    assign client_write[1]=0;assign client_byte[1]=0;assign client_wdata[32+:32]=0;
    assign client_write[2]=1;
    generate if(1) begin:systolic_path
        systolic_overlap_context #(.ENABLE_OVERLAP(ENABLE_OVERLAP)) engine(
            .clk(clk),.rst_n(rst_n),.clear(reset),.start(context_start[0]),
            .ia(task_ia),.oa(task_oa),.wa(task_wa),.ba(task_ba),.fs(task_fs),.ch(task_ch),.lp(task_lp),.op(task_op==9 ? 4'd0 : task_op),
            .queue_active(queue_active),.queue_base(queue_base),.queue_end(queue_end),
            .busy(unit_busy[0]),.done(unit_done[0]),.error(unit_error[0]),
            .ld_valid(client_valid[1]),.ld_ready(client_ready[1]),.ld_addr(client_addr[32+:32]),
            .ld_response(client_response[1]),.ld_data(cnn_rdata[32+:32]),
            .st_valid(client_valid[2]),.st_ready(client_ready[2]),.st_byte(client_byte[2]),
            .st_addr(client_addr[64+:32]),.st_data(client_wdata[64+:32]),.st_response(client_response[2]),.array_running(ctx_running[0]),
            .row_capacity(dispatch_rows),.sums(sums0),.array_clear(ctx_clear[0]),.array_ce(ctx_ce[0]),
            .array_load(ctx_load[0]),.array_dw(ctx_dw[0]),.initial_sums(ctx_seeds[0+:2048]),
            .a_edge(ctx_ae[0+:64]),.b_edge(ctx_be[0+:64]),.dw_weights(ctx_dww[0+:64]),
            .dw_valid(ctx_dwv[0+:64]),.a_valid(ctx_av[0+:8]),.b_valid(ctx_bv[0+:8]),
            .dw_inputs(ctx_dwi[0+:512]));
    end endgenerate
    assign client_write[3]=0;assign client_byte[3]=0;assign client_wdata[96+:32]=0;
    assign client_write[4]=1;
    generate if(1) begin:systolic_path_1
        systolic_overlap_context #(.ENABLE_OVERLAP(ENABLE_OVERLAP)) engine(
            .clk(clk),.rst_n(rst_n),.clear(reset),.start(context_start[1]),
            .ia(task_ia),.oa(task_oa),.wa(task_wa),.ba(task_ba),.fs(task_fs),.ch(task_ch),.lp(task_lp),.op(task_op==9 ? 4'd0 : task_op),
            .queue_active(queue_active),.queue_base(queue_base),.queue_end(queue_end),
            .busy(unit_busy[1]),.done(unit_done[1]),.error(unit_error[1]),
            .ld_valid(client_valid[3]),.ld_ready(client_ready[3]),.ld_addr(client_addr[96+:32]),
            .ld_response(client_response[3]),.ld_data(cnn_rdata[96+:32]),
            .st_valid(client_valid[4]),.st_ready(client_ready[4]),.st_byte(client_byte[4]),
            .st_addr(client_addr[128+:32]),.st_data(client_wdata[128+:32]),.st_response(client_response[4]),.array_running(ctx_running[1]),
            .row_capacity(dispatch_rows),.sums(sums1),.array_clear(ctx_clear[1]),.array_ce(ctx_ce[1]),
            .array_load(ctx_load[1]),.array_dw(ctx_dw[1]),.initial_sums(ctx_seeds[2048+:2048]),
            .a_edge(ctx_ae[64+:64]),.b_edge(ctx_be[64+:64]),.dw_weights(ctx_dww[64+:64]),
            .dw_valid(ctx_dwv[64+:64]),.a_valid(ctx_av[8+:8]),.b_valid(ctx_bv[8+:8]),
            .dw_inputs(ctx_dwi[512+:512]));
    end endgenerate
    systolic_shared_array8 array(clk,rst_n,reset,allocated,row_base0,row_base1,row_count0,row_count1,
        ctx_clear,ctx_ce,ctx_load,ctx_dw,ctx_seeds,ctx_ae,ctx_be,ctx_dww,ctx_dwv,ctx_av,ctx_bv,ctx_dwi,
        sums0,sums1,pe_fire_map,pe_mask0,pe_mask1);
    genvar u;
    generate for(u=2;u<8;u=u+1) begin:operators
        localparam CODE=u==2 ? 2 : u==3 ? 3 : u==4 ? 6 : u==5 ? 7 : u==6 ? 8 : 10;
        tensor_operator_engine #(.OPCODE(CODE)) engine(
            clk,rst_n,reset,unit_start[u],descriptor,unit_busy[u],unit_done[u],unit_error[u],
            client_valid[u+3],client_ready[u+3],client_write[u+3],client_byte[u+3],
            client_addr[(u+3)*32+:32],client_wdata[(u+3)*32+:32],client_response[u+3],cnn_rdata[(u+3)*32+:32]);
    end endgenerate
endmodule
