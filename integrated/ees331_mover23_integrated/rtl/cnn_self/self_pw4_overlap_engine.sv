// Four spatial lanes for ordinary 1x1 UINT8 x INT8 -> raw INT32.
// HWC / OHWI, 2x2 output tile. Each input pixel has its own synchronous RAM.
// One cached weight is broadcast to all live pixels; local sums wrap to INT32.
// Aligned groups use 32-bit reads; unaligned starts/tails use exact byte reads.
// Double-buffered weights and an eight-word write FIFO overlap local MACs.
// One outstanding external transaction; clear requires fabric cancellation too.
module self_pw4_overlap_engine #(parameter MAX_CHANNELS=512)(
 input logic clk,rst_n,clear,start,depthwise,
 input logic [31:0] input_base,weight_base,output_base,width,height,
 input logic [31:0] in_channels,out_channels,kernel,stride,
 output wire busy,done,error,valid,write,byte_access,
 output logic [31:0] addr,wdata,
 input logic ready,response,input logic [31:0] rdata,
 output wire mac_fire,output wire [3:0] phase,
 output logic [31:0] input_reads,weight_reads,mac_count
);
 localparam WORDS=(MAX_CHANNELS+3)/4, C_BITS=$clog2(MAX_CHANNELS+1);
 typedef enum logic [3:0] {IDLE,SETUP,CHECK,TILE_BEGIN,IREQ,WREQ,MAC_RUN,OREQ,OWAIT,DRAIN,FINISH,FAIL} state_t;
 state_t state;
 logic [31:0] ib,wb,ob;
 logic [C_BITS-1:0] ci,co,oc;
 logic [15:0] w,h,ow,oh;
 logic stride_two;
 logic [31:0] input_row_bytes,output_row_bytes;
 logic [63:0] input_extent,weight_extent,output_extent;
 logic [63:0] mul_lhs,mul_acc,mul_value;
 logic [31:0] mul_rhs;logic [4:0] mul_bit;logic [2:0] setup_step;
 wire [63:0] input_end={32'd0,ib}+input_extent;
 wire [63:0] weight_end={32'd0,wb}+weight_extent;
 wire [63:0] output_end={32'd0,ob}+output_extent;
 logic [31:0] tile_x,tile_y,tile_input_base,tile_input_row_base,tile_output_base,tile_output_row_base;
 logic [1:0] tile_w,tile_h,load_lane,store_lane;
 logic [31:0] load_addr,weight_addr,weight_channel_addr,output_addr;
 logic [C_BITS-1:0] load_c,weight_c,issue_c,retire_c;
 logic pipe_valid,product_valid;logic [1:0] pipe_offset;
 logic [31:0] input_q[4],weight_q[2];
 logic signed [31:0] sums[4];
 logic signed [16:0] products[4];
 logic signed [16:0] product_q[4];
 logic [3:0] lane_mask;
 logic [2:0] live_lanes;
 // Weight producer owns the inactive bank until its last response arrives.
 logic compute_bank,fill_bank,fill_active;
 logic [1:0] weight_loaded;
 logic [31:0] out_data[8],out_addr[8];
 logic [2:0] q_read,q_write;
 logic [3:0] q_count;
 wire push=state==OREQ && q_count<8 && !clear;
 localparam [1:0] INPUT_READ=0,WEIGHT_READ=1,OUTPUT_WRITE=2;
 logic bus_valid,bus_pending,bus_byte,prefer_write;
 logic [1:0] bus_kind;
 logic [31:0] bus_addr,bus_data;
 logic held,held_byte;
 logic [1:0] held_kind;
 logic [31:0] held_addr,held_data;
 logic offer_valid,offer_byte;
 logic [1:0] offer_kind;
 logic [31:0] offer_addr,offer_data;
 wire accept=bus_valid && ready && !clear;
 wire complete=response && (bus_pending || accept) && !clear;
 wire input_response=complete && bus_kind==INPUT_READ;
 wire weight_response=complete && bus_kind==WEIGHT_READ;
 wire output_response=complete && bus_kind==OUTPUT_WRITE;
 // Aligned c has four valid bytes iff its word number precedes ci/4.
 // Each loader retains its address/counter until its own response, so its
 // count need not pass through the shared arbitration/held-request mux.
 wire in_wide=load_addr[1:0]==0 && load_c[1:0]==0 && (load_c>>2)<(ci>>2);
 wire weight_wide=weight_addr[1:0]==0 && weight_c[1:0]==0 && (weight_c>>2)<(ci>>2);
 wire [2:0] in_count=in_wide?3'd4:3'd1,weight_count=weight_wide?3'd4:3'd1;
 wire [31:0] pixel_input_step=stride_two?(ci<<1):ci;
 wire [31:0] row_input_step=stride_two?(input_row_bytes<<1):input_row_bytes;
 wire [31:0] output_pixel_step=co<<2;
 wire has_next_load=load_lane==0?(tile_w==2 || tile_h==2):load_lane==1?tile_h==2:load_lane==2?tile_w==2:0;
 wire [1:0] next_load=load_lane==0 && tile_w==1?2:load_lane+1'b1;
 wire has_next_store=store_lane==0?(tile_w==2 || tile_h==2):store_lane==1?tile_h==2:store_lane==2?tile_w==2:0;
 wire [1:0] next_store=store_lane==0 && tile_w==1?2:store_lane+1'b1;
 assign busy=state!=IDLE && state!=FINISH && state!=FAIL;
 assign done=state==FINISH;assign error=state==FAIL;assign phase=state;
 assign valid=bus_valid && !clear;
 assign write=bus_kind==OUTPUT_WRITE;
 assign byte_access=bus_byte;
 assign mac_fire=!clear && state==MAC_RUN && product_valid;
 always_comb begin
  addr=bus_addr;wdata=bus_data;
  mul_value=mul_acc+(mul_rhs[0]?mul_lhs:64'd0);
  lane_mask=0;live_lanes=0;
  for(integer p=0;p<4;p++)begin
   lane_mask[p]=(p%2<tile_w && p/2<tile_h);
   live_lanes=live_lanes+{2'b0,lane_mask[p]};
   products[p]=$signed({1'b0,input_q[p][pipe_offset*8+:8]}) * $signed(weight_q[compute_bank][pipe_offset*8+:8]);
  end
 end
 // Independent banks give four synchronous pixel reads without a 4-port RAM.
 for(genvar p=0;p<4;p++)begin:pixel_banks
  (* ram_style="block" *) logic [31:0] pixels[WORDS];
  always_ff @(posedge clk)if(!clear)begin
   if(input_response && load_lane==p)begin
    // Constant byte slices infer a byte-enable RAM, not 32 one-bit RAMs.
    for(integer b=0;b<4;b++)if(in_wide || load_c[1:0]==b)
     pixels[load_c>>2][b*8+:8]<=in_wide?rdata[b*8+:8]:rdata[7:0];
   end
   if(state==MAC_RUN && issue_c<ci && lane_mask[p])input_q[p]<=pixels[issue_c>>2];
  end
 end
 for(genvar bank=0;bank<2;bank++)begin:weight_banks
  (* ram_style="block" *) logic [31:0] weights[WORDS];
  always_ff @(posedge clk)if(!clear)begin
   if(weight_response && fill_bank==bank)
    for(integer b=0;b<4;b++)if(weight_wide || weight_c[1:0]==b)
     weights[weight_c>>2][b*8+:8]<=weight_wide?rdata[b*8+:8]:rdata[7:0];
   if(state==MAC_RUN && issue_c<ci && compute_bank==bank)weight_q[bank]<=weights[issue_c>>2];
  end
 end
 // Entries include absolute addresses. Keep the head until the write response,
 // so done cannot precede an acknowledged SRAM write.
 always_ff @(posedge clk)if(push)begin
  out_addr[q_write]<=output_addr;out_data[q_write]<=sums[store_lane];
 end
 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin q_read<=0;q_write<=0;q_count<=0;end
  else if(clear)begin q_read<=0;q_write<=0;q_count<=0;end
  else begin
   if(push)q_write<=q_write+1'b1;
   if(output_response)q_read<=q_read+1'b1;
   case({push,output_response})
    2'b10:q_count<=q_count+1'b1;
    2'b01:q_count<=q_count-1'b1;
    default:;
   endcase
  end
 end
 // Offer directly while idle; lock the selected request on backpressure.
 // Keep the accepted metadata through its response, including byte enables.
 always_comb begin
  offer_valid=0;offer_kind=INPUT_READ;offer_addr=0;offer_data=0;offer_byte=0;
  if(state==IREQ)begin
   offer_valid=1;offer_kind=INPUT_READ;offer_addr=load_addr;offer_byte=!in_wide;
  end else if(q_count!=0 && (q_count>=4 || !fill_active || prefer_write))begin
   offer_valid=1;offer_kind=OUTPUT_WRITE;offer_addr=out_addr[q_read];offer_data=out_data[q_read];
  end else if(fill_active)begin
   offer_valid=1;offer_kind=WEIGHT_READ;offer_addr=weight_addr;offer_byte=!weight_wide;
  end
  bus_valid=!bus_pending && (held || offer_valid);
  bus_kind=(held || bus_pending)?held_kind:offer_kind;
  bus_addr=(held || bus_pending)?held_addr:offer_addr;
  bus_data=(held || bus_pending)?held_data:offer_data;
  bus_byte=(held || bus_pending)?held_byte:offer_byte;
 end
 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin bus_pending<=0;held<=0;prefer_write<=0;held_kind<=INPUT_READ;held_byte<=0;held_addr<=0;held_data<=0;end
  else if(clear)begin bus_pending<=0;held<=0;prefer_write<=0;end
  else begin
   if(bus_valid)begin
    held_kind<=bus_kind;held_addr<=bus_addr;held_data<=bus_data;held_byte<=bus_byte;
    held<=!ready;
   end
   if(accept)bus_pending<=1;
   if(complete)begin bus_pending<=0;held<=0;prefer_write<=bus_kind!=OUTPUT_WRITE;end
  end
 end
 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin state<=IDLE;pipe_valid<=0;product_valid<=0;fill_active<=0;weight_loaded<=0;input_reads<=0;weight_reads<=0;mac_count<=0;end
  else if(clear)begin state<=IDLE;pipe_valid<=0;product_valid<=0;fill_active<=0;weight_loaded<=0;input_reads<=0;weight_reads<=0;mac_count<=0;end
  else begin
   if(weight_response)begin
    weight_reads<=weight_reads+weight_count;
    if(weight_c+weight_count<ci)begin weight_c<=weight_c+weight_count;weight_addr<=weight_addr+weight_count;end
    else begin fill_active<=0;weight_loaded[fill_bank]<=1;end
   end
   case(state)
   IDLE:if(start)begin
    ib<=input_base;wb<=weight_base;ob<=output_base;ci<=in_channels;co<=out_channels;w<=width;h<=height;
    stride_two<=stride==2;ow<=((width-1)>>((stride==2)?1:0))+1;oh<=((height-1)>>((stride==2)?1:0))+1;
    input_reads<=0;weight_reads<=0;mac_count<=0;pipe_valid<=0;product_valid<=0;
    setup_step<=0;mul_bit<=0;mul_acc<=0;mul_lhs<={32'd0,width};mul_rhs<=in_channels;
    if(MAX_CHANNELS<1 || MAX_CHANNELS>65535 || depthwise || kernel!=1 ||
       width==0 || height==0 || width>65535 || height>65535 ||
       in_channels==0 || out_channels==0 || in_channels>MAX_CHANNELS || out_channels>MAX_CHANNELS ||
       (stride!=1 && stride!=2) || output_base[1:0]!=0)state<=FAIL;
    else state<=SETUP;
   end
   SETUP:begin
    if(mul_bit!=31)begin mul_acc<=mul_value;mul_lhs<=mul_lhs<<1;mul_rhs<=mul_rhs>>1;mul_bit<=mul_bit+1'b1;end
    else begin
     mul_bit<=0;mul_acc<=0;setup_step<=setup_step+1'b1;
     case(setup_step)
      0:begin input_row_bytes<=mul_value[31:0];mul_lhs<=mul_value;mul_rhs<=h;end
      1:begin input_extent<=mul_value;mul_lhs<={32'd0,ci};mul_rhs<=co;end
      2:begin weight_extent<=mul_value;mul_lhs<={32'd0,ow};mul_rhs<=co;end
      3:begin output_row_bytes<=mul_value[31:0]<<2;mul_lhs<=mul_value<<2;mul_rhs<=oh;end
      4:begin output_extent<=mul_value;state<=CHECK;end
      default:state<=FAIL;
     endcase
    end
   end
   CHECK:begin
    if(input_end>64'h100000000 || weight_end>64'h100000000 || output_end>64'h100000000 ||
       ({32'd0,ob}<input_end && {32'd0,ib}<output_end) ||
       ({32'd0,ob}<weight_end && {32'd0,wb}<output_end))state<=FAIL;
    else begin
     tile_x<=0;tile_y<=0;tile_input_base<=ib;tile_input_row_base<=ib;
     tile_output_base<=ob;tile_output_row_base<=ob;state<=TILE_BEGIN;
    end
   end
   TILE_BEGIN:begin
    tile_w<=ow-tile_x<2?1:2;tile_h<=oh-tile_y<2?1:2;
    load_lane<=0;load_c<=0;load_addr<=tile_input_base;
    oc<=0;compute_bank<=0;weight_loaded<=0;weight_channel_addr<=wb;state<=IREQ;
   end
   IREQ:if(input_response)begin
    input_reads<=input_reads+in_count;
    if(load_c+in_count<ci)begin load_c<=load_c+in_count;load_addr<=load_addr+in_count;end
    else if(has_next_load)begin
     load_lane<=next_load;load_c<=0;
     load_addr<=tile_input_base+(next_load[1]?row_input_step:0)+(next_load[0]?pixel_input_step:0);
    end else begin
     fill_active<=1;fill_bank<=0;weight_c<=0;weight_addr<=wb;state<=WREQ;
    end
   end
   WREQ:if(weight_loaded[compute_bank])begin
    weight_loaded[compute_bank]<=0;
    if(oc+1'b1<co)begin
     fill_active<=1;fill_bank<=!compute_bank;weight_c<=0;weight_addr<=weight_channel_addr+ci;
    end
    for(integer p=0;p<4;p++)sums[p]<=0;
    issue_c<=0;retire_c<=0;pipe_valid<=0;product_valid<=0;state<=MAC_RUN;
   end
   MAC_RUN:begin
    pipe_valid<=issue_c<ci;
    product_valid<=pipe_valid;
    if(issue_c<ci)begin issue_c<=issue_c+1'b1;pipe_offset<=issue_c[1:0];end
    // Registered multiply separates RAM/multiply delay from the INT32 adder.
    // Once filled, all live lanes still retire one channel every cycle.
    if(pipe_valid)for(integer p=0;p<4;p++)product_q[p]<=products[p];
    if(product_valid)begin
     for(integer p=0;p<4;p++)if(lane_mask[p])sums[p]<=sums[p]+{{15{product_q[p][16]}},product_q[p]};
     mac_count<=mac_count+live_lanes;retire_c<=retire_c+1'b1;
     if(retire_c+1'b1==ci)begin
      pipe_valid<=0;product_valid<=0;store_lane<=0;output_addr<=tile_output_base+(oc<<2);state<=OREQ;
     end
    end
   end
   OREQ:if(push)begin
    if(has_next_store)begin
     store_lane<=next_store;
     output_addr<=tile_output_base+(oc<<2)+(next_store[1]?output_row_bytes:0)+(next_store[0]?output_pixel_step:0);
    end else if(oc+1'b1<co)begin
     oc<=oc+1'b1;compute_bank<=!compute_bank;weight_channel_addr<=weight_channel_addr+ci;state<=WREQ;
    end else state<=OWAIT;
   end
   OWAIT:begin
    if(tile_x+tile_w<ow)begin
      tile_x<=tile_x+tile_w;tile_input_base<=tile_input_base+(pixel_input_step<<1);
      tile_output_base<=tile_output_base+(output_pixel_step<<1);state<=TILE_BEGIN;
     end else if(tile_y+tile_h<oh)begin
      tile_x<=0;tile_y<=tile_y+tile_h;
      tile_input_row_base<=tile_input_row_base+(row_input_step<<1);tile_input_base<=tile_input_row_base+(row_input_step<<1);
      tile_output_row_base<=tile_output_row_base+(output_row_bytes<<1);tile_output_base<=tile_output_row_base+(output_row_bytes<<1);state<=TILE_BEGIN;
    end else state<=DRAIN;
   end
   DRAIN:if(q_count==0 && !bus_valid && !bus_pending && !fill_active)state<=FINISH;
   FINISH,FAIL:state<=IDLE;
   default:state<=FAIL;
   endcase
  end
 end
endmodule
