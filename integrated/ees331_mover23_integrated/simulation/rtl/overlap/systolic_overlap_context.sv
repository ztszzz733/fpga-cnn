`timescale 1ns/1ps
// Access/execute decoupling around the existing PE array (no extra PEs).
// Two operand tiles, one captured output tile, independent load/store masters.
module systolic_overlap_context #(parameter bit ENABLE_OVERLAP=1)(
    input wire clk,rst_n,clear,start,
    input wire [31:0] ia,oa,wa,ba,fs,ch,lp,input wire [3:0] op,
    input wire queue_active,input wire [31:0] queue_base,input wire [63:0] queue_end,
    output wire busy,done,error,
    output wire ld_valid,input wire ld_ready,output wire [31:0] ld_addr,
    input wire ld_response,input wire [31:0] ld_data,
    output wire st_valid,input wire st_ready,output wire st_byte,
    output wire [31:0] st_addr,st_data,input wire st_response,
    output wire array_running,input wire [3:0] row_capacity,input wire [2047:0] sums,
    output wire array_clear,array_ce,array_load,array_dw,output wire [2047:0] initial_sums,
    output wire [63:0] a_edge,b_edge,dw_weights,dw_valid,
    output wire [7:0] a_valid,b_valid,output wire [511:0] dw_inputs
);
    localparam IDLE=0,CHECK=1,ACTIVE=2,FINISH=3,FAILED=4;
    localparam L_FREE=0,L_BIAS=1,L_BIAS_WAIT=2,L_A=3,L_A_WAIT=4,L_B=5,L_B_WAIT=6,L_PUBLISH=7;
    reg [2:0] state,ls;
    reg [31:0] cia,coa,cwa,cba,cfs,cch,clp,mb,nb,kb;
    reg [3:0] cop,capacity;
    reg [2:0] row,col,ki;
    reg producer,consumer,load_finished,compute_active,compute_finished;
    reg [1:0] full;
    reg [31:0] tile_m[0:1],tile_n[0:1],tile_k[0:1];
    reg [3:0] tile_rows[0:1],tile_cols[0:1],tile_depth[0:1];
    reg tile_last[0:1];
    wire dw=cop==1;
    wire [31:0] input_address,weight_address,bias_address,unused_out,spatial,reduction,count;
    wire padding,geometry;
    wire [31:0] rem_r={16'd0,cch[31:16]}-mb,rem_c=spatial-nb,rem_k=reduction-kb;
    wire [3:0] nr=rem_r<capacity ? rem_r[3:0] : capacity;
    wire [3:0] nc=rem_c<8 ? rem_c[3:0] : 4'd8;
    wire [3:0] nk=rem_k<8 ? rem_k[3:0] : 4'd8;
    conv_window_address loader_address(cia,coa,cwa,cba,cfs,cch,clp,cop,mb,nb,kb,row,col,ki,
        input_address,weight_address,bias_address,unused_out,padding,geometry,spatial,reduction,count);
    wire safe_table=!queue_active || {32'd0,coa}+{32'd0,count}<={32'd0,queue_base} || {32'd0,coa}>=queue_end;
    assign busy=state!=IDLE;assign done=state==FINISH;assign error=state==FAILED;
    assign array_clear=clear || state==CHECK;

    reg [1:0] ws;
    reg [2047:0] output_tile;
    reg [31:0] output_m,output_n;
    reg [3:0] output_rows,output_cols;
    reg [2:0] wr,wc;
    wire load_allowed=ENABLE_OVERLAP || (!compute_active && full==0 && ws==0);
    wire load_step=state==ACTIVE && load_allowed && !clear;
    wire read_ready,read_done;wire [31:0] read_data;
    wire read_request=load_step && (ls==L_BIAS || ls==L_A || (ls==L_B && !padding));
    wire [31:0] read_address=ls==L_BIAS ? bias_address : ls==L_A ? weight_address : input_address;
    systolic_read_cache reads(clk,rst_n,clear || state==CHECK,read_request,read_ready,read_address,
        ls!=L_BIAS,ls!=L_B,read_done,read_data,ld_valid,ld_ready,ld_addr,ld_response,ld_data);

    wire [1:0] tile_busy,tile_done,tile_ce,tile_load,tile_dw;
    wire [4095:0] seeds;
    wire [127:0] ae,be,dww,dwv;
    wire [15:0] av,bv;
    wire [1023:0] dwi;
    wire launch=state==ACTIVE && full[consumer] && !compute_active && !clear &&
        (ENABLE_OVERLAP || ws==0);
    genvar b;
    generate for(b=0;b<2;b=b+1) begin:operand_buffers
        systolic_tile_driver tile(clk,rst_n,clear || state==CHECK,1'b1,launch && consumer==b,
            tile_k[b]!=0,dw,tile_rows[b],tile_cols[b],tile_depth[b],
            producer==b && ls==L_A_WAIT && read_done,
            producer==b && ((ls==L_B_WAIT && read_done) || (load_step && ls==L_B && padding)),
            producer==b && ls==L_BIAS_WAIT && read_done,
            row,col,ki,(ls==L_B && padding) ? 8'd0 : read_data[7:0],read_data,
            tile_busy[b],tile_done[b],tile_ce[b],tile_load[b],tile_dw[b],seeds[b*2048+:2048],
            ae[b*64+:64],be[b*64+:64],dww[b*64+:64],dwv[b*64+:64],av[b*8+:8],bv[b*8+:8],dwi[b*512+:512]);
    end endgenerate
    assign array_running=|tile_busy;
    assign array_ce=compute_active && tile_ce[consumer];
    assign array_load=compute_active && tile_load[consumer];
    assign array_dw=tile_dw[consumer];
    assign initial_sums=seeds[consumer*2048+:2048];
    assign a_edge=ae[consumer*64+:64];assign b_edge=be[consumer*64+:64];
    assign dw_weights=dww[consumer*64+:64];assign dw_valid=dwv[consumer*64+:64];
    assign a_valid=av[consumer*8+:8];assign b_valid=bv[consumer*8+:8];assign dw_inputs=dwi[consumer*512+:512];
    wire retire=compute_active && (compute_finished || tile_done[consumer]) &&
        (!tile_last[consumer] || ws==0);

    wire [31:0] u0,u1,u2,u3,u4,u5;wire u6,u7;
    conv_window_address writer_address(cia,coa,cwa,cba,cfs,cch,clp,cop,output_m,output_n,32'd0,wr,wc,3'd0,
        u0,u1,u2,st_addr,u6,u7,u3,u4,u5);
    wire signed [31:0] raw=$signed(output_tile[({wr,wc}*32)+:32]);
    wire signed [31:0] shifted;wire signed [7:0] quantized;
    quantizer quant(raw,clp[19:12],shifted,quantized);
    assign st_valid=ws==1 && !clear;
    assign st_byte=!clp[23];assign st_data=clp[23] ? raw : {24'd0,quantized};

    task advance_b;
        begin
            if({1'b0,ki}+1<nk) begin ki<=ki+1'b1;ls<=L_B;end
            else begin
                ki<=0;
                if({1'b0,col}+1<nc) begin col<=col+1'b1;ls<=L_B;end
                else begin
                    col<=0;
                    if(dw && {1'b0,row}+1<nr) begin row<=row+1'b1;ls<=L_B;end
                    else begin row<=0;ls<=L_PUBLISH;end
                end
            end
        end
    endtask
    integer i;
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            state<=IDLE;ls<=L_FREE;full<=0;producer<=0;consumer<=0;load_finished<=0;
            compute_active<=0;compute_finished<=0;ws<=0;wr<=0;wc<=0;
            cia<=0;coa<=0;cwa<=0;cba<=0;cfs<=0;cch<=0;clp<=0;cop<=0;capacity<=0;
            mb<=0;nb<=0;kb<=0;row<=0;col<=0;ki<=0;
            output_tile<=0;output_m<=0;output_n<=0;output_rows<=0;output_cols<=0;
            for(i=0;i<2;i=i+1) begin tile_m[i]<=0;tile_n[i]<=0;tile_k[i]<=0;
                tile_rows[i]<=0;tile_cols[i]<=0;tile_depth[i]<=0;tile_last[i]<=0;end
        end else if(clear) begin
            state<=IDLE;ls<=L_FREE;full<=0;producer<=0;consumer<=0;load_finished<=0;
            compute_active<=0;compute_finished<=0;ws<=0;
        end else begin
            case(state)
                IDLE:if(start) begin
                    cia<=ia;coa<=oa;cwa<=wa;cba<=ba;cfs<=fs;cch<=ch;clp<=lp;cop<=op;capacity<=row_capacity;
                    mb<=0;nb<=0;kb<=0;row<=0;col<=0;ki<=0;producer<=0;consumer<=0;full<=0;
                    load_finished<=0;compute_active<=0;compute_finished<=0;ws<=0;ls<=L_FREE;state<=CHECK;
                end
                CHECK:state<=geometry && safe_table && capacity>=1 && capacity<=8 ? ACTIVE : FAILED;
                ACTIVE:begin
                    if(load_step) case(ls)
                        L_FREE:if(!load_finished && !full[producer]) begin
                            tile_m[producer]<=mb;tile_n[producer]<=nb;tile_k[producer]<=kb;
                            tile_rows[producer]<=nr;tile_cols[producer]<=nc;tile_depth[producer]<=nk;
                            tile_last[producer]<=kb+{28'd0,nk}>=reduction;
                            row<=0;col<=0;ki<=0;ls<=kb==0 ? L_BIAS : L_A;
                        end
                        L_BIAS:if(read_ready) ls<=L_BIAS_WAIT;
                        L_BIAS_WAIT:if(read_done) begin
                            if({1'b0,row}+1<nr) begin row<=row+1'b1;ls<=L_BIAS;end
                            else begin row<=0;ls<=L_A;end
                        end
                        L_A:if(read_ready) ls<=L_A_WAIT;
                        L_A_WAIT:if(read_done) begin
                            if({1'b0,ki}+1<nk) begin ki<=ki+1'b1;ls<=L_A;end
                            else begin ki<=0;
                                if({1'b0,row}+1<nr) begin row<=row+1'b1;ls<=L_A;end
                                else begin row<=0;col<=0;ls<=L_B;end
                            end
                        end
                        L_B:if(padding) advance_b();else if(read_ready) ls<=L_B_WAIT;
                        L_B_WAIT:if(read_done) advance_b();
                        L_PUBLISH:begin
                            full[producer]<=1;producer<=!producer;ls<=L_FREE;
                            if(kb+{28'd0,nk}<reduction) kb<=kb+{28'd0,nk};
                            else begin kb<=0;
                                if(nb+{28'd0,nc}<spatial) nb<=nb+{28'd0,nc};
                                else if(mb+{28'd0,nr}<{16'd0,cch[31:16]}) begin nb<=0;mb<=mb+{28'd0,nr};end
                                else load_finished<=1;
                            end
                        end
                        default:ls<=L_FREE;
                    endcase
                    if(launch) begin compute_active<=1;compute_finished<=0;end
                    if(compute_active && tile_done[consumer]) compute_finished<=1;
                    if(retire) begin
                        full[consumer]<=0;consumer<=!consumer;compute_active<=0;compute_finished<=0;
                        if(tile_last[consumer]) begin
                            output_tile<=sums;output_m<=tile_m[consumer];output_n<=tile_n[consumer];
                            output_rows<=tile_rows[consumer];output_cols<=tile_cols[consumer];wr<=0;wc<=0;ws<=1;
                        end
                    end
                    if(ws==1 && st_ready) ws<=2;
                    if(ws==2 && st_response) begin
                        if({1'b0,wc}+1<output_cols) begin wc<=wc+1'b1;ws<=1;end
                        else if({1'b0,wr}+1<output_rows) begin wc<=0;wr<=wr+1'b1;ws<=1;end
                        else ws<=0;
                    end
                    if(load_finished && full==0 && !compute_active && ws==0) state<=FINISH;
                end
                FINISH:state<=IDLE;
                FAILED:state<=IDLE;
                default:state<=FAILED;
            endcase
        end
    end
`ifndef SYNTHESIS
    always @(posedge clk) if(rst_n && !clear && state==ACTIVE) begin
        assert (!(load_step && ls!=L_FREE && full[producer])) else $fatal(1,"operand tile overwritten");
        assert (!(retire && tile_last[consumer] && ws!=0)) else $fatal(1,"output tile overwritten");
        assert (!compute_active || full[consumer]) else $fatal(1,"compute without a full tile");
    end
`endif
endmodule
