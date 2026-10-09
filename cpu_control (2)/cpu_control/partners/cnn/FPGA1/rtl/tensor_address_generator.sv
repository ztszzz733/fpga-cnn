`timescale 1ns/1ps
// CHW elementwise and 2x2/stride2/floor MaxPool byte addresses.
module tensor_address_generator(input wire [31:0] ia,oa,wa,ba,fs,ch,lp,
    input wire [3:0] op,input wire [31:0] index,input wire [1:0] tap,
    output wire [31:0] input_address,second_address,output_address,param_address,
    output wire [31:0] output_count,channel_end);
    wire [31:0] w={16'd0,fs[15:0]},h={16'd0,fs[31:16]};
    wire pool=op==8,wide=op==10 && lp[20];
    wire [31:0] ow=pool ? w>>1 : w,oh=pool ? h>>1 : h;
    wire [31:0] plane=ow*oh;
    wire [31:0] channel=plane!=0 ? index/plane : 0;
    wire [31:0] pos=plane!=0 ? index%plane : 0;
    wire [31:0] y=ow!=0 ? pos/ow : 0,x=ow!=0 ? pos%ow : 0;
    assign input_address=ia+(pool ? (channel*h+2*y+{31'd0,tap[1]})*w+2*x+{31'd0,tap[0]} : (wide ? index*4 : index));
    assign second_address=wa+index;
    assign output_address=oa+index;
    assign param_address=ba+(lp[21] ? channel*24 : 0);
    assign output_count=plane*{16'd0,ch[15:0]};
    assign channel_end=(channel+1)*plane;
endmodule
