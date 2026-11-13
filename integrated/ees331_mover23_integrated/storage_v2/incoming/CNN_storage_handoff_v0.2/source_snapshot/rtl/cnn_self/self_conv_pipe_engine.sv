// Cached UINT8 x INT8 valid convolution, producing raw signed INT32 sums.
// HWC activation/output; ordinary weights OHWI; depthwise weights [C,KY,KX].
// A tile's input (including halo) is read once and reused by all output
// channels. One output channel's weights are reused by every tile pixel.
// No activation, bias, zero-point correction, or requantization is applied.
// Input/weight byte responses must return the addressed byte in rdata[7:0].
// clear aborts this master; the interconnect must also cancel its pending
// transaction, as this interface has no transaction ID for a late response.
module self_conv_pipe_engine #(
 parameter integer MAX_CHANNELS=512, MAX_KERNEL=3, TILE=2
)(
 input logic clk,rst_n,clear,start,depthwise,
 input logic [31:0] input_base,weight_base,output_base,
 input logic [31:0] width,height,in_channels,out_channels,kernel,stride,
 output wire busy,done,error,valid,write,byte_access,
 output logic [31:0] addr,wdata,
 input logic ready,response,
 input logic [31:0] rdata,
 output wire mac_fire,
 output wire [3:0] phase,
 output logic [31:0] input_reads,weight_reads,mac_count
);
 localparam integer EDGE=2*(TILE-1)+MAX_KERNEL;
 localparam integer INPUT_BYTES=EDGE*EDGE*MAX_CHANNELS;
 localparam integer WEIGHT_BYTES=MAX_KERNEL*MAX_KERNEL*MAX_CHANNELS;
 localparam integer IA_BITS=$clog2(INPUT_BYTES+1);
 localparam integer WA_BITS=$clog2(WEIGHT_BYTES+1);
 localparam integer C_BITS=$clog2(MAX_CHANNELS+1);
 localparam integer P_BITS=(TILE*TILE>1)?$clog2(TILE*TILE):1;
 typedef enum logic [3:0] {
  IDLE,SETUP,CHECK,TILE_BEGIN,IREQ,IWAIT,WREQ,WWAIT,
  MAC_READ,MAC_ACC,OREQ,OWAIT,FINISH,FAIL
 } state_t;
 state_t state;
 (* ram_style="block" *) logic [7:0] input_mem[0:INPUT_BYTES-1];
 (* ram_style="block" *) logic signed [7:0] weight_mem[0:WEIGHT_BYTES-1];
 logic signed [31:0] tile_sum[0:TILE*TILE-1];
 logic [7:0] input_q;
 logic signed [7:0] weight_q;
 logic signed [16:0] product;
 logic signed [16:0] product_q;
 logic read_valid,product_valid,read_last,product_last;
 logic signed [31:0] accumulator,accumulated;

 logic [31:0] ib,wb,ob;
 logic [15:0] w,h,ow,oh;
 logic [C_BITS-1:0] ci,co,oc,load_c,mac_c;
 logic [2:0] k,tap_x,tap_y;
 logic dw,stride_two;
 logic [31:0] input_row_bytes,output_row_bytes,weight_per_channel;
 logic [63:0] input_extent,weight_extent,output_extent;
 // One shared serial unsigned multiplier handles descriptor sizes only.
 // Runtime address generation uses incrementers; only product is a DSP MAC.
 logic [63:0] mul_lhs,mul_acc,mul_value;
 logic [31:0] mul_rhs;
 logic [4:0] mul_bit;
 logic [2:0] setup_step;
 wire [63:0] input_end={32'd0,ib}+input_extent;
 wire [63:0] weight_end={32'd0,wb}+weight_extent;
 wire [63:0] output_end={32'd0,ob}+output_extent;

 logic [15:0] tile_x,tile_y;
 logic [7:0] tile_w,tile_h,tile_iw,tile_ih;
 logic [7:0] load_x,load_y,pixel_x,pixel_y,store_x,store_y;
 logic [P_BITS-1:0] pixel_index,store_index;
 logic [31:0] tile_input_base,tile_input_row_base;
 logic [31:0] tile_output_base,tile_output_row_base;
 logic [31:0] load_addr,load_row_addr,weight_channel_addr,weight_addr;
 logic [31:0] output_channel_addr,output_addr,output_pixel_row_addr;
 logic [IA_BITS-1:0] load_index,cache_row_bytes,input_index;
 logic [IA_BITS-1:0] window_base,window_row_base,kernel_row_base;
 logic [WA_BITS-1:0] weight_load_index,weight_index;
 wire [31:0] channel_stride_bytes=stride_two?({{(32-C_BITS){1'b0}},ci}<<1):ci;
 wire [31:0] output_pixel_bytes={{(32-C_BITS){1'b0}},co}<<2;
 wire input_response=response && (state==IWAIT || (state==IREQ && ready));
 wire weight_response=response && (state==WWAIT || (state==WREQ && ready));
 wire output_response=response && (state==OWAIT || (state==OREQ && ready));

 assign phase=state;
 assign busy=(state!=IDLE && state!=FINISH && state!=FAIL);
 assign done=(state==FINISH);
 assign error=(state==FAIL);
 assign valid=!clear && (state==IREQ || state==WREQ || state==OREQ);
 assign write=(state==OREQ);
 assign byte_access=(state==IREQ || state==WREQ);
 wire last_issue=(dw || mac_c+1'b1>=ci) && tap_x+1'b1>=k && tap_y+1'b1>=k;
 assign mac_fire=!clear && product_valid;
 always_comb begin
  addr=0;wdata=0;
  case(state)
   IREQ:addr=load_addr;
   WREQ:addr=weight_addr;
   OREQ:begin addr=output_addr;wdata=tile_sum[store_index];end
   default:;
  endcase
  mul_value=mul_acc+(mul_rhs[0]?mul_lhs:64'd0);
  product=$signed({1'b0,input_q})*$signed(weight_q);
  accumulated=accumulator+{{15{product_q[16]}},product_q};
 end

 // Issue one tap/channel each cycle. The last marker drains with its product,
 // so no partial sum from the following output pixel enters this accumulator.
 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin read_valid<=0;product_valid<=0;read_last<=0;product_last<=0;end
  else if(clear)begin read_valid<=0;product_valid<=0;read_last<=0;product_last<=0;end
  else begin
   read_valid<=state==MAC_READ;
   product_valid<=read_valid;
   if(state==MAC_READ)read_last<=last_issue;
   if(read_valid)begin product_q<=product;product_last<=read_last;end
  end
 end

 // Synchronous single-port accesses, without reset/clear loops on either RAM.
 // FSM never reads and writes one of these memories in the same cycle.
 always_ff @(posedge clk) begin
  if(!clear)begin
   if(input_response)input_mem[load_index]<=rdata[7:0];
   if(weight_response)weight_mem[weight_load_index]<=rdata[7:0];
   if(state==MAC_READ)begin
    input_q<=input_mem[input_index];
    weight_q<=weight_mem[weight_index];
   end
  end
 end

 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   state<=IDLE;input_reads<=0;weight_reads<=0;mac_count<=0;
  end else if(clear)begin
   state<=IDLE;input_reads<=0;weight_reads<=0;mac_count<=0;
  end else case(state)
   IDLE:if(start)begin
    input_reads<=0;weight_reads<=0;mac_count<=0;
    ib<=input_base;wb<=weight_base;ob<=output_base;
    w<=width[15:0];h<=height[15:0];ci<=in_channels[C_BITS-1:0];co<=out_channels[C_BITS-1:0];
    k<=kernel[2:0];dw<=depthwise;stride_two<=(stride==2);
    ow<=((width-kernel)>>((stride==2)?1:0))+1;
    oh<=((height-kernel)>>((stride==2)?1:0))+1;
    setup_step<=0;mul_bit<=0;mul_acc<=0;
    mul_lhs<={32'd0,width};mul_rhs<=in_channels;
    if(MAX_CHANNELS<1 || MAX_CHANNELS>65535 || TILE<1 || TILE>4 ||
       (MAX_KERNEL!=1 && MAX_KERNEL!=3) ||
       (kernel!=1 && kernel!=3) || kernel>MAX_KERNEL ||
       (stride!=1 && stride!=2) || width<kernel || height<kernel ||
       width>65535 || height>65535 || in_channels==0 || out_channels==0 ||
       in_channels>MAX_CHANNELS || out_channels>MAX_CHANNELS ||
       (depthwise && in_channels!=out_channels) || output_base[1:0]!=0)
     state<=FAIL;
    else state<=SETUP;
   end
   SETUP:begin
    if(mul_bit!=31)begin
     mul_acc<=mul_value;mul_lhs<=mul_lhs<<1;mul_rhs<=mul_rhs>>1;mul_bit<=mul_bit+1'b1;
    end else begin
     mul_bit<=0;mul_acc<=0;setup_step<=setup_step+1'b1;
     case(setup_step)
      0:begin input_row_bytes<=mul_value[31:0];mul_lhs<=mul_value;mul_rhs<={16'd0,h};end
      1:begin input_extent<=mul_value;mul_lhs<=dw?64'd1:{{(64-C_BITS){1'b0}},ci};mul_rhs<=(k==3)?32'd9:32'd1;end
      2:begin weight_per_channel<=mul_value[31:0];mul_lhs<=mul_value;mul_rhs<=co;end
      3:begin weight_extent<=mul_value;mul_lhs<={48'd0,ow};mul_rhs<=co;end
      4:begin output_row_bytes<=mul_value[31:0]<<2;mul_lhs<=mul_value<<2;mul_rhs<={16'd0,oh};end
      5:begin output_extent<=mul_value;state<=CHECK;end
      default:state<=FAIL;
     endcase
    end
   end
   CHECK:begin
    // Intervals are half-open: an end of 2^32 is legal. Read-only input
    // and weights may share storage, but output must not overwrite either.
    if(input_end>64'h100000000 || weight_end>64'h100000000 || output_end>64'h100000000 ||
       ({32'd0,ob}<input_end && {32'd0,ib}<output_end) ||
       ({32'd0,ob}<weight_end && {32'd0,wb}<output_end))state<=FAIL;
    else begin
     tile_x<=0;tile_y<=0;
     tile_input_base<=ib;tile_input_row_base<=ib;
     tile_output_base<=ob;tile_output_row_base<=ob;
     state<=TILE_BEGIN;
    end
   end
   TILE_BEGIN:begin
    tile_w<=((ow-tile_x)<TILE)?(ow-tile_x):TILE;
    tile_h<=((oh-tile_y)<TILE)?(oh-tile_y):TILE;
    tile_iw<=((((ow-tile_x)<TILE)?(ow-tile_x):TILE)-1)*(stride_two?2:1)+k;
    tile_ih<=((((oh-tile_y)<TILE)?(oh-tile_y):TILE)-1)*(stride_two?2:1)+k;
    load_x<=0;load_y<=0;load_c<=0;load_index<=0;
    load_addr<=tile_input_base;load_row_addr<=tile_input_base;
    oc<=0;weight_channel_addr<=wb;weight_addr<=wb;weight_load_index<=0;
    output_channel_addr<=tile_output_base;
    state<=IREQ;
   end
   IREQ,IWAIT:begin
    if(state==IREQ && ready)state<=IWAIT;
    if(input_response)begin
     input_reads<=input_reads+1'b1;load_index<=load_index+1'b1;
     if(load_c+1'b1<ci)begin
      load_c<=load_c+1'b1;load_addr<=load_addr+1'b1;state<=IREQ;
     end else if(load_x+1'b1<tile_iw)begin
      load_c<=0;load_x<=load_x+1'b1;load_addr<=load_addr+1'b1;state<=IREQ;
     end else begin
      if(load_y==0)cache_row_bytes<=load_index+1'b1;
      load_c<=0;load_x<=0;
      if(load_y+1'b1<tile_ih)begin
       load_y<=load_y+1'b1;load_row_addr<=load_row_addr+input_row_bytes;
       load_addr<=load_row_addr+input_row_bytes;state<=IREQ;
      end else state<=WREQ;
     end
    end
   end
   WREQ,WWAIT:begin
    if(state==WREQ && ready)state<=WWAIT;
    if(weight_response)begin
     weight_reads<=weight_reads+1'b1;
     if(weight_load_index+1'b1<weight_per_channel)begin
      weight_load_index<=weight_load_index+1'b1;weight_addr<=weight_addr+1'b1;state<=WREQ;
     end else begin
      pixel_x<=0;pixel_y<=0;pixel_index<=0;window_base<=0;window_row_base<=0;
      input_index<=dw?oc:0;kernel_row_base<=dw?oc:0;
      weight_index<=0;tap_x<=0;tap_y<=0;mac_c<=0;accumulator<=0;
      state<=MAC_READ;
     end
    end
   end
   MAC_READ,MAC_ACC:begin
    if(state==MAC_READ)begin
     if(last_issue)state<=MAC_ACC;
     else if(!dw && mac_c+1'b1<ci)begin
     mac_c<=mac_c+1'b1;input_index<=input_index+1'b1;weight_index<=weight_index+1'b1;
    end else if(tap_x+1'b1<k)begin
     tap_x<=tap_x+1'b1;mac_c<=0;
     input_index<=input_index+(dw?ci:1);weight_index<=weight_index+1'b1;
    end else if(tap_y+1'b1<k)begin
     tap_x<=0;tap_y<=tap_y+1'b1;mac_c<=0;
     kernel_row_base<=kernel_row_base+cache_row_bytes;
     input_index<=kernel_row_base+cache_row_bytes;weight_index<=weight_index+1'b1;
     end
    end
    if(product_valid)begin
     accumulator<=accumulated;mac_count<=mac_count+1'b1;
    end
    if(product_valid && product_last)begin
     state<=MAC_READ;
     tile_sum[pixel_index]<=accumulated;
     accumulator<=0;weight_index<=0;tap_x<=0;tap_y<=0;mac_c<=0;
     if(pixel_x+1'b1<tile_w)begin
      pixel_x<=pixel_x+1'b1;pixel_index<=pixel_index+1'b1;
      window_base<=window_base+channel_stride_bytes;
      input_index<=window_base+channel_stride_bytes+(dw?oc:0);
      kernel_row_base<=window_base+channel_stride_bytes+(dw?oc:0);
     end else if(pixel_y+1'b1<tile_h)begin
      pixel_x<=0;pixel_y<=pixel_y+1'b1;pixel_index<=pixel_index+1'b1;
      window_row_base<=window_row_base+(stride_two?(cache_row_bytes<<1):cache_row_bytes);
      window_base<=window_row_base+(stride_two?(cache_row_bytes<<1):cache_row_bytes);
      input_index<=window_row_base+(stride_two?(cache_row_bytes<<1):cache_row_bytes)+(dw?oc:0);
      kernel_row_base<=window_row_base+(stride_two?(cache_row_bytes<<1):cache_row_bytes)+(dw?oc:0);
     end else begin
      store_index<=0;store_x<=0;store_y<=0;
      output_addr<=output_channel_addr;output_pixel_row_addr<=output_channel_addr;state<=OREQ;
     end
    end
   end
   OREQ,OWAIT:begin
    if(state==OREQ && ready)state<=OWAIT;
    if(output_response)begin
     if(store_x+1'b1<tile_w)begin
      store_x<=store_x+1'b1;store_index<=store_index+1'b1;
      output_addr<=output_addr+output_pixel_bytes;state<=OREQ;
     end else if(store_y+1'b1<tile_h)begin
      store_x<=0;store_y<=store_y+1'b1;store_index<=store_index+1'b1;
      output_pixel_row_addr<=output_pixel_row_addr+output_row_bytes;
      output_addr<=output_pixel_row_addr+output_row_bytes;state<=OREQ;
     end else if(oc+1'b1<co)begin
      oc<=oc+1'b1;weight_load_index<=0;
      weight_channel_addr<=weight_channel_addr+weight_per_channel;
      weight_addr<=weight_channel_addr+weight_per_channel;
      output_channel_addr<=output_channel_addr+4;state<=WREQ;
     end else if(tile_x+tile_w<ow)begin
      tile_x<=tile_x+tile_w;
      tile_input_base<=tile_input_base+TILE*channel_stride_bytes;
      tile_output_base<=tile_output_base+TILE*output_pixel_bytes;state<=TILE_BEGIN;
     end else if(tile_y+tile_h<oh)begin
      tile_x<=0;tile_y<=tile_y+tile_h;
      tile_input_row_base<=tile_input_row_base+TILE*(stride_two?(input_row_bytes<<1):input_row_bytes);
      tile_input_base<=tile_input_row_base+TILE*(stride_two?(input_row_bytes<<1):input_row_bytes);
      tile_output_row_base<=tile_output_row_base+TILE*output_row_bytes;
      tile_output_base<=tile_output_row_base+TILE*output_row_bytes;state<=TILE_BEGIN;
     end else state<=FINISH;
    end
   end
   FINISH,FAIL:state<=IDLE;
   default:state<=FAIL;
  endcase
 end
endmodule
