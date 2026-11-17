// Actual four-bank RAM; one 32-bit access per clock, in-order fixed-latency
// responses. Both baseline and prefetch use precisely this same frontend.
module pipeline_bank #(parameter BYTES=401408,LATENCY=2)(
 input logic clk,rst_n,clear,stall,
 input wire valid,write,byte_access,input wire [31:0] addr,wdata,
 output wire ready,response,output wire [31:0] rdata,
 output wire idle,output logic fault,
 output logic [31:0] write_commands,write_completions,write_service_cycles,read_commands,write_commits,
 output wire commit_valid,output wire [31:0] commit_addr,commit_data,
 input wire dma_valid,dma_write,input wire [31:0] dma_addr,dma_wdata,
 input wire [3:0] dma_wstrb,output wire dma_ready,dma_rsp_valid,dma_error,output wire [31:0] dma_rdata
);
 wire [31:0] aligned={addr[31:2],2'b00};
 wire [1:0] bank=addr<98304?0:addr<196608?1:addr<299008?2:3;
 wire bad=addr>=BYTES || (!byte_access && (addr[1:0]!=0 || {1'b0,addr}+33'd4>BYTES));
 assign ready=rst_n && !clear && !fault && !stall;
 wire take=valid && ready;
 wire [3:0] comp_req,comp_we;wire [3:0][31:0] comp_addr,comp_wdata,comp_rdata;
 wire [3:0][3:0] comp_wstrb;wire [3:0] comp_error;
 wire [31:0] shifted=byte_access?({24'd0,wdata[7:0]}<<(addr[1:0]*8)):wdata;
 for(genvar b=0;b<4;b++)begin
  assign comp_req[b]=take && !bad && bank==2'(b);
  assign comp_we[b]=write;assign comp_addr[b]=aligned;assign comp_wdata[b]=shifted;
  assign comp_wstrb[b]=byte_access?(4'b1<<addr[1:0]):4'hf;
 end
 tile_local_ram_bank4 #(.BYTES(BYTES)) memory(
  .clk,.rst_n(rst_n && !clear),.comp_req,.comp_we,.comp_addr,.comp_wdata,.comp_wstrb,.comp_rdata,.comp_error,
  .dma_valid,.dma_write,.dma_ready,.dma_addr,.dma_wdata,.dma_wstrb,.dma_rsp_valid,.dma_error,.dma_rdata);
 logic [LATENCY-1:0] v,wr,byt;logic [1:0] banks[LATENCY],lanes[LATENCY];logic [31:0] data[LATENCY];
 assign response=v[LATENCY-1] && !clear;
 assign rdata=data[LATENCY-1];assign idle=!(|v);
 assign commit_valid=take && write && !bad;assign commit_addr=aligned;assign commit_data=shifted;
 wire write_service=take && write || |(v & wr);
 always_ff @(posedge clk)begin
  if(!rst_n || clear)begin
   v<=0;wr<=0;byt<=0;fault<=0;write_commands<=0;write_completions<=0;write_service_cycles<=0;read_commands<=0;write_commits<=0;
   for(integer j=0;j<LATENCY;j++)begin banks[j]<=0;lanes[j]<=0;data[j]<=0;end
  end else begin
   v[0]<=take;wr[0]<=write;byt[0]<=byte_access;banks[0]<=bank;lanes[0]<=addr[1:0];
   for(integer j=1;j<LATENCY;j++)begin
    v[j]<=v[j-1];wr[j]<=wr[j-1];byt[j]<=byt[j-1];banks[j]<=banks[j-1];lanes[j]<=lanes[j-1];
    if(j==1)data[j]<=wr[0]?0:byt[0]?{{24{comp_rdata[banks[0]][lanes[0]*8+7]}},comp_rdata[banks[0]][lanes[0]*8+:8]}:comp_rdata[banks[0]];
    else data[j]<=data[j-1];
   end
   if(take)begin if(bad)fault<=1;if(write)write_commands<=write_commands+1;else read_commands<=read_commands+1;end
   if(response && wr[LATENCY-1])write_completions<=write_completions+1;
   if(write_service)write_service_cycles<=write_service_cycles+1;
   if(commit_valid)write_commits<=write_commits+1;
   if(|comp_error)fault<=1;
  end
 end
endmodule
