`timescale 1ns/1ps
// Implicit im2col: no expanded image in RAM. Tile rows=OC, columns=flattened OH*OW.
// Normal reduction=IC*KY*KX; DW reduction=KY*KX and IC=OC for each row.
module conv_window_address(
    input wire [31:0] ia,oa,wa,ba,fs,ch,lp,input wire [3:0] op,
    input wire [31:0] row_base,col_base,k_base,
    input wire [2:0] row,col,k_index,
    output wire [31:0] input_address,weight_address,bias_address,output_address,
    output wire padding,valid,output wire [31:0] spatial_count,reduction_count,output_count
);
    wire [31:0] ow,oh,second_unused;
    wire [31:0] ksquare={28'd0,lp[3:0]}*lp[3:0];
    wire [31:0] red=k_base+{29'd0,k_index},pos=col_base+{29'd0,col},channel=row_base+{29'd0,row};
    wire [31:0] in_channel=op==1 ? channel : (ksquare!=0 ? red/ksquare : 0);
    wire [31:0] tap=ksquare!=0 ? red%ksquare : 0;
    assign spatial_count=ow*oh;
    assign reduction_count=ksquare*(op==1 ? 32'd1 : {16'd0,ch[15:0]});
    address_generator generator(ia,oa,wa,ba,fs,ch,lp,op,
        ow!=0 ? pos%ow : 32'd0,ow!=0 ? pos/ow : 32'd0,32'd0,
        in_channel[15:0],channel[15:0],tap[5:0],input_address,weight_address,bias_address,output_address,
        second_unused,ow,oh,output_count,padding,valid);
endmodule
