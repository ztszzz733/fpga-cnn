`timescale 1ns/1ps
// A task is tiled over OC, flattened spatial positions, then reduction chunks of 8.
// Each buffer entry is loaded before RUN. RAM stalls cannot advance the array.
// Unsupported opcodes and activation flags fail in CHECK before RAM access.
module systolic_conv_context(
    input wire clk,rst_n,clear,start,
    input wire [31:0] ia,oa,wa,ba,fs,ch,lp,input wire [3:0] op,
    input wire queue_active,input wire [31:0] queue_base,input wire [63:0] queue_end,
    output wire busy,done,error,
    output wire cmd_valid,input wire cmd_ready,output wire cmd_write,cmd_byte,
    output wire [31:0] cmd_addr,cmd_wdata,input wire rsp_valid,input wire [31:0] rsp_data,
    output wire array_running,
    input wire [3:0] row_capacity,input wire [2047:0] sums,
    output wire array_clear,array_ce,array_load,array_dw,output wire [2047:0] initial_sums,
    output wire [63:0] a_edge,b_edge,dw_weights,dw_valid,
    output wire [7:0] a_valid,b_valid,output wire [511:0] dw_inputs
);
    localparam IDLE=0,CHECK=1,BIAS_REQ=2,BIAS_WAIT=3,A_REQ=4,A_WAIT=5,B_REQ=6,B_WAIT=7,
        RUN_START=8,RUN_WAIT=9,POST=10,WRITE_REQ=11,WRITE_WAIT=12,DONE=13,ERROR=14;
    reg [3:0] state;
    reg [31:0] cia,coa,cwa,cba,cfs,cch,clp,mb,nb,kb;
    reg [3:0] capacity;reg [3:0] cop;reg [2:0] row,col,kidx;
    wire [31:0] input_address,weight_address,bias_address,output_address,spatial,reduction,count;
    wire padding,valid;
    wire dw=cop==1;
    wire [31:0] remaining_rows={16'd0,cch[31:16]}-mb,remaining_cols=spatial-nb,remaining_k=reduction-kb;
    wire [3:0] nr=remaining_rows<capacity ? remaining_rows[3:0] : capacity;
    wire [3:0] nc=remaining_cols<8 ? remaining_cols[3:0] : 4'd8;
    wire [3:0] nk=remaining_k<8 ? remaining_k[3:0] : 4'd8;
    assign busy=state!=IDLE;assign done=state==DONE;assign error=state==ERROR;
    wire safe_table=!queue_active || {32'd0,coa}+{32'd0,count}<={32'd0,queue_base} || {32'd0,coa}>=queue_end;
    conv_window_address address_map(cia,coa,cwa,cba,cfs,cch,clp,cop,mb,nb,kb,row,col,kidx,
        input_address,weight_address,bias_address,output_address,padding,valid,spatial,reduction,count);
    wire read_ready,read_done,cache_valid,cache_ready;wire [31:0] read_data,cache_addr;
    wire read_request=state==BIAS_REQ || state==A_REQ || (state==B_REQ && !padding);
    wire [31:0] read_address=state==BIAS_REQ ? bias_address : state==A_REQ ? weight_address : input_address;
    systolic_read_cache reads(clk,rst_n,clear || state==CHECK,read_request,read_ready,read_address,
        state!=BIAS_REQ,state!=B_REQ,read_done,read_data,cache_valid,cache_ready,cache_addr,
        rsp_valid && state!=WRITE_WAIT,rsp_data);
    wire tile_busy,tile_done;
    assign array_clear=clear || state==CHECK;
    assign array_running=tile_busy;
    wire a_we=state==A_WAIT && read_done;
    wire b_we=(state==B_WAIT && read_done) || (state==B_REQ && padding);
    wire bias_we=state==BIAS_WAIT && read_done;
    systolic_tile_driver tile(clk,rst_n,clear || state==CHECK,1'b1,state==RUN_START,kb!=0,dw,nr,nc,nk,
        a_we,b_we,bias_we,row,col,kidx,(state==B_REQ && padding) ? 8'd0 : read_data[7:0],
        read_data,tile_busy,tile_done,array_ce,array_load,array_dw,initial_sums,
        a_edge,b_edge,dw_weights,dw_valid,a_valid,b_valid,dw_inputs);
    wire signed [31:0] raw=$signed(sums[({row,col}*32)+:32]);
    wire signed [31:0] shifted;reg signed [31:0] raw_out;
    wire signed [7:0] quantized,out_value;
    // Output format conversion only: arithmetic shift and signed INT8 clamp.
    quantizer requant(raw,clp[19:12],shifted,quantized);
    output_buffer output_store(clk,rst_n,clear || state==CHECK,state==POST,quantized,out_value);
    assign cmd_valid=!clear && (state==WRITE_REQ || cache_valid);
    assign cmd_write=state==WRITE_REQ;assign cmd_byte=state==WRITE_REQ && !clp[23];
    assign cmd_addr=state==WRITE_REQ ? output_address : cache_addr;
    assign cmd_wdata=clp[23] ? raw_out : {24'd0,out_value};assign cache_ready=cmd_ready && state!=WRITE_REQ;
    // Advance window loading over k, then column, then independent DW channel.
    task advance_b;
        begin
            if({1'b0,kidx}+1<nk) begin kidx<=kidx+1'b1;state<=B_REQ;end
            else begin
                kidx<=0;
                if({1'b0,col}+1<nc) begin col<=col+1'b1;state<=B_REQ;end
                else begin
                    col<=0;
                    if(dw && {1'b0,row}+1<nr) begin row<=row+1'b1;state<=B_REQ;end
                    else begin row<=0;state<=RUN_START;end
                end
            end
        end
    endtask
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin raw_out<=0;state<=IDLE;capacity<=0;cia<=0;coa<=0;cwa<=0;cba<=0;cfs<=0;cch<=0;clp<=0;cop<=0;mb<=0;nb<=0;kb<=0;row<=0;col<=0;kidx<=0;end
        else if(clear) begin state<=IDLE;row<=0;col<=0;kidx<=0;end
        else case(state)
            IDLE:if(start) begin
                capacity<=row_capacity;cia<=ia;coa<=oa;cwa<=wa;cba<=ba;cfs<=fs;cch<=ch;clp<=lp;cop<=op;
                mb<=0;nb<=0;kb<=0;row<=0;col<=0;kidx<=0;state<=CHECK;
            end
            CHECK:state<=valid && safe_table && capacity>=1 && capacity<=8 ? BIAS_REQ : ERROR;
            BIAS_REQ:if(read_ready) state<=BIAS_WAIT;
            BIAS_WAIT:if(read_done) begin
                if({1'b0,row}+1<nr) begin row<=row+1'b1;state<=BIAS_REQ;end
                else begin row<=0;state<=A_REQ;end
            end
            A_REQ:if(read_ready) state<=A_WAIT;
            A_WAIT:if(read_done) begin
                if({1'b0,kidx}+1<nk) begin kidx<=kidx+1'b1;state<=A_REQ;end
                else begin
                    kidx<=0;
                    if({1'b0,row}+1<nr) begin row<=row+1'b1;state<=A_REQ;end
                    else begin row<=0;col<=0;state<=B_REQ;end
                end
            end
            B_REQ:if(padding) advance_b();else if(read_ready) state<=B_WAIT;
            B_WAIT:if(read_done) advance_b();
            RUN_START:state<=RUN_WAIT;
            RUN_WAIT:if(tile_done) begin
                if(kb+nk<reduction) begin kb<=kb+nk;row<=0;col<=0;kidx<=0;state<=A_REQ;end
                else begin row<=0;col<=0;state<=POST;end
            end
            POST:begin raw_out<=raw;state<=WRITE_REQ;end
            WRITE_REQ:if(cmd_ready) state<=WRITE_WAIT;
            WRITE_WAIT:if(rsp_valid) begin
                if({1'b0,col}+1<nc) begin col<=col+1'b1;state<=POST;end
                else begin
                    col<=0;
                    if({1'b0,row}+1<nr) begin row<=row+1'b1;state<=POST;end
                    else begin
                        row<=0;kb<=0;kidx<=0;
                        if(nb+nc<spatial) begin nb<=nb+nc;state<=BIAS_REQ;end
                        else if(mb+nr<{16'd0,cch[31:16]}) begin mb<=mb+nr;nb<=0;state<=BIAS_REQ;end
                        else state<=DONE;
                    end
                end
            end
            DONE:state<=IDLE;
            ERROR:state<=IDLE;
            default:state<=ERROR;
        endcase
    end
endmodule
