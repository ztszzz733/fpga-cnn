// The K3 core emits a channel for every live pixel before advancing.
module k3_result_packer(
 input wire clk,rst_n,clear,input_valid,
 input wire [64:0] item,
 output wire pop,
 input wire launch,completed,
 output wire empty,valid,wide,
 output wire [31:0] addr,
 output wire [255:0] data
);
 wire packable=item[64];
 wire [1:0] pixel=item[63:62];
 wire [29:0] word_address=item[61:32];
 wire [2:0] word_index=word_address[2:0];
 wire [31:0] word_data=item[31:0];

 logic scalar_full;
 logic [29:0] scalar_addr;
 logic [31:0] scalar_data;
 logic [3:0] partial,complete;
 logic [26:0] line_addr[4];
 logic [1:0] selected,issued_pixel;
 logic issued_scalar;
 wire [255:0] line_data;
 always_comb begin
  selected=0;
  for(integer p=3;p>=0;p--)if(complete[p])selected=2'(p);
 end
 assign pop=input_valid && !clear && (packable ? !complete[pixel] : !scalar_full);
 assign empty=!(|partial) && !(|complete) && !scalar_full;
 assign valid=!clear && (scalar_full || (|complete));
 assign wide=!scalar_full;
 assign addr=scalar_full?{scalar_addr,2'b00}:{line_addr[selected],5'b00000};
 assign data=scalar_full?{224'd0,scalar_data}:line_data;

 for(genvar i=0;i<8;i++)begin:columns
  (* ram_style="distributed" *) logic [31:0] words[4];
  always_ff @(posedge clk)
   if(pop && packable && word_index==3'(i))words[pixel]<=word_data;
  assign line_data[32*i+:32]=words[selected];
 end
 always_ff @(posedge clk)begin
  if(!rst_n || clear)begin
   scalar_full<=0;partial<=0;complete<=0;issued_scalar<=0;issued_pixel<=0;
  end else begin
   if(pop)begin
    if(packable)begin
     if(word_index==0)begin
      line_addr[pixel]<=word_address[29:3];
      partial[pixel]<=1;
     end
     if(word_index==7)begin
      partial[pixel]<=0;
      complete[pixel]<=1;
     end
    end else begin
     scalar_full<=1;
     scalar_addr<=word_address;
     scalar_data<=word_data;
    end
   end
   if(launch)begin
    issued_scalar<=scalar_full;
    issued_pixel<=selected;
   end
   if(completed)begin
    if(issued_scalar)scalar_full<=0;
    else complete[issued_pixel]<=0;
   end
  end
 end
`ifndef SYNTHESIS
 logic [2:0] expected_word[4];
 always_ff @(posedge clk)if(rst_n && !clear)begin
  if(launch)assert(valid)else $fatal(1,"empty K3 write launch");
  if(completed)assert(issued_scalar?scalar_full:complete[issued_pixel])
    else $fatal(1,"K3 write completion lost its buffered payload");
  if(pop && packable)begin
   if(word_index==0)begin
    assert(!partial[pixel])else $fatal(1,"overlapping K3 lines");
   end else begin
    assert(partial[pixel] && line_addr[pixel]==word_address[29:3] && expected_word[pixel]==word_index)
     else $fatal(1,"nonconsecutive K3 packed line");
   end
   expected_word[pixel]<=word_index+1'b1;
  end
 end
`endif
endmodule

