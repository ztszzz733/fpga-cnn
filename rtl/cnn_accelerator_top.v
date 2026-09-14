`timescale 1ns/1ps
module cnn_accelerator_top #(parameter [31:0] BASE_ADDR=32'h4000_0000)(
    input wire clk, rst_n,
    input wire [31:0] mmio_addr, mmio_wdata,
    input wire mmio_we, mmio_re,
    output wire [31:0] mmio_rdata, output wire mmio_ready,
    output wire [31:0] mem_addr, mem_wdata,
    output wire mem_read, mem_write,
    input wire [31:0] mem_rdata, input wire mem_ready
);
    wire start,soft_reset,core_busy,done,error,mem_idle;
    wire [31:0] ia,oa,wa,ba,sz,ch,cp;
    wire [31:0] cfg_ia,cfg_oa,cfg_wa,cfg_ba,cfg_sz,cfg_ch,cfg_cp;
    wire [31:0] input_address,output_address,weight_address,bias_address;
    wire [31:0] conv_width,conv_height,output_width,output_height,x,y;
    wire [15:0] ic,oc;
    wire [3:0] tap; wire [1:0] pool_sample,address_select;
    wire config_valid,input_is_padding;
    wire cmd_valid,cmd_ready,cmd_write,cmd_byte,rsp_valid;
    wire [31:0] rsp_rdata; reg [31:0] cmd_addr;
    wire clear,input_we,weight_we,bias_we,acc_load,mac_enable,input_zero;
    wire pool_first,pool_valid,output_we;
    wire signed [7:0] input_value,weight_value,quantized,output_value;
    wire signed [31:0] bias_value,product,acc_value,relu_value,pool_value;
    wire [4:0] controller_state;

    accelerator_regs #(.BASE_ADDR(BASE_ADDR)) regs(
        .clk(clk),.rst_n(rst_n),.mmio_addr(mmio_addr),.mmio_wdata(mmio_wdata),
        .mmio_we(mmio_we),.mmio_re(mmio_re),.mmio_rdata(mmio_rdata),.mmio_ready(mmio_ready),
        .accelerator_start(start),.accelerator_reset(soft_reset),
        .accelerator_busy(core_busy || !mem_idle),.accelerator_done(done),.accelerator_error(error),
        .input_addr(ia),.output_addr(oa),.weight_addr(wa),.bias_addr(ba),
        .image_size(sz),.channels(ch),.cnn_param(cp));
    cnn_controller controller(
        .clk(clk),.rst_n(rst_n),.soft_reset(soft_reset),.start(start),
        .input_addr(ia),.output_addr(oa),.weight_addr(wa),.bias_addr(ba),
        .image_size(sz),.channels(ch),.cnn_param(cp),
        .cfg_input_addr(cfg_ia),.cfg_output_addr(cfg_oa),.cfg_weight_addr(cfg_wa),
        .cfg_bias_addr(cfg_ba),.cfg_image_size(cfg_sz),.cfg_channels(cfg_ch),.cfg_cnn_param(cfg_cp),
        .config_valid(config_valid),.input_is_padding(input_is_padding),
        .output_width(output_width),.output_height(output_height),.mem_idle(mem_idle),
        .cmd_ready(cmd_ready),.rsp_valid(rsp_valid),.cmd_valid(cmd_valid),
        .cmd_write(cmd_write),.cmd_byte(cmd_byte),.address_select(address_select),
        .busy(core_busy),.done(done),.error(error),.datapath_clear(clear),
        .input_we(input_we),.weight_we(weight_we),.bias_we(bias_we),
        .accumulator_load(acc_load),.mac_enable(mac_enable),.input_zero(input_zero),
        .pool_first(pool_first),.pool_valid(pool_valid),.output_we(output_we),
        .output_x(x),.output_y(y),.input_channel(ic),.output_channel(oc),
        .tap(tap),.pool_sample(pool_sample),.debug_state(controller_state));
    address_generator addresses(
        .input_base(cfg_ia),.output_base(cfg_oa),.weight_base(cfg_wa),.bias_base(cfg_ba),
        .image_size(cfg_sz),.channels(cfg_ch),.cnn_param(cfg_cp),
        .output_x(x),.output_y(y),.input_channel(ic),.output_channel(oc),
        .tap(tap),.pool_sample(pool_sample),.input_address(input_address),
        .output_address(output_address),.weight_address(weight_address),.bias_address(bias_address),
        .input_is_padding(input_is_padding),.config_valid(config_valid),
        .conv_width(conv_width),.conv_height(conv_height),.output_width(output_width),.output_height(output_height));
    input_buffer inputs(clk,input_we,tap,tap,input_zero ? 8'sd0 : rsp_rdata[7:0],input_value);
    weight_buffer weights(clk,weight_we,tap,tap,rsp_rdata[7:0],weight_value);
    bias_buffer biases(clk,rst_n,clear,bias_we,rsp_rdata,bias_value);
    mac_unit mac(input_value,weight_value,product);
    accumulator acc(clk,rst_n,clear,acc_load,mac_enable,bias_value,product,acc_value);
    relu_unit relu(acc_value,cfg_cp[20],relu_value);
    maxpool_unit pool(clk,rst_n,clear,pool_valid,pool_first,relu_value,pool_value);
    quantizer quant(pool_value,cfg_cp[19:12],cfg_cp[20],quantized);
    output_buffer outputs(clk,rst_n,clear,output_we,quantized,output_value);
    always @* begin
        case(address_select)
            0: cmd_addr=input_address;
            1: cmd_addr=weight_address;
            2: cmd_addr=bias_address;
            3: cmd_addr=output_address;
            default: cmd_addr=0;
        endcase
    end
    accelerator_mem_if memory_interface(
        .clk(clk),.rst_n(rst_n),.cancel(soft_reset),
        .cmd_valid(cmd_valid),.cmd_ready(cmd_ready),.cmd_write(cmd_write),.cmd_byte(cmd_byte),
        .cmd_addr(cmd_addr),.cmd_wdata({24'd0,output_value}),.rsp_valid(rsp_valid),.rsp_rdata(rsp_rdata),
        .idle(mem_idle),.mem_addr(mem_addr),.mem_wdata(mem_wdata),.mem_read(mem_read),
        .mem_write(mem_write),.mem_rdata(mem_rdata),.mem_ready(mem_ready));
endmodule
