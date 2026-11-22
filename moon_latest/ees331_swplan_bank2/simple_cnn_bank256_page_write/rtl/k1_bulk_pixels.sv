// Keep the original 4096-byte tile capacity. Each lane stores its own
// pixels, in eight byte stripes, so one aligned read fills all eight
// channels of one pixel in one cycle. The read returns the requested
// channel from all eight spatial lanes in parallel.
module k1_bulk_pixels #(
 parameter integer DEPTH=512, AW=$clog2(DEPTH+1)
)(
 input wire clk,we,re,
 input wire [AW-1:0] waddr,raddr,
 input wire [2:0] wlane,
 input wire [63:0] wdata,
 input wire [3:0] wbytes,
 output logic [63:0] rdata
);
 localparam ROWS=(DEPTH+7)/8;
 localparam ROW_BITS=$clog2(ROWS);
 wire [ROW_BITS-1:0] wrow=ROW_BITS'(waddr>>3);
 wire [ROW_BITS-1:0] rrow=ROW_BITS'(raddr>>3);
 wire [7:0] bytes[8][8];
 for(genvar lane=0;lane<8;lane++)begin:spatial_lane
  for(genvar stripe=0;stripe<8;stripe++)begin:channel_byte
   (* ram_style="distributed" *) logic [7:0] storage[ROWS];
   wire bulk_write=wbytes==8;
   wire word_write=wbytes==4 && waddr[2]==1'(stripe/4);
   wire byte_write=wbytes==1 && waddr[2:0]==3'(stripe);
   wire [7:0] value=bulk_write?wdata[8*stripe+:8]:
                     (word_write?wdata[8*(stripe%4)+:8]:wdata[7:0]);
   always_ff @(posedge clk)
    if(we && wlane==3'(lane) && (bulk_write || word_write || byte_write))
     storage[wrow]<=value;
   assign bytes[lane][stripe]=storage[rrow];
  end
  always_ff @(posedge clk)
   if(re)rdata[8*lane+:8]<=bytes[lane][raddr[2:0]];
 end
endmodule

