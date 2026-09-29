`timescale 1ns/1ps
// CHW activation, OIHW normal weights, [C][KY][KX] depthwise weights.
// All arithmetic and range checks are byte based. No tensor address formulas
// are duplicated in the controller. BatchNorm is folded offline:
// a[c]=gamma[c]/sqrt(var[c]+epsilon), W'[c]=a[c]*W[c],
// b'[c]=beta[c]+a[c]*(b[c]-mean[c]). Quantize AFTER folding.
module address_generator(
    input wire [31:0] input_base,output_base,weight_base,bias_base,
    input wire [31:0] feature_size,channels,layer_param,input wire [3:0] op_type,
    input wire [31:0] output_x,output_y,element_index,
    input wire [15:0] input_channel,output_channel,input wire [5:0] tap,
    output reg [31:0] input_address,weight_address,bias_address,output_address,
    output wire [31:0] second_address,output_width,output_height,output_count,
    output reg input_is_padding,output wire config_valid
);
    wire convolution=op_type==0 || op_type==1;
    wire [63:0] w={48'd0,feature_size[15:0]},h={48'd0,feature_size[31:16]};
    wire [63:0] ci={48'd0,channels[15:0]},co={48'd0,channels[31:16]};
    wire [63:0] k={60'd0,layer_param[3:0]},s={60'd0,layer_param[7:4]},p={60'd0,layer_param[11:8]};
    wire geometry=s!=0 && k!=0 && w+2*p>=k && h+2*p>=k;
    wire [63:0] ow=geometry ? (w+2*p-k)/s+1 : 64'd0;
    wire [63:0] oh=geometry ? (h+2*p-k)/s+1 : 64'd0;
    wire [63:0] in_size=w*h*ci,out_size=ow*oh*co;
    wire [63:0] weight_size=(op_type==0) ? co*ci*k*k : co*k*k;
    wire [63:0] in_end={32'd0,input_base}+in_size;
    wire [63:0] out_end={32'd0,output_base}+out_size;
    wire [63:0] weight_end={32'd0,weight_base}+weight_size;
    wire [63:0] bias_end={32'd0,bias_base}+co*4;
    wire input_disjoint=out_end<={32'd0,input_base} || {32'd0,output_base}>=in_end;
    wire weight_disjoint=out_end<={32'd0,weight_base} || {32'd0,output_base}>=weight_end;
    wire bias_disjoint=out_end<={32'd0,bias_base} || {32'd0,output_base}>=bias_end;
    wire conv_valid=geometry && bias_base[1:0]==0 &&
        ((op_type==0 && (k==1 || k==3)) || (op_type==1 && (k==3 || k==7) && ci==co)) &&
        weight_end<=64'h100000000 && bias_end<=64'h100000000 && weight_disjoint && bias_disjoint;
    assign config_valid=convolution && layer_param[31:20]==0 && w!=0 && h!=0 && ci!=0 && co!=0 &&
        ow!=0 && oh!=0 && in_size<=64'hffffffff && out_size<=64'hffffffff &&
        in_end<=64'h100000000 && out_end<=64'h100000000 && input_disjoint &&
        conv_valid;
    assign output_width=ow[31:0],output_height=oh[31:0],output_count=out_size[31:0];
    assign second_address=0;
    wire [63:0] tx=k!=0 ? {58'd0,tap}%k : 64'd0;
    wire [63:0] ty=k!=0 ? {58'd0,tap}/k : 64'd0;
    wire [63:0] channel_index=op_type==1 ? {48'd0,output_channel} : {48'd0,input_channel};
    reg signed [63:0] ix,iy;
    always @* begin
        ix=$signed({32'd0,output_x}*s+tx)-$signed(p);
        iy=$signed({32'd0,output_y}*s+ty)-$signed(p);
        input_is_padding=convolution && (ix<0 || iy<0 || ix>=$signed(w) || iy>=$signed(h));
        input_address=0;
        if(convolution) begin
            input_address=0;
            if(!input_is_padding) input_address=input_base+((channel_index*h+iy)*w+ix);
        end
        weight_address=weight_base+((op_type==1 ? {48'd0,output_channel} : {48'd0,output_channel}*ci+input_channel)*k*k+tap);
        bias_address=bias_base+{16'd0,output_channel}*4;
        output_address=output_base+(({48'd0,output_channel}*oh+output_y)*ow+output_x);
    end
endmodule
