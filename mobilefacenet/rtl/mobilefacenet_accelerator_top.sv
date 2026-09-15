`timescale 1ns/1ps
module mobilefacenet_accelerator_top #(
    parameter [31:0] BASE_ADDR=32'h40000000,
    parameter signed [31:0] RELU6_MAX=32'sd96,
    parameter TASK_PREFETCH_DEPTH=4
)(
    input wire clk,rst_n,input wire [31:0] mmio_addr,mmio_wdata,
    input wire mmio_we,mmio_re,output wire [31:0] mmio_rdata,output wire mmio_ready,
    output wire [31:0] mem_addr,mem_wdata,output wire mem_read,mem_write,
    input wire [31:0] mem_rdata,input wire mem_ready
);
    wire start,reset,core_busy,done,error,mem_idle;
    wire exec_start,exec_busy,exec_done,exec_error,queue_active,queue_done,queue_error,fetch_phase;
    wire fetch_valid,fetch_ready,fetch_response,bus_ready,bus_response;
    wire [31:0] fetch_addr,bus_rdata,task_ia,task_oa,task_wa,task_ba,task_fs,task_ch,task_lp;
    wire [31:0] queue_base,queue_completed,queue_fetched,queue_buffered;
    wire [63:0] queue_end;
    wire [3:0] task_op,queue_state;
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
    assign core_busy=exec_busy || queue_active;
    assign done=queue_active ? queue_done : exec_done;
    assign error=queue_active ? queue_error : exec_error;
    assign cr=bus_ready && !fetch_phase;
    assign rv=bus_response && !fetch_phase;
    assign rsp=bus_rdata;
    assign fetch_ready=bus_ready && fetch_phase;
    assign fetch_response=bus_response && fetch_phase;
    // Protect the whole task table, including descriptors not yet prefetched.
    wire queue_output_safe=!queue_active || ({32'd0,coa}+{32'd0,count}<={32'd0,queue_base}) ||
                           ({32'd0,coa}>=queue_end);
    accelerator_regs #(.BASE_ADDR(BASE_ADDR)) regs(clk,rst_n,mmio_addr,mmio_wdata,mmio_we,mmio_re,
        mmio_rdata,mmio_ready,start,reset,op,core_busy || !mem_idle,done,error,ia,oa,wa,ba,fs,ch,lp);
    task_queue_controller #(.PREFETCH_DEPTH(TASK_PREFETCH_DEPTH)) task_queue(
        .clk(clk),.rst_n(rst_n),.soft_reset(reset),.start(start),.op_type(op),
        .input_addr(ia),.output_addr(oa),.weight_addr(wa),.bias_addr(ba),.feature_size(fs),.channels(ch),.layer_param(lp),
        .exec_busy(exec_busy),.exec_done(exec_done),.exec_error(exec_error),.mem_idle(mem_idle),.exec_start(exec_start),
        .task_op(task_op),.task_input(task_ia),.task_output(task_oa),.task_weight(task_wa),.task_bias(task_ba),
        .task_size(task_fs),.task_channels(task_ch),.task_param(task_lp),.active(queue_active),.done(queue_done),.error(queue_error),
        .fetch_phase(fetch_phase),.fetch_valid(fetch_valid),.fetch_ready(fetch_ready),.fetch_addr(fetch_addr),
        .fetch_rsp_valid(fetch_response),.fetch_rsp_data(bus_rdata),.queue_base(queue_base),.queue_end(queue_end),
        .completed(queue_completed),.fetched(queue_fetched),.buffered(queue_buffered),.debug_state(queue_state));
    mobilefacenet_controller controller(clk,rst_n,reset,exec_start,task_ia,task_oa,task_wa,task_ba,task_fs,task_ch,task_lp,task_op,
        cia,coa,cwa,cba,cfs,cch,clp,cop,cfg_valid && queue_output_safe,pad,ow,oh,count,mem_idle,cr,rv,engine_ready,engine_done,engine_error,
        cv,cwrite,cbyte,select_addr,exec_busy,exec_done,exec_error,clear,iw,ww,bw,es,sv,out_we,zero,ax,ay,elem,ic,oc,tap,state);
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
    // Ownership changes only when no transaction or response is outstanding.
    accelerator_mem_if memory_interface(clk,rst_n,reset,fetch_phase ? fetch_valid : cv,bus_ready,
        fetch_phase ? 1'b0 : cwrite,fetch_phase ? 1'b0 : cbyte,fetch_phase ? fetch_addr : command_addr,
        {24'd0,out_value},bus_response,bus_rdata,mem_idle,mem_addr,mem_wdata,mem_read,mem_write,mem_rdata,mem_ready);
endmodule
