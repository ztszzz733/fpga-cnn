`timescale 1ns/1ps
// Control only: all tensor address arithmetic belongs to address_generator.
module cnn_controller(
    input wire clk, rst_n, soft_reset, start,
    input wire [31:0] input_addr, output_addr, weight_addr, bias_addr,
    input wire [31:0] image_size, channels, cnn_param,
    output reg [31:0] cfg_input_addr, cfg_output_addr, cfg_weight_addr, cfg_bias_addr,
    output reg [31:0] cfg_image_size, cfg_channels, cfg_cnn_param,
    input wire config_valid, input_is_padding,
    input wire [31:0] output_width, output_height,
    input wire mem_idle, cmd_ready, rsp_valid,
    output reg cmd_valid, cmd_write, cmd_byte,
    output reg [1:0] address_select,
    output wire busy, done, error,
    output wire datapath_clear,
    output reg input_we, weight_we, bias_we, accumulator_load, mac_enable,
    output wire input_zero, pool_first,
    output reg pool_valid, output_we,
    output reg [31:0] output_x, output_y,
    output reg [15:0] input_channel, output_channel,
    output reg [3:0] tap, output reg [1:0] pool_sample,
    output wire [4:0] debug_state
);
    localparam IDLE=0, VALIDATE=1, LOAD_BIAS=2, WAIT_BIAS=3,
        INIT_ACC=4, LOAD_INPUT=5, WAIT_INPUT=6, LOAD_WEIGHT=7,
        WAIT_WEIGHT=8, CONV=9, RELU=10, POOL=11, QUANTIZE=12,
        WRITE_BACK=13, WAIT_WRITE=14, DONE=15, ERROR=16;
    reg [4:0] state;
    assign debug_state=state;
    assign busy=(state!=IDLE);
    assign done=(state==DONE);
    assign error=(state==ERROR);
    assign datapath_clear=soft_reset || state==VALIDATE;
    assign input_zero=(state==LOAD_INPUT && input_is_padding);
    assign pool_first=(pool_sample==0);
    always @* begin
        cmd_valid=0; cmd_write=0; cmd_byte=1; address_select=0;
        input_we=0; weight_we=0; bias_we=0; accumulator_load=0;
        mac_enable=0; pool_valid=0; output_we=0;
        if(!soft_reset) case(state)
            LOAD_BIAS: begin cmd_valid=1; cmd_byte=0; address_select=2; end
            WAIT_BIAS: bias_we=rsp_valid;
            INIT_ACC: accumulator_load=1;
            LOAD_INPUT: begin
                if(input_is_padding) input_we=1;
                else begin cmd_valid=1; address_select=0; end
            end
            WAIT_INPUT: input_we=rsp_valid;
            LOAD_WEIGHT: begin cmd_valid=1; address_select=1; end
            WAIT_WEIGHT: weight_we=rsp_valid;
            CONV: mac_enable=1;
            RELU: pool_valid=1;
            QUANTIZE: output_we=1;
            WRITE_BACK: begin cmd_valid=1; cmd_write=1; address_select=3; end
            default: ;
        endcase
    end
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            state<=IDLE; output_x<=0; output_y<=0; input_channel<=0;
            output_channel<=0; tap<=0; pool_sample<=0;
            cfg_input_addr<=0; cfg_output_addr<=0; cfg_weight_addr<=0; cfg_bias_addr<=0;
            cfg_image_size<=0; cfg_channels<=0; cfg_cnn_param<=0;
        end else if(soft_reset) begin
            state<=IDLE; output_x<=0; output_y<=0; input_channel<=0;
            output_channel<=0; tap<=0; pool_sample<=0;
        end else case(state)
            IDLE: if(start && mem_idle) begin
                cfg_input_addr<=input_addr; cfg_output_addr<=output_addr;
                cfg_weight_addr<=weight_addr; cfg_bias_addr<=bias_addr;
                cfg_image_size<=image_size; cfg_channels<=channels; cfg_cnn_param<=cnn_param;
                output_x<=0; output_y<=0; input_channel<=0;
                output_channel<=0; tap<=0; pool_sample<=0;
                state<=VALIDATE;
            end
            VALIDATE: state<=config_valid ? LOAD_BIAS : ERROR;
            LOAD_BIAS: if(cmd_ready) state<=WAIT_BIAS;
            WAIT_BIAS: if(rsp_valid) state<=INIT_ACC;
            INIT_ACC: begin tap<=0; input_channel<=0; state<=LOAD_INPUT; end
            LOAD_INPUT: begin
                if(input_is_padding) begin
                    if(tap==8) begin tap<=0; state<=LOAD_WEIGHT; end
                    else tap<=tap+1'b1;
                end else if(cmd_ready) state<=WAIT_INPUT;
            end
            WAIT_INPUT: if(rsp_valid) begin
                if(tap==8) begin tap<=0; state<=LOAD_WEIGHT; end
                else begin tap<=tap+1'b1; state<=LOAD_INPUT; end
            end
            LOAD_WEIGHT: if(cmd_ready) state<=WAIT_WEIGHT;
            WAIT_WEIGHT: if(rsp_valid) begin
                if(tap==8) begin tap<=0; state<=CONV; end
                else begin tap<=tap+1'b1; state<=LOAD_WEIGHT; end
            end
            CONV: begin
                if(tap==8) begin
                    tap<=0;
                    if(input_channel < cfg_channels[15:0]-1'b1) begin
                        input_channel<=input_channel+1'b1; state<=LOAD_INPUT;
                    end else state<=RELU;
                end else tap<=tap+1'b1;
            end
            RELU: state<=POOL;
            POOL: begin
                if(cfg_cnn_param[21] && pool_sample!=3) begin
                    pool_sample<=pool_sample+1'b1; state<=LOAD_BIAS;
                end else state<=QUANTIZE;
            end
            QUANTIZE: state<=WRITE_BACK;
            WRITE_BACK: if(cmd_ready) state<=WAIT_WRITE;
            WAIT_WRITE: if(rsp_valid) begin
                pool_sample<=0;
                if(output_channel < cfg_channels[31:16]-1'b1) begin
                    output_channel<=output_channel+1'b1; state<=LOAD_BIAS;
                end else begin
                    output_channel<=0;
                    if(output_x < output_width-1'b1) begin
                        output_x<=output_x+1'b1; state<=LOAD_BIAS;
                    end else begin
                        output_x<=0;
                        if(output_y < output_height-1'b1) begin
                            output_y<=output_y+1'b1; state<=LOAD_BIAS;
                        end else state<=DONE;
                    end
                end
            end
            DONE: state<=IDLE;
            ERROR: state<=IDLE;
            default: state<=ERROR;
        endcase
    end
endmodule
