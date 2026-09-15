`timescale 1ns/1ps
// One START = one operator. Network scheduling belongs to the external host.
module mobilefacenet_controller(
    input wire clk,rst_n,soft_reset,start,
    input wire [31:0] input_addr,output_addr,weight_addr,bias_addr,feature_size,channels,layer_param,
    input wire [3:0] op_type,
    output reg [31:0] cfg_input_addr,cfg_output_addr,cfg_weight_addr,cfg_bias_addr,cfg_feature_size,cfg_channels,cfg_layer_param,
    output reg [3:0] cfg_op_type,
    input wire config_valid,input_is_padding,
    input wire [31:0] output_width,output_height,output_count,
    input wire mem_idle,cmd_ready,rsp_valid,engine_ready,engine_done,engine_error,
    output reg cmd_valid,cmd_write,cmd_byte,output reg [2:0] address_select,
    output wire busy,done,error,datapath_clear,
    output reg input_we,weight_we,bias_we,engine_start,sample_valid,output_we,
    output wire input_zero,
    output reg [31:0] output_x,output_y,element_index,
    output reg [15:0] input_channel,output_channel,output reg [5:0] tap,
    output wire [4:0] debug_state
);
    localparam IDLE=0,LOAD_CONFIG=1,LOAD_BIAS=2,WAIT_BIAS=3,ENGINE_START=4,
        LOAD_INPUT=5,WAIT_INPUT=6,LOAD_WEIGHT=7,WAIT_WEIGHT=8,CONV=9,WAIT_ENGINE=10,
        READ_A=11,WAIT_A=12,READ_B=13,WAIT_B=14,POST=15,WRITE_BACK=16,WAIT_WRITE=17,DONE=18,ERROR=19;
    reg [4:0] state;
    wire convolution=cfg_op_type<=1;
    wire [7:0] taps={4'd0,cfg_layer_param[3:0]}*cfg_layer_param[3:0];
    assign busy=state!=IDLE;assign done=state==DONE;assign error=state==ERROR;
    assign debug_state=state;
    assign datapath_clear=soft_reset || state==LOAD_CONFIG;
    assign input_zero=state==LOAD_INPUT && input_is_padding;
    always @* begin
        cmd_valid=0;cmd_write=0;cmd_byte=1;address_select=0;
        input_we=0;weight_we=0;bias_we=0;engine_start=0;sample_valid=0;output_we=0;
        if(!soft_reset) case(state)
            LOAD_BIAS:begin cmd_valid=1;cmd_byte=0;address_select=2;end
            WAIT_BIAS:bias_we=rsp_valid;
            ENGINE_START:engine_start=1;
            LOAD_INPUT:if(input_is_padding) input_we=1;else cmd_valid=1;
            WAIT_INPUT:input_we=rsp_valid;
            LOAD_WEIGHT:begin cmd_valid=1;address_select=1;end
            WAIT_WEIGHT:weight_we=rsp_valid;
            CONV:sample_valid=1;
            READ_A:cmd_valid=1;
            WAIT_A:input_we=rsp_valid;
            READ_B:begin cmd_valid=1;address_select=4;end
            WAIT_B:weight_we=rsp_valid;
            POST:output_we=1;
            WRITE_BACK:begin cmd_valid=1;cmd_write=1;address_select=3;end
            default:;
        endcase
    end
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            state<=IDLE;output_x<=0;output_y<=0;element_index<=0;input_channel<=0;output_channel<=0;tap<=0;
            cfg_input_addr<=0;cfg_output_addr<=0;cfg_weight_addr<=0;cfg_bias_addr<=0;
            cfg_feature_size<=0;cfg_channels<=0;cfg_layer_param<=0;cfg_op_type<=0;
        end else if(soft_reset) begin
            state<=IDLE;output_x<=0;output_y<=0;element_index<=0;input_channel<=0;output_channel<=0;tap<=0;
        end else if(engine_error) state<=ERROR;
        else case(state)
            IDLE:if(start && mem_idle) begin
                cfg_input_addr<=input_addr;cfg_output_addr<=output_addr;cfg_weight_addr<=weight_addr;cfg_bias_addr<=bias_addr;
                cfg_feature_size<=feature_size;cfg_channels<=channels;cfg_layer_param<=layer_param;cfg_op_type<=op_type;
                output_x<=0;output_y<=0;element_index<=0;input_channel<=0;output_channel<=0;tap<=0;state<=LOAD_CONFIG;
            end
            LOAD_CONFIG:if(!config_valid) state<=ERROR;else state<=convolution ? LOAD_BIAS : READ_A;
            LOAD_BIAS:if(cmd_ready) state<=WAIT_BIAS;
            WAIT_BIAS:if(rsp_valid) state<=ENGINE_START;
            ENGINE_START:begin tap<=0;input_channel<=0;state<=LOAD_INPUT;end
            LOAD_INPUT:if(input_is_padding) begin
                if(tap==taps-1) begin tap<=0;state<=LOAD_WEIGHT;end else tap<=tap+1'b1;
            end else if(cmd_ready) state<=WAIT_INPUT;
            WAIT_INPUT:if(rsp_valid) begin
                if(tap==taps-1) begin tap<=0;state<=LOAD_WEIGHT;end
                else begin tap<=tap+1'b1;state<=LOAD_INPUT;end
            end
            LOAD_WEIGHT:if(cmd_ready) state<=WAIT_WEIGHT;
            WAIT_WEIGHT:if(rsp_valid) begin
                if(tap==taps-1) begin tap<=0;state<=CONV;end
                else begin tap<=tap+1'b1;state<=LOAD_WEIGHT;end
            end
            CONV:if(engine_ready) begin
                if(tap==taps-1) begin
                    tap<=0;
                    if(cfg_op_type==0 && input_channel<cfg_channels[15:0]-1'b1) begin
                        input_channel<=input_channel+1'b1;state<=LOAD_INPUT;
                    end else state<=WAIT_ENGINE;
                end else tap<=tap+1'b1;
            end
            WAIT_ENGINE:if(engine_done) state<=POST;
            READ_A:if(cmd_ready) state<=WAIT_A;
            WAIT_A:if(rsp_valid) state<=cfg_op_type==3 ? READ_B : POST;
            READ_B:if(cmd_ready) state<=WAIT_B;
            WAIT_B:if(rsp_valid) state<=POST;
            POST:state<=WRITE_BACK;
            WRITE_BACK:if(cmd_ready) state<=WAIT_WRITE;
            WAIT_WRITE:if(rsp_valid) begin
                if(!convolution) begin
                    if(element_index==output_count-1) state<=DONE;
                    else begin element_index<=element_index+1;state<=READ_A;end
                end else if(output_x<output_width-1) begin output_x<=output_x+1;state<=LOAD_BIAS;end
                else begin
                    output_x<=0;
                    if(output_y<output_height-1) begin output_y<=output_y+1;state<=LOAD_BIAS;end
                    else begin
                        output_y<=0;
                        if(output_channel<cfg_channels[31:16]-1'b1) begin output_channel<=output_channel+1'b1;state<=LOAD_BIAS;end
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
