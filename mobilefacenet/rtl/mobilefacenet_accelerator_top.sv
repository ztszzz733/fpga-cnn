`timescale 1ns/1ps
module mobilefacenet_accelerator_top #(
    parameter [31:0] BASE_ADDR=32'h40000000,
    parameter signed [31:0] RELU6_MAX=32'sd96
)(
    input wire clk,rst_n,input wire [31:0] mmio_addr,mmio_wdata,
    input wire mmio_we,mmio_re,output wire [31:0] mmio_rdata,output wire mmio_ready,
    output wire [31:0] mem_addr,mem_wdata,output wire mem_read,mem_write,
    input wire [31:0] mem_rdata,input wire mem_ready
);
    wire start,reset,core_busy,done,error,mem_idle;
    wire [3:0] op,cop;
    wire [31:0] ia,oa,wa,ba,fs,ch,lp,cia,coa,cwa,cba,cfs,cch,clp;
    wire [31:0] ax,ay,elem,input_address,weight_address,bias_address,output_address,second_address,ow,oh,count;
    wire [15:0] ic,oc;wire [5:0] tap;wire [2:0] select_addr;wire [4:0] state;
    wire cfg_valid,pad,clear,iw,ww,bw,es,sv,out_we,zero,cv,cr,cwrite,cbyte,rv;
    wire [31:0] rsp;reg [31:0] command_addr;
    wire signed [7:0] av,wv,out_value,quantized,unused_quant;
    wire signed [31:0] bias_value,normal_result,depthwise_result,add_result,shifted,activated,unused_shift;
    reg signed [31:0] raw_result;
    wire nr,nd,ne,nb,dr,dd,de,db;
    wire engine_ready=cop==0 ? nr : dr;
    wire engine_done=cop==0 ? nd : dd;
    wire engine_error=cop==0 ? ne : (cop==1 ? de : 1'b0);
    accelerator_regs #(.BASE_ADDR(BASE_ADDR)) regs(clk,rst_n,mmio_addr,mmio_wdata,mmio_we,mmio_re,
        mmio_rdata,mmio_ready,start,reset,op,core_busy || !mem_idle,done,error,ia,oa,wa,ba,fs,ch,lp);
    mobilefacenet_controller controller(clk,rst_n,reset,start,ia,oa,wa,ba,fs,ch,lp,op,
        cia,coa,cwa,cba,cfs,cch,clp,cop,cfg_valid,pad,ow,oh,count,mem_idle,cr,rv,engine_ready,engine_done,engine_error,
        cv,cwrite,cbyte,select_addr,core_busy,done,error,clear,iw,ww,bw,es,sv,out_we,zero,ax,ay,elem,ic,oc,tap,state);
    address_generator addresses(cia,coa,cwa,cba,cfs,cch,clp,cop,ax,ay,elem,ic,oc,tap,
        input_address,weight_address,bias_address,output_address,second_address,ow,oh,count,pad,cfg_valid);
    input_buffer input_store(clk,iw,tap,tap,zero ? 8'sd0 : rsp[7:0],av);
    weight_buffer weight_store(clk,ww,tap,tap,rsp[7:0],wv);
    bias_buffer bias_store(clk,rst_n,clear,bw,rsp,bias_value);
    conv_engine conv(clk,rst_n,clear,es && cop==0,clp[3:0],cch[15:0],bias_value,
        sv && cop==0,nr,av,wv,nb,nd,ne,normal_result);
    depthwise_conv_engine depthwise(clk,rst_n,clear,es && cop==1,clp[3:0],bias_value,
        sv && cop==1,dr,av,wv,db,dd,de,depthwise_result);
    add_unit residual(av,wv,add_result);
    always @* begin
        case(cop)
            0:raw_result=normal_result;
            1:raw_result=depthwise_result;
            3:raw_result=add_result;
            default:raw_result={{24{av[7]}},av};
        endcase
    end
    quantizer requant(raw_result,clp[19:12],shifted,unused_quant);
    relu6_unit #(.RELU6_MAX(RELU6_MAX)) activation(shifted,clp[20],clp[21] || cop==2,activated);
    quantizer saturate(activated,8'd0,unused_shift,quantized);
    output_buffer output_store(clk,rst_n,clear,out_we,quantized,out_value);
    always @* begin
        case(select_addr)
            0:command_addr=input_address;
            1:command_addr=weight_address;
            2:command_addr=bias_address;
            3:command_addr=output_address;
            4:command_addr=second_address;
            default:command_addr=0;
        endcase
    end
    accelerator_mem_if memory_interface(clk,rst_n,reset,cv,cr,cwrite,cbyte,command_addr,
        {24'd0,out_value},rv,rsp,mem_idle,mem_addr,mem_wdata,mem_read,mem_write,mem_rdata,mem_ready);
endmodule
