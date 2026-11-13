module pad_hwc_engine #(parameter ROW_PACKING=1)(
 input logic clk,rst_n,clear,start,
 input logic [31:0] source,destination,width,height,channels,
 input logic [7:0] zero_point,
 output wire busy,done,error,valid,write,byte_access,
 output logic [31:0] addr,wdata,
 input logic ready,response,input logic [31:0] rdata
);
wire [3:0] state;
generate if(ROW_PACKING)begin:rows
pad_rows_impl impl(.*);assign state=impl.state;
end else begin:legacy
pad_legacy_impl impl(.*);assign state=impl.state;
end endgenerate
endmodule
// Copy each interior HWC row as a contiguous segment. Word assembly handles
// different source/destination alignment without reading outside the segment.
// Aliased tensors retain the original byte/word transaction order.
module pad_rows_impl(
 input logic clk,rst_n,clear,start,
 input logic [31:0] source,destination,width,height,channels,
 input logic [7:0] zero_point,
 output wire busy,done,error,valid,write,byte_access,
 output logic [31:0] addr,wdata,
 input logic ready,response,input logic [31:0] rdata
);
 typedef enum logic [3:0] {IDLE=0,PREP=1,RREQ=2,RWAIT=3,WREQ=4,WWAIT=5,FINISH=6,FAIL=7,
                          SETUP=8,CHECK=9,SEGMENT=10,BYTE_STEP=11} state_t;
 state_t state;
 logic [31:0] src,dst,source_cursor,destination_cursor;
 logic [6:0] w,h,y;logic [9:0] c;logic [7:0] fill;
 logic [15:0] row_bytes,out_row_bytes,remaining;
 logic [31:0] input_extent,output_extent,lhs,acc;
 logic [6:0] rhs;logic [2:0] bit_count;logic [1:0] setup_step,section;
 logic aliasing,copy_segment,read_wide,direct_word,cache_valid,byte_valid;
 logic [2:0] transfer,packed_count;
 logic [31:0] packet,cache_word;logic [29:0] cache_tag;logic [7:0] byte_value;
 wire [31:0] sum_value=acc+(rhs[0]?lhs:32'd0);
 wire border_row=y==0 || y==h+1;
 wire can_write_word=destination_cursor[1:0]==0 && remaining>=4 && (!aliasing || c[1:0]==0);
 wire cache_hit=!aliasing && cache_valid && cache_tag==source_cursor[31:2];
 wire read_return=response && (state==RWAIT || (state==RREQ && ready));
 wire write_return=response && (state==WWAIT || (state==WREQ && ready));
 assign busy=state!=IDLE && state!=FINISH && state!=FAIL;
 assign done=state==FINISH;assign error=state==FAIL;
 assign valid=!clear && (state==RREQ || state==WREQ);
 assign write=state==WREQ;
 assign byte_access=state==RREQ?!read_wide:transfer!=4;
 always_comb begin
  addr=state==RREQ?(read_wide?{source_cursor[31:2],2'b00}:source_cursor):destination_cursor;
  wdata=packet;
 end
 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin state<=IDLE;cache_valid<=0;byte_valid<=0;end
  else if(clear)begin state<=IDLE;cache_valid<=0;byte_valid<=0;end
  else case(state)
   IDLE:if(start)begin
    src<=source;dst<=destination;w<=width;h<=height;c<=channels;fill<=zero_point;
    cache_valid<=0;byte_valid<=0;acc<=0;lhs<=channels;rhs<=width[6:0];bit_count<=0;setup_step<=0;
    state<=width==0 || height==0 || channels==0 || width>112 || height>112 || channels>512 ||
           (channels%4==0 && ((source|destination)&3)!=0)?FAIL:SETUP;
   end
   SETUP:begin
    if(bit_count!=6)begin acc<=sum_value;lhs<=lhs<<1;rhs<=rhs>>1;bit_count<=bit_count+1'b1;end
    else begin
     bit_count<=0;acc<=0;setup_step<=setup_step+1'b1;
     case(setup_step)
      0:begin row_bytes<=sum_value[15:0];out_row_bytes<=sum_value[15:0]+(c<<1);lhs<=sum_value;rhs<=h;end
      1:begin input_extent<=sum_value;lhs<={16'd0,out_row_bytes};rhs<=h+2;end
      2:begin output_extent<=sum_value;state<=CHECK;end
      default:state<=FAIL;
     endcase
    end
   end
   CHECK:begin
    aliasing<=({1'b0,src}<{1'b0,dst}+{1'b0,output_extent}) && ({1'b0,dst}<{1'b0,src}+{1'b0,input_extent});
    source_cursor<=src;destination_cursor<=dst;y<=0;section<=0;state<=SEGMENT;
   end
   SEGMENT:begin
    copy_segment<=!border_row && section==1;
    remaining<=border_row?out_row_bytes:(section==1?row_bytes:16'(c));
    state<=PREP;
   end
   PREP:begin
    if(remaining==0)begin
     if(border_row || section==2)begin
      if(y==h+1)state<=FINISH;
      else begin y<=y+1'b1;section<=0;state<=SEGMENT;end
     end else begin section<=section+1'b1;state<=SEGMENT;end
    end else begin
     transfer<=can_write_word?3'd4:3'd1;packet<=0;packed_count<=0;
     if(!copy_segment)begin packet<={4{fill}};state<=WREQ;end
     else if(can_write_word && source_cursor[1:0]==0)begin read_wide<=1;direct_word<=1;state<=RREQ;end
     else state<=BYTE_STEP;
    end
   end
   BYTE_STEP:begin
    if(cache_hit || byte_valid)begin
     packet[packed_count*8+:8]<=cache_hit?cache_word[source_cursor[1:0]*8+:8]:byte_value;
     source_cursor<=source_cursor+1'b1;remaining<=remaining-1'b1;byte_valid<=0;
     if(packed_count+1'b1==transfer)state<=WREQ;
     else packed_count<=packed_count+1'b1;
    end else begin
     read_wide<=!aliasing && source_cursor[1:0]==0 && remaining>=4;
     direct_word<=0;state<=RREQ;
    end
   end
   RREQ,RWAIT:begin
    if(state==RREQ && ready)state<=RWAIT;
    if(read_return)begin
     if(direct_word)begin packet<=rdata;source_cursor<=source_cursor+4;remaining<=remaining-4;state<=WREQ;end
     else begin
      if(read_wide)begin cache_valid<=1;cache_tag<=source_cursor[31:2];cache_word<=rdata;end
      else begin byte_valid<=1;byte_value<=rdata[7:0];end
      state<=BYTE_STEP;
     end
    end
   end
   WREQ,WWAIT:begin
    if(state==WREQ && ready)state<=WWAIT;
    if(write_return)begin
     destination_cursor<=destination_cursor+transfer;
     if(!copy_segment)remaining<=remaining-transfer;
     state<=PREP;
    end
   end
   FINISH,FAIL:state<=IDLE;
   default:state<=FAIL;
  endcase
 end
endmodule

// Materialize a one-pixel zero-point border around an HWC tensor.
// Packed word transfers when channels are a multiple of four, byte otherwise.
module pad_legacy_impl(
 input logic clk,rst_n,clear,start,
 input logic [31:0] source,destination,width,height,channels,
 input logic [7:0] zero_point,
 output wire busy,done,error,valid,write,byte_access,
 output logic [31:0] addr,wdata,
 input logic ready,response,input logic [31:0] rdata
);
 typedef enum logic [3:0] {IDLE,SELECT,RREQ,RWAIT,WREQ,WWAIT,FINISH,FAIL} state_t;
 state_t state;
 logic [31:0] src,dst,w,h,c,x,y,ch,value,step;
 logic [7:0] fill;
 wire border=x==0 || y==0 || x==w+1 || y==h+1;
 assign busy=state!=IDLE && state!=FINISH && state!=FAIL;
 assign done=state==FINISH;assign error=state==FAIL;
 assign valid=!clear && (state==RREQ || state==WREQ);
 assign write=state==WREQ;assign byte_access=step==1;
 always_comb begin
  addr=state==RREQ ? src+((y-1)*w+x-1)*c+ch : dst+(y*(w+2)+x)*c+ch;
  wdata=value;
 end
 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin state<=IDLE;src<=0;dst<=0;w<=0;h<=0;c<=0;x<=0;y<=0;ch<=0;value<=0;step<=1;fill<=0;end
  else if(clear)state<=IDLE;
  else case(state)
   IDLE:if(start)begin
    src<=source;dst<=destination;w<=width;h<=height;c<=channels;fill<=zero_point;x<=0;y<=0;ch<=0;
    step<=channels%4==0 ? 4:1;
    state<=width==0 || height==0 || channels==0 || width>112 || height>112 || channels>512 ||
           (channels%4==0 && ((source|destination)&3)!=0) ? FAIL:SELECT;
   end
   SELECT:if(border)begin value<={4{fill}};state<=WREQ;end else state<=RREQ;
   RREQ:if(ready)state<=RWAIT;
   RWAIT:if(response)begin value<=rdata;state<=WREQ;end
   WREQ:if(ready)state<=WWAIT;
   WWAIT:if(response)begin
    state<=SELECT;
    if(ch+step<c)ch<=ch+step;
    else begin ch<=0;if(x<w+1)x<=x+1;else begin x<=0;if(y<h+1)y<=y+1;else state<=FINISH;end end
   end
   FINISH,FAIL:state<=IDLE;
   default:state<=FAIL;
  endcase
 end
endmodule
