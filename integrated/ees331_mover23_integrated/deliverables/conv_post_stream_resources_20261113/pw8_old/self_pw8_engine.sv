// Eight spatial lanes for ordinary 1x1 UINT8 x INT8 -> raw INT32.
// HWC / OHWI, 4x2 output tile. Each input pixel has its own synchronous RAM.
// One cached weight is broadcast to all live pixels; local sums wrap to INT32.
// Aligned groups use 32-bit reads; unaligned starts/tails use exact byte reads.
// Double-buffered weights and an eight-word write FIFO overlap local MACs.
// One outstanding external transaction; clear requires fabric cancellation too.
module self_pw8_engine #(parameter MAX_CHANNELS=512, INPUT_PREFETCH=1, WEIGHT_LAYER_REUSE=1, PANEL_REUSE=1, ADDR_REGS=1)(
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
 logic [2:0] load_lane,store_lane;
 // A panel holds several existing 4x2 microtiles in the same pixel RAM.
 // Each microtile consumes ci channel rows; no input byte is loaded twice.
 logic [3:0] panel_w,panel_h;
 logic [2:0] load_slot,compute_slot;
 logic [C_BITS-1:0] load_cache_base,compute_cache_base;
 logic panel_enabled;
 wire [3:0] panel_limit_w=panel_enabled?4'd8:4'd4;
 wire [3:0] panel_limit_h=!panel_enabled?4'd2:(ci<=MAX_CHANNELS/8?4'd8:(ci<=MAX_CHANNELS/4?4'd4:4'd2));
 wire two_columns=panel_w>4;
 wire [3:0] panel_rows=(panel_h+1'b1)>>1;
 wire [3:0] panel_slots=two_columns?(panel_rows<<1):panel_rows;
 wire [2:0] active_slot=state==IREQ?load_slot:compute_slot;
 wire active_right=two_columns && active_slot[0];
 wire [1:0] active_row=two_columns?active_slot[2:1]:active_slot[1:0];
 wire [2:0] tile_w=active_right?3'(panel_w-4):(panel_w>4?3'd4:panel_w[2:0]);
 wire [1:0] tile_h=(panel_h-{1'b0,active_row,1'b0})>=2?2'd2:2'd1;
 wire [1:0] load_row=two_columns?load_slot[2:1]:load_slot[1:0];
 wire [1:0] compute_row=two_columns?compute_slot[2:1]:compute_slot[1:0];
 wire [31:0] load_tile_base_comb=tile_input_base+
  ((two_columns && load_slot[0])?(pixel_input_step<<2):32'd0)+
  (load_row[0]?(row_input_step<<1):32'd0)+(load_row[1]?(row_input_step<<2):32'd0);
 wire [31:0] compute_tile_base_comb=tile_output_base+
  ((two_columns && compute_slot[0])?(output_pixel_step<<2):32'd0)+
  (compute_row[0]?(output_row_bytes<<1):32'd0)+(compute_row[1]?(output_row_bytes<<2):32'd0);
 wire [2:0] next_load_slot=load_slot+1'b1;
 wire [1:0] next_load_row=two_columns?next_load_slot[2:1]:next_load_slot[1:0];
 wire [31:0] next_load_base_comb=tile_input_base+
  ((two_columns && next_load_slot[0])?(pixel_input_step<<2):32'd0)+
  (next_load_row[0]?(row_input_step<<1):32'd0)+(next_load_row[1]?(row_input_step<<2):32'd0);
 // Runtime microtile origins are pointers. Each change uses one row/column
 // increment rather than decoding slot -> row/column -> several 32-bit sums.
 logic [31:0] load_origin,load_row_origin,store_origin,store_row_origin;
 wire load_next_column=two_columns && !load_slot[0];
 wire store_next_column=two_columns && !compute_slot[0];
 wire [31:0] load_origin_next=load_next_column?
  load_origin+(pixel_input_step<<2):load_row_origin+(row_input_step<<1);
 wire [31:0] store_origin_next=store_next_column?
  store_origin+(output_pixel_step<<2):store_row_origin+(output_row_bytes<<1);
 wire [31:0] load_tile_base=ADDR_REGS?load_origin:load_tile_base_comb;
 wire [31:0] compute_tile_base=ADDR_REGS?store_origin:compute_tile_base_comb;
 wire [31:0] next_load_base=ADDR_REGS?load_origin_next:next_load_base_comb;
 wire [31:0] panel_input_x_step=panel_limit_w==8?(pixel_input_step<<3):(pixel_input_step<<2);
 wire [31:0] panel_output_x_step=panel_limit_w==8?(output_pixel_step<<3):(output_pixel_step<<2);
 wire [31:0] panel_input_y_step=panel_limit_h==8?(row_input_step<<3):(panel_limit_h==4?(row_input_step<<2):(row_input_step<<1));
 wire [31:0] panel_output_y_step=panel_limit_h==8?(output_row_bytes<<3):(panel_limit_h==4?(output_row_bytes<<2):(output_row_bytes<<1));
 logic [31:0] load_addr,weight_addr,weight_channel_addr,output_addr;
 localparam WBITS=$clog2(8*WORDS+1);
 logic [C_BITS-1:0] load_c,issue_c,retire_c;
 logic [WBITS-1:0] weight_c,cache_channel;
 logic layer_valid;
 logic layer_cached;
 // Descriptor choices settle before any memory request. Keep wide extent
 // comparisons and final-beat arithmetic off the runtime handshake path.
 wire layer_cached_choice=WEIGHT_LAYER_REUSE && (ow>panel_limit_w || oh>panel_limit_h) && weight_extent<=8*WORDS;
 wire [WBITS-1:0] weight_target_choice=layer_cached_choice?weight_extent[WBITS-1:0]:WBITS'(ci);
 logic [WBITS-1:0] weight_last_byte,weight_last_word;
 logic [WBITS-3:0] weight_full_words;
 wire [WBITS-1:0] read_weight_index=(layer_cached?cache_channel:WBITS'(compute_bank?4*WORDS:0))+WBITS'(issue_c);
 logic pipe_valid,product_valid;logic [1:0] pipe_offset;
 logic [63:0] pixel_q;logic [31:0] weight_word_q;
 logic [31:0] input_fill_word;logic [2:0] input_fill_left,input_fill_lane;logic [C_BITS-1:0] input_fill_c;
 logic prefetch_valid;
 logic [31:0] prefetch_word;
 logic [2:0] prefetch_count,prefetch_lane;
 logic [C_BITS-1:0] prefetch_c;
 wire promote_prefetch=prefetch_valid && input_fill_left<=1;
 logic signed [31:0] sums[8];
 logic signed [16:0] products[8];
 logic signed [16:0] product_q[8];
 logic [7:0] lane_mask;
 logic [3:0] live_lanes;
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
 wire weight_wide=weight_addr[1:0]==0 && weight_c[1:0]==0 && (weight_c>>2)<weight_full_words;
 wire [2:0] in_count=in_wide?3'd4:3'd1,weight_count=weight_wide?3'd4:3'd1;
 wire [31:0] pixel_input_step=stride_two?(ci<<1):ci;
 wire [31:0] row_input_step=stride_two?(input_row_bytes<<1):input_row_bytes;
 wire [31:0] output_pixel_step=co<<2;
 wire has_next_load=(load_lane[1:0]+1<tile_w) || (!load_lane[2] && tile_h==2);
 wire [2:0] next_load=(load_lane[1:0]+1<tile_w)?load_lane+1'b1:3'd4;
 wire has_next_store=(store_lane[1:0]+1<tile_w) || (!store_lane[2] && tile_h==2);
 wire [2:0] next_store=(store_lane[1:0]+1<tile_w)?store_lane+1'b1:3'd4;
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
  for(integer p=0;p<8;p++)begin
   lane_mask[p]=(p%4<tile_w && p/4<tile_h);
   live_lanes=live_lanes+{2'b0,lane_mask[p]};
   products[p]=$signed({1'b0,pixel_q[p*8+:8]}) * $signed(weight_word_q[pipe_offset*8+:8]);
  end
 end
 // Packed channel rows supply all eight pixel bytes with one 64-bit read.
 // Incoming 32-bit words are committed over at most four local cycles.
 for(genvar p=0;p<8;p++)begin:pixel_banks
  // Kept only as a constant byte-enable selector, not a separate RAM.
 end
 (* ram_style="block" *) logic [63:0] pixels[0:MAX_CHANNELS-1];
 always @(posedge clk)if(!clear)begin
  for(integer p=0;p<8;p++)if(input_fill_left!=0 && input_fill_lane==p)
   pixels[input_fill_c][p*8+:8]<=input_fill_word[7:0];
  if(state==MAC_RUN && issue_c<ci)pixel_q<=pixels[compute_cache_base+issue_c];
 end
 // One skid word lets external reads proceed while bytes drain into pixel RAM.
 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin input_fill_left<=0;input_fill_word<=0;input_fill_c<=0;input_fill_lane<=0;
   prefetch_valid<=0;prefetch_word<=0;prefetch_count<=0;prefetch_lane<=0;prefetch_c<=0;end
  else if(clear || (state==IDLE && start))begin input_fill_left<=0;prefetch_valid<=0;end
  else begin
   if(input_fill_left!=0)begin
    input_fill_word<=input_fill_word>>8;input_fill_left<=input_fill_left-1'b1;input_fill_c<=input_fill_c+1'b1;
   end
   if(promote_prefetch)begin
    input_fill_word<=prefetch_word;input_fill_left<=prefetch_count;input_fill_c<=prefetch_c;input_fill_lane<=prefetch_lane;prefetch_valid<=0;
   end
   if(input_response)begin
    if(input_fill_left<=1 && !prefetch_valid)begin
     input_fill_word<=rdata;input_fill_left<=in_count;input_fill_c<=load_cache_base+load_c;input_fill_lane<=load_lane;
    end else begin
     prefetch_valid<=1;prefetch_word<=rdata;prefetch_count<=in_count;prefetch_c<=load_cache_base+load_c;prefetch_lane<=load_lane;
    end
   end
  end
 end
 wire [3:0] weight_mask=weight_wide?4'hf:(4'b1<<weight_c[1:0]);
 compact_word_ram #(.DEPTH(2*WORDS)) weights(
  .clk(clk),.wr_en(weight_response && !clear),.rd_en(state==MAC_RUN && issue_c<ci && !clear),
  .wr_addr($clog2(2*WORDS)'((layer_cached?0:(fill_bank?WORDS:0))+(weight_c>>2))),
  .rd_addr($clog2(2*WORDS)'(read_weight_index>>2)),
  .wr_data(weight_wide?rdata:{4{rdata[7:0]}}),.wr_mask(weight_mask),.rd_data(weight_word_q));
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
  if(state==IREQ && (INPUT_PREFETCH?(!prefetch_valid || promote_prefetch):(input_fill_left==0)))begin
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
  if(!rst_n)begin state<=IDLE;pipe_valid<=0;product_valid<=0;fill_active<=0;weight_loaded<=0;panel_enabled<=0;layer_cached<=0;layer_valid<=0;input_reads<=0;weight_reads<=0;mac_count<=0;end
  else if(clear)begin state<=IDLE;pipe_valid<=0;product_valid<=0;fill_active<=0;weight_loaded<=0;panel_enabled<=0;layer_cached<=0;layer_valid<=0;input_reads<=0;weight_reads<=0;mac_count<=0;end
  else begin
   if(weight_response)begin
    weight_reads<=weight_reads+weight_count;
    if(weight_wide?(weight_c!=weight_last_word):(weight_c!=weight_last_byte))begin weight_c<=weight_c+weight_count;weight_addr<=weight_addr+weight_count;end
    else begin fill_active<=0;if(layer_cached)layer_valid<=1;else weight_loaded[fill_bank]<=1;end
   end
   case(state)
   IDLE:if(start)begin
    ib<=input_base;wb<=weight_base;ob<=output_base;ci<=in_channels;co<=out_channels;w<=width;h<=height;
    stride_two<=stride==2;ow<=((width-1)>>((stride==2)?1:0))+1;oh<=((height-1)>>((stride==2)?1:0))+1;
    panel_enabled<=0;layer_cached<=0;layer_valid<=0;input_reads<=0;weight_reads<=0;mac_count<=0;pipe_valid<=0;product_valid<=0;
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
      2:begin weight_extent<=mul_value;panel_enabled<=PANEL_REUSE && mul_value>8*WORDS && ci<=MAX_CHANNELS/2;mul_lhs<={32'd0,ow};mul_rhs<=co;end
      3:begin output_row_bytes<=mul_value[31:0]<<2;mul_lhs<=mul_value<<2;mul_rhs<=oh;end
      4:begin output_extent<=mul_value;state<=CHECK;end
      default:state<=FAIL;
     endcase
    end
   end
   CHECK:begin
    layer_cached<=layer_cached_choice;
    weight_last_byte<=weight_target_choice-1'b1;weight_last_word<=weight_target_choice-4;
    weight_full_words<=weight_target_choice>>2;
    if(input_end>64'h100000000 || weight_end>64'h100000000 || output_end>64'h100000000 ||
       ({32'd0,ob}<input_end && {32'd0,ib}<output_end) ||
       ({32'd0,ob}<weight_end && {32'd0,wb}<output_end))state<=FAIL;
    else begin
     tile_x<=0;tile_y<=0;tile_input_base<=ib;tile_input_row_base<=ib;
     tile_output_base<=ob;tile_output_row_base<=ob;state<=TILE_BEGIN;
    end
   end
   TILE_BEGIN:begin
    panel_w<=ow-tile_x<panel_limit_w?4'(ow-tile_x):panel_limit_w;
    panel_h<=oh-tile_y<panel_limit_h?4'(oh-tile_y):panel_limit_h;
    load_slot<=0;compute_slot<=0;load_cache_base<=0;compute_cache_base<=0;
    load_origin<=tile_input_base;load_row_origin<=tile_input_base;
    store_origin<=tile_output_base;store_row_origin<=tile_output_base;
    load_lane<=0;load_c<=0;load_addr<=tile_input_base;
    oc<=0;cache_channel<=0;compute_bank<=0;weight_loaded<=0;weight_channel_addr<=wb;state<=IREQ;
   end
   IREQ:if(input_response)begin
    input_reads<=input_reads+in_count;
    if(load_c+in_count<ci)begin load_c<=load_c+in_count;load_addr<=load_addr+in_count;end
    else if(has_next_load)begin
     load_lane<=next_load;load_c<=0;
     load_addr<=load_tile_base+(next_load[2]?row_input_step:0)+(next_load[1:0]*pixel_input_step);
    end else if({1'b0,load_slot}+1'b1<panel_slots)begin
     load_slot<=next_load_slot;load_cache_base<=load_cache_base+ci;
     load_origin<=load_origin_next;
     if(!load_next_column)load_row_origin<=load_origin_next;
     load_lane<=0;load_c<=0;load_addr<=next_load_base;
    end else begin
     if(!layer_cached || !layer_valid)begin fill_active<=1;fill_bank<=0;weight_c<=0;weight_addr<=wb;end
     state<=WREQ;
    end
   end
   WREQ:if((layer_cached?layer_valid:weight_loaded[compute_bank]) && input_fill_left==0 && !prefetch_valid)begin
    weight_loaded[compute_bank]<=0;
    if(!layer_cached && oc+1'b1<co)begin
     fill_active<=1;fill_bank<=!compute_bank;weight_c<=0;weight_addr<=weight_channel_addr+ci;
    end
    for(integer p=0;p<8;p++)sums[p]<=0;
    issue_c<=0;retire_c<=0;pipe_valid<=0;product_valid<=0;state<=MAC_RUN;
   end
   MAC_RUN:begin
    pipe_valid<=issue_c<ci;
    product_valid<=pipe_valid;
    if(issue_c<ci)begin issue_c<=issue_c+1'b1;pipe_offset<=read_weight_index[1:0];end
    // Registered multiply separates RAM/multiply delay from the INT32 adder.
    // Once filled, all live lanes still retire one channel every cycle.
    if(pipe_valid)for(integer p=0;p<8;p++)product_q[p]<=products[p];
    if(product_valid)begin
     for(integer p=0;p<8;p++)if(lane_mask[p])sums[p]<=sums[p]+{{15{product_q[p][16]}},product_q[p]};
     mac_count<=mac_count+live_lanes;retire_c<=retire_c+1'b1;
     if(retire_c+1'b1==ci)begin
      pipe_valid<=0;product_valid<=0;store_lane<=0;output_addr<=compute_tile_base+(oc<<2);state<=OREQ;
     end
    end
   end
   OREQ:if(push)begin
    if(has_next_store)begin
     store_lane<=next_store;
     output_addr<=compute_tile_base+(oc<<2)+(next_store[2]?output_row_bytes:0)+(next_store[1:0]*output_pixel_step);
    end else if({1'b0,compute_slot}+1'b1<panel_slots)begin
     compute_slot<=compute_slot+1'b1;compute_cache_base<=compute_cache_base+ci;
     store_origin<=store_origin_next;
     if(!store_next_column)store_row_origin<=store_origin_next;
     for(integer p=0;p<8;p++)sums[p]<=0;
     issue_c<=0;retire_c<=0;pipe_valid<=0;product_valid<=0;state<=MAC_RUN;
    end else if(oc+1'b1<co)begin
     compute_slot<=0;compute_cache_base<=0;
     store_origin<=tile_output_base;store_row_origin<=tile_output_base;
     oc<=oc+1'b1;cache_channel<=cache_channel+ci;compute_bank<=!compute_bank;weight_channel_addr<=weight_channel_addr+ci;state<=WREQ;
    end else state<=OWAIT;
   end
   OWAIT:begin
    if(tile_x+panel_w<ow)begin
      tile_x<=tile_x+panel_w;tile_input_base<=tile_input_base+panel_input_x_step;
      tile_output_base<=tile_output_base+panel_output_x_step;state<=TILE_BEGIN;
     end else if(tile_y+panel_h<oh)begin
      tile_x<=0;tile_y<=tile_y+panel_h;
      tile_input_row_base<=tile_input_row_base+panel_input_y_step;tile_input_base<=tile_input_row_base+panel_input_y_step;
      tile_output_row_base<=tile_output_row_base+panel_output_y_step;tile_output_base<=tile_output_row_base+panel_output_y_step;state<=TILE_BEGIN;
    end else state<=DRAIN;
   end
   DRAIN:if(q_count==0 && !bus_valid && !bus_pending && !fill_active)state<=FINISH;
   FINISH,FAIL:state<=IDLE;
   default:state<=FAIL;
   endcase
  end
 end
endmodule
