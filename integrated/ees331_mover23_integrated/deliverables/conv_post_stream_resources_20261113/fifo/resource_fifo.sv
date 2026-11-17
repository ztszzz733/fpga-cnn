module resource_fifo(
 input wire clk,rst_n,clear,s_valid,input wire [73:0] s_payload,
 output wire s_ready,m_valid,output wire [73:0] m_payload,input wire m_ready,output wire [3:0] level
);
 (* ram_style="registers" *) logic [31:0] data_mem[0:7],index_mem[0:7];
 (* ram_style="registers" *) logic [9:0] channel_mem[0:7];
 logic [2:0] wp,rp;logic [3:0] used;
 wire push=s_valid && s_ready,pop=m_valid && m_ready;
 assign s_ready=used<8 && !clear;assign m_valid=used!=0 && !clear;
 assign m_payload={channel_mem[rp],index_mem[rp],data_mem[rp]};assign level=used;
 always_ff @(posedge clk)if(push)begin data_mem[wp]<=s_payload[31:0];index_mem[wp]<=s_payload[63:32];channel_mem[wp]<=s_payload[73:64];end
 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin wp<=0;rp<=0;used<=0;end
  else if(clear)begin wp<=0;rp<=0;used<=0;end
  else begin
   if(push)wp<=wp+1'b1;if(pop)rp<=rp+1'b1;
   case({push,pop})2'b10:used<=used+1'b1;2'b01:used<=used-1'b1;default:;endcase
  end
 end
endmodule
