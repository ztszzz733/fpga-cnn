`timescale 1ns/1ps
// Four word-aligned RAM spans: input, second input/weights, parameters/bias, output.
// MATMUL: A[M,K] @WA, B[K,N] @IA, C[M,N] @OA uses the existing 1x1 data path.
module task_descriptor_info(
    input wire [255:0] descriptor,input wire [31:0] queue_base,input wire [63:0] queue_end,
    output wire valid,output wire [511:0] spans
);
    wire [31:0] ia=descriptor[63:32],oa=descriptor[95:64],wa=descriptor[127:96],ba=descriptor[159:128];
    wire [31:0] fs=descriptor[191:160],ch=descriptor[223:192],lp=descriptor[255:224];
    wire [7:0] op=descriptor[7:0];
    wire matrix=op==9,conv=op==0 || op==1 || matrix;
    wire [31:0] ow,oh,count,u0,u1,u2,u3,u4;wire padding,geometry;
    address_generator check_config(ia,oa,wa,ba,fs,ch,lp,matrix ? 4'd0 : op[3:0],
        32'd0,32'd0,32'd0,16'd0,16'd0,6'd0,u0,u1,u2,u3,u4,ow,oh,count,padding,geometry);
    wire [63:0] w={48'd0,fs[15:0]},h={48'd0,fs[31:16]},ci={48'd0,ch[15:0]},co={48'd0,ch[31:16]};
    wire vector_op=op==2 || op==3 || op==6 || op==7 || op==8 || op==10;
    wire wide=op==10 && lp[20];
    wire [63:0] ni=w*h*ci*(wide ? 64'd4 : 64'd1);
    wire [63:0] nw=conv ? co*(op==1 ? 64'd1 : ci)*{60'd0,lp[3:0]}*{60'd0,lp[3:0]} :
        (op==3 ? w*h*ci : 64'd0);
    wire [63:0] nb=conv ? co*4 : (ba==0 ? 64'd0 : (lp[21] ? ci*24 : 64'd24));
    wire [63:0] no=conv ? {32'd0,count} : (op==8 ? (w/2)*(h/2)*ci : w*h*ci);
    wire [63:0] ie={32'd0,ia}+ni,we={32'd0,wa}+nw,be={32'd0,ba}+nb,oe={32'd0,oa}+no;
    function [63:0] floor_word(input [31:0] a);floor_word={32'd0,a[31:2],2'b00};endfunction
    function [63:0] ceil_word(input [63:0] a);ceil_word=(a+3)&64'hfffffffffffffffc;endfunction
    assign spans={ceil_word(oe),floor_word(oa),
        nb!=0 ? ceil_word(be) : 64'd0,nb!=0 ? floor_word(ba) : 64'd0,
        nw!=0 ? ceil_word(we) : 64'd0,nw!=0 ? floor_word(wa) : 64'd0,
        ceil_word(ie),floor_word(ia)};
    wire vector_valid=vector_op && w!=0 && h!=0 && ci!=0 && ci==co &&
        no!=0 && ni<=64'hffffffff && no<=64'hffffffff &&
        ie<=64'h100000000 && oe<=64'h100000000 && we<=64'h100000000 && be<=64'h100000000 &&
        (oe<={32'd0,ia} || {32'd0,oa}>=ie) &&
        (nw==0 || oe<={32'd0,wa} || {32'd0,oa}>=we) &&
        (nb==0 || (ba[1:0]==0 && (oe<={32'd0,ba} || {32'd0,oa}>=be))) &&
        (!wide || ia[1:0]==0) && (op!=7 || ba!=0) &&
        lp[31:23]==0 && (!lp[20] || op==10) &&
        (op==8 ? lp[11:0]==12'h022 : lp[11:0]==0);
    assign valid=descriptor[31:8]==24'd1 &&
        (conv ? (geometry && (!matrix || (fs[31:16]==1 && lp[11:0]==12'h011))) : vector_valid) &&
        (oe<={32'd0,queue_base} || {32'd0,oa}>=queue_end);
endmodule
