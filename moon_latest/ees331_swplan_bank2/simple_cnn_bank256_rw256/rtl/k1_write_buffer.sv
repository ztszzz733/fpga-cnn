// Result FIFO with two 4096-word slots and an optional 2048-word slot. The producer deposits a panel in
// HWC address order, even though compute emits it channel-first. The oldest
// completed panel drains in address order. Only the panel bases travel with data.
module k1_write_buffer #(parameter integer WRITE_BITS=256, parameter bit EXTRA_SLOT=1)(
 input wire clk,rst_n,clear,
 input wire start_panel,push,publish,
 input wire [31:0] panel_base,result_addr,result_word,
 input wire [12:0] panel_count,
 output wire can_start,small_slot,empty,
 output wire valid,wide,
 output wire [31:0] addr,
 output wire [WRITE_BITS-1:0] data,
 input wire completed
);
 localparam integer SLOTS=EXTRA_SLOT?3:2;
 localparam integer SLOT_BITS=$clog2(SLOTS);
 logic [SLOTS-1:0] full;
 logic [SLOT_BITS-1:0] producer,order_write,order_read;
 logic [SLOT_BITS-1:0] order[SLOTS];
 wire [SLOT_BITS-1:0] consumer=order[order_read];
 logic [31:0] base[SLOTS],head_addr;
 logic [12:0] count[SLOTS],left;
 wire small_read=EXTRA_SLOT && consumer==SLOT_BITS'(2);
 // Keep full-sized panels whenever either large slot is free.
 assign small_slot=EXTRA_SLOT && (&full[1:0]);
 wire [SLOT_BITS-1:0] next_producer=small_slot?SLOT_BITS'(2):SLOT_BITS'(full[0]);
 wire small_write=EXTRA_SLOT && producer==SLOT_BITS'(2);
 function automatic [SLOT_BITS-1:0] next_slot(input logic [SLOT_BITS-1:0] slot);
  return slot==SLOT_BITS'(SLOTS-1)?'0:slot+1'b1;
 endfunction
 localparam integer WORDS=WRITE_BITS/32;
 localparam integer LANE_BITS=$clog2(WORDS);
 localparam integer OFFSET_BITS=LANE_BITS+2;
 localparam integer ROW_BITS=12-LANE_BITS;
 logic [ROW_BITS-1:0] row,base_row;
 typedef enum logic [1:0] {IDLE,LOAD,LOAD_HIGH,OFFER} state_t;
 state_t state;
 wire [11:0] wr_index=result_addr[13:2]-{panel_base[13:OFFSET_BITS],{LANE_BITS{1'b0}}};
 wire [LANE_BITS-1:0] head_lane=head_addr[OFFSET_BITS-1:2];
 assign can_start=!(&full);
 assign empty=full==0;
 assign valid=state==OFFER && !clear;
 assign addr=head_addr;
 assign wide=head_lane==0 && left>=WORDS;
 wire [3:0] step=wide?4'(WORDS):4'd1;
 wire [31:0] lane_word[WORDS],regular_word[WORDS],extra_word[WORDS];
 for(genvar lane=0;lane<WORDS;lane++)begin:stripe
  (* ram_style="block" *) logic [31:0] mem[0:8192/WORDS-1];
  logic [31:0] value;
  always_ff @(posedge clk)begin
   if(push && !clear && !small_write && wr_index[LANE_BITS-1:0]==LANE_BITS'(lane))
    mem[{producer[0],wr_index[11:LANE_BITS]}]<=result_word;
   if(state==LOAD && !clear && !small_read)value<=mem[{consumer[0],row}];
  end
  assign regular_word[lane]=value;
  assign lane_word[lane]=small_read?extra_word[lane]:regular_word[lane];
 end
 if(EXTRA_SLOT)begin:small_panel
  // 2048 entries split across four RAMB18-sized stripes. A 256-bit
  // offer fetches its two halves on consecutive cycles.
  localparam integer SMALL_LANES=4;
  for(genvar lane=0;lane<SMALL_LANES;lane++)begin:stripe
   (* ram_style="block" *) logic [31:0] mem[0:511];
   logic [31:0] value,low;
   wire [8:0] small_read_row=WORDS==8?{8'(row),state==LOAD_HIGH}:9'(row);
   always_ff @(posedge clk)begin
    if(push && !clear && small_write && wr_index[1:0]==2'(lane))
     mem[wr_index[10:2]]<=result_word;
    if(small_read && !clear && (state==LOAD || state==LOAD_HIGH))
     value<=mem[small_read_row];
    if(small_read && !clear && state==LOAD_HIGH)low<=value;
   end
   assign extra_word[lane]=WORDS==8?low:value;
   if(WORDS==8)assign extra_word[lane+SMALL_LANES]=value;
  end
 end else for(genvar lane=0;lane<WORDS;lane++)assign extra_word[lane]=0;
 for(genvar lane=1;lane<WORDS;lane++)begin:upper
  assign data[32*lane+:32]=lane_word[lane];
 end
 assign data[31:0]=lane_word[head_lane];
 always_ff @(posedge clk)begin
  if(!rst_n || clear)begin
   full<=0;producer<=0;order_write<=0;order_read<=0;state<=IDLE;
   left<=0;row<=0;base_row<=0;head_addr<=0;
  end else begin
   if(start_panel)producer<=next_producer;
   if(publish)begin
    full[producer]<=1;
    base[producer]<=panel_base;
    count[producer]<=panel_count;
    order[order_write]<=producer;
    order_write<=next_slot(order_write);
   end
   case(state)
    IDLE:if(!empty)begin
     head_addr<=base[consumer];
     left<=count[consumer];
     base_row<=base[consumer][13:OFFSET_BITS];
     row<=0;
     state<=LOAD;
    end
    LOAD:state<=small_read && WORDS==8?LOAD_HIGH:OFFER;
    LOAD_HIGH:state<=OFFER;
    OFFER:if(completed)begin
     if(left==13'(step))begin
      full[consumer]<=0;
      order_read<=next_slot(order_read);
      state<=IDLE;
     end else begin
      head_addr<=head_addr+(wide?32'(WRITE_BITS/8):32'd4);
      if(wide || (&head_lane))begin row<=row+1'b1;state<=LOAD;end
      left<=left-13'(step);
     end
    end
    default:state<=IDLE;
   endcase
  end
 end
`ifndef SYNTHESIS
 always_ff @(posedge clk)if(rst_n && !clear)begin
  if(start_panel)assert(can_start && !full[next_producer]);
  if(publish)assert(!full[producer] && panel_count>0 && panel_count<=(small_write?2048:4096));
  if(push)assert(!full[producer] && (result_addr-panel_base)<32'(4*panel_count));
  if(state==IDLE && !empty)assert(full[consumer]);
  if(completed)assert(valid);
  if(state!=IDLE && full[consumer])assert(row==head_addr[13:OFFSET_BITS]-base_row);
 end
`endif
endmodule

