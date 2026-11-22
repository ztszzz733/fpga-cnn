// Result FIFO with two 4096-word slots. The producer deposits a panel in
// HWC address order, even though compute emits it channel-first. The oldest
// completed panel drains in address order. Only the panel bases travel with data.
module k1_write_buffer(
 input wire clk,rst_n,clear,
 input wire push,publish,
 input wire [31:0] panel_base,result_addr,result_word,
 input wire [12:0] panel_count,
 output wire can_start,empty,
 output wire valid,wide,
 output wire [31:0] addr,
 output wire [127:0] data,
 input wire completed
);
 logic [1:0] full;
 logic producer,consumer;
 logic [31:0] base[2],head_addr;
 logic [12:0] count[2],left;
 logic [9:0] row,base_row;
 typedef enum logic [1:0] {IDLE,LOAD,OFFER} state_t;
 state_t state;
 wire [11:0] wr_index=result_addr[13:2]-{panel_base[13:4],2'b00};
 wire [1:0] head_lane=head_addr[3:2];
 assign can_start=!full[producer];
 assign empty=full==0;
 assign valid=state==OFFER && !clear;
 assign addr=head_addr;
 assign wide=head_lane==0 && left>=4;
 wire [2:0] step=wide?3'd4:3'd1;
 wire [31:0] lane_word[4];
 for(genvar lane=0;lane<4;lane++)begin:stripe
  (* ram_style="block" *) logic [31:0] mem[0:2047];
  logic [31:0] value;
  always_ff @(posedge clk)begin
   if(push && !clear && wr_index[1:0]==2'(lane))
    mem[{producer,wr_index[11:2]}]<=result_word;
   if(state==LOAD && !clear)value<=mem[{consumer,row}];
  end
  assign lane_word[lane]=value;
 end
 for(genvar lane=1;lane<4;lane++)begin:upper
  assign data[32*lane+:32]=lane_word[lane];
 end
 assign data[31:0]=lane_word[head_lane];
 always_ff @(posedge clk)begin
  if(!rst_n || clear)begin
   full<=0;producer<=0;consumer<=0;state<=IDLE;
   left<=0;row<=0;base_row<=0;head_addr<=0;
  end else begin
   if(publish)begin
    full[producer]<=1;
    base[producer]<=panel_base;
    count[producer]<=panel_count;
    producer<=!producer;
   end
   case(state)
    IDLE:if(full[consumer])begin
     head_addr<=base[consumer];
     left<=count[consumer];
     base_row<=base[consumer][13:4];
     row<=0;
     state<=LOAD;
    end
    LOAD:state<=OFFER;
    OFFER:if(completed)begin
     if(left==13'(step))begin
      full[consumer]<=0;
      consumer<=!consumer;
      state<=IDLE;
     end else begin
      head_addr<=head_addr+(wide?32'd16:32'd4);
      if(wide || head_lane==3)begin row<=row+1'b1;state<=LOAD;end
      left<=left-13'(step);
     end
    end
    default:state<=IDLE;
   endcase
  end
 end
`ifndef SYNTHESIS
 always_ff @(posedge clk)if(rst_n && !clear)begin
  if(publish)assert(can_start && panel_count>0 && panel_count<=4096);
  if(push)assert(can_start && (result_addr-panel_base)<32'(4*panel_count));
  if(completed)assert(valid);
  if(state!=IDLE && full[consumer])assert(row==head_addr[13:4]-base_row);
 end
`endif
endmodule

