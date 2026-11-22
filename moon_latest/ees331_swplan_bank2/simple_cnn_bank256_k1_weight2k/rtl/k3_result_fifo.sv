// One result enters and leaves per clock. The head remains stable until pop.
module k3_result_fifo #(parameter integer ITEM_BITS=64)(
 input wire clk,rst_n,clear,push,pop,
 input wire [ITEM_BITS-1:0] item,
 output wire space,empty,valid,
 output logic [ITEM_BITS-1:0] head
);
 (* ram_style="block" *) logic [ITEM_BITS-1:0] mem[0:1023];
 logic [9:0] tail,rd;
 logic [10:0] count;
 logic head_valid;
 wire add=push && space;
 wire take=valid && pop;
 assign space=count<1024 && !clear;
 assign empty=count==0;
 assign valid=head_valid && !clear;
 always_ff @(posedge clk)begin
  if(add)mem[tail]<=item;
  if(!head_valid && count!=0 && !clear)head<=mem[rd];
  if(!rst_n || clear)begin
   tail<=0;rd<=0;count<=0;head_valid<=0;
  end else begin
   if(add)tail<=tail+1'b1;
   if(take)begin rd<=rd+1'b1;head_valid<=0;end
   else if(count!=0)head_valid<=1;
   case({add,take})
    2'b10:count<=count+1'b1;
    2'b01:count<=count-1'b1;
    default:;
   endcase
  end
 end
endmodule

