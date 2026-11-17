// One synchronous read, one byte-enabled write. Split the short tail so a
// 1152-word cache does not require two complete 36-Kbit blocks.
module compact_word_ram #(parameter integer DEPTH=128, AW=$clog2(DEPTH))(
 input wire clk,wr_en,rd_en,
 input wire [AW-1:0] wr_addr,rd_addr,
 input wire [31:0] wr_data,input wire [3:0] wr_mask,
 output wire [31:0] rd_data
);
 generate if(DEPTH>1024 && DEPTH<=1536)begin:split
  (* ram_style="block" *) logic [31:0] main_mem[0:1023];
  (* ram_style="block" *) logic [31:0] tail_mem[0:DEPTH-1025];
  logic [31:0] main_q,tail_q;logic tail_select;
  always @(posedge clk)begin
   for(integer b=0;b<4;b++)if(wr_en && wr_mask[b])begin
    if(wr_addr<1024)main_mem[wr_addr[9:0]][b*8+:8]<=wr_data[b*8+:8];
    else tail_mem[wr_addr-1024][b*8+:8]<=wr_data[b*8+:8];
   end
   if(rd_en)begin
    tail_select<=rd_addr>=1024;
    if(rd_addr<1024)main_q<=main_mem[rd_addr[9:0]];
    else tail_q<=tail_mem[rd_addr-1024];
   end
  end
  assign rd_data=tail_select?tail_q:main_q;
 end else begin:single
  (* ram_style="block" *) logic [31:0] mem[0:DEPTH-1];
  logic [31:0] value;
  always @(posedge clk)begin
   for(integer b=0;b<4;b++)if(wr_en && wr_mask[b])mem[wr_addr][b*8+:8]<=wr_data[b*8+:8];
   if(rd_en)value<=mem[rd_addr];
  end
  assign rd_data=value;
 end endgenerate
endmodule
