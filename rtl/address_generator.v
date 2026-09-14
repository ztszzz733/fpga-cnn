`timescale 1ns/1ps
// Byte addresses: activations HWC, weights [OC][KY][KX][IC], bias [OC].
// Wide intermediates prevent silent 32-bit overflow during validation.
module address_generator(
    input wire [31:0] input_base, output_base, weight_base, bias_base,
    input wire [31:0] image_size, channels, cnn_param,
    input wire [31:0] output_x, output_y,
    input wire [15:0] input_channel, output_channel,
    input wire [3:0] tap, input wire [1:0] pool_sample,
    output reg [31:0] input_address, output_address, weight_address, bias_address,
    output reg input_is_padding, output wire config_valid,
    output wire [31:0] conv_width, conv_height, output_width, output_height
);
    // Configuration-only arithmetic is continuously driven and independent
    // of tap/coordinate changes (including when configuration is constant).
    wire [63:0] w={48'd0,image_size[15:0]}, h={48'd0,image_size[31:16]};
    wire [63:0] ci={48'd0,channels[15:0]}, co={48'd0,channels[31:16]};
    wire [63:0] s={60'd0,cnn_param[7:4]}, p={60'd0,cnn_param[11:8]};
    wire extent_valid=(s!=0 && w+2*p>=3 && h+2*p>=3);
    wire [63:0] cw=extent_valid ? (w+2*p-3)/s+1 : 64'd0;
    wire [63:0] ch=extent_valid ? (h+2*p-3)/s+1 : 64'd0;
    wire [63:0] ow=cnn_param[21] ? cw/2 : cw;
    wire [63:0] oh=cnn_param[21] ? ch/2 : ch;
    wire [63:0] input_end={32'd0,input_base}+w*h*ci;
    wire [63:0] weight_end={32'd0,weight_base}+co*9*ci;
    wire [63:0] bias_end={32'd0,bias_base}+co*4;
    wire [63:0] output_end={32'd0,output_base}+ow*oh*co;
    reg [63:0] px,py;
    reg signed [63:0] ix,iy;
    wire [3:0] tap_x = tap % 4'd3;
    wire [3:0] tap_y = tap / 4'd3;
    assign conv_width=cw[31:0], conv_height=ch[31:0];
    assign output_width=ow[31:0], output_height=oh[31:0];
    assign config_valid=(w!=0 && h!=0 && ci!=0 && co!=0 && s!=0 &&
                      cnn_param[3:0]==3 && cnn_param[31:22]==0 &&
                      ow!=0 && oh!=0 && bias_base[1:0]==0 &&
                      input_end<=64'h100000000 && weight_end<=64'h100000000 &&
                      bias_end<=64'h100000000 && output_end<=64'h100000000 &&
                      // No in-place output: subsequent convolution reads must
                      // still see the original input, weights and bias.
                      (output_end<={32'd0,input_base} || {32'd0,output_base}>=input_end) &&
                      (output_end<={32'd0,weight_base} || {32'd0,output_base}>=weight_end) &&
                      (output_end<={32'd0,bias_base} || {32'd0,output_base}>=bias_end));
    always @* begin
        px={32'd0,output_x}; py={32'd0,output_y};
        if(cnn_param[21]) begin
            px=px*2+{63'd0,pool_sample[0]};
            py=py*2+{63'd0,pool_sample[1]};
        end
        ix=$signed(px*s)+$signed({60'd0,tap_x})-$signed(p);
        iy=$signed(py*s)+$signed({60'd0,tap_y})-$signed(p);
        input_is_padding=(ix<0 || iy<0 || ix>=$signed(w) || iy>=$signed(h));
        input_address=0;
        if(!input_is_padding)
            input_address=input_base+((iy*w+ix)*ci+input_channel);
        weight_address=weight_base+(({48'd0,output_channel}*9+tap)*ci+input_channel);
        bias_address=bias_base+{16'd0,output_channel}*4;
        output_address=output_base+(({32'd0,output_y}*ow+output_x)*co+output_channel);
    end
endmodule
