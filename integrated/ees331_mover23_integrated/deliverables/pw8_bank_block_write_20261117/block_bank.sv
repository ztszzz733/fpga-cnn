// One 32-bit compute write/read per clock, independent of frontend protocol.
// No DDR exists here. DMA is used only for untimed fixture preload/readback.
module block_bank #(parameter BYTES=401408)(
 input logic clk,rst_n,clear,stall,
 input wire mem_valid,mem_write,mem_byte,
 input wire [31:0] mem_addr,mem_wdata,
 output wire mem_ready,output logic mem_response,
 output logic [31:0] mem_rdata,
 input wire block_valid,output wire block_ready,
 input wire [31:0] block_base,block_stride,
 input wire [3:0] block_words,
 input wire block_data_valid,output wire block_data_ready,
 input wire [31:0] block_data,
 output logic block_response,block_response_error,
 output wire idle,output logic fault,
 output logic [31:0] write_commands,write_completions,write_service_cycles,read_commands,write_commits,
 output wire commit_valid,output wire [31:0] commit_addr,commit_data,
 input wire dma_valid,dma_write,input wire [31:0] dma_addr,dma_wdata,
 input wire [3:0] dma_wstrb,
 output wire dma_ready,dma_rsp_valid,dma_error,output wire [31:0] dma_rdata
);
 logic mem_pending,mem_was_write,mem_was_byte;
 logic [1:0] mem_lane;
 logic block_active,block_finish,block_bad,turn_block;
 logic [3:0] block_left;
 logic [31:0] next_addr,step_bytes;
 wire available=rst_n && !clear && !fault && !mem_pending && !mem_response &&
  !block_active && !block_finish && !block_response;
 wire choose_block=block_valid && (!mem_valid || turn_block);
 assign block_ready=available && !stall && choose_block;
 assign mem_ready=available && !stall && !choose_block;
 wire take_mem=mem_valid && mem_ready;
 wire take_block=block_valid && block_ready;
 assign block_data_ready=rst_n && !clear && !fault && block_active && !stall;
 wire take_data=block_data_valid && block_data_ready;
 wire [63:0] block_limit={32'd0,block_base}+
  (64'(block_words)-1)*64'(block_stride)+64'd4;
 wire bad_block=block_words==0 || block_words>8 || block_base[1:0]!=0 ||
  block_stride[1:0]!=0 || block_limit>64'(BYTES);
 wire bad_mem=mem_addr>=BYTES || (!mem_byte &&
  (mem_addr[1:0]!=0 || {1'b0,mem_addr}+33'd4>33'(BYTES)));
 wire selected_write=take_data || (take_mem && mem_write);
 wire [31:0] address=take_data ? next_addr : {mem_addr[31:2],2'b00};
 wire [31:0] write_data=take_data ? block_data :
  (mem_byte ? ({24'b0,mem_wdata[7:0]}<<(8*mem_addr[1:0])) : mem_wdata);
 wire [3:0] write_mask=take_data ? 4'hf : (mem_byte ? (4'b1<<mem_addr[1:0]):4'hf);
 wire [1:0] selected_bank=address<98304?0:address<196608?1:address<299008?2:3;
 wire [3:0] comp_req,comp_we;
 wire [3:0][31:0] comp_addr,comp_wdata,comp_rdata;
 wire [3:0][3:0] comp_wstrb;
 wire [3:0] comp_error;
 for(genvar b=0;b<4;b++)begin:ports
  assign comp_req[b]=(take_data || (take_mem && !bad_mem)) && selected_bank==2'(b);
  assign comp_we[b]=selected_write;
  assign comp_addr[b]=address;assign comp_wdata[b]=write_data;assign comp_wstrb[b]=write_mask;
 end
 logic [1:0] read_bank;
 wire [31:0] returned_word=comp_rdata[read_bank];
 tile_local_ram_bank4 #(.BYTES(BYTES)) memory(
  .clk,.rst_n(rst_n && !clear),.comp_req,.comp_we,.comp_addr,.comp_wdata,.comp_wstrb,
  .comp_rdata,.comp_error,.dma_valid,.dma_write,.dma_ready,.dma_addr,.dma_wdata,
  .dma_wstrb,.dma_rsp_valid,.dma_error,.dma_rdata);
 assign idle=!mem_pending && !mem_response && !block_active && !block_finish && !block_response;
 assign commit_valid=selected_write && (|comp_req);
 assign commit_addr=address;assign commit_data=write_data;
 always_ff @(posedge clk)begin
  if(!rst_n || clear)begin
   mem_pending<=0;mem_response<=0;mem_was_write<=0;mem_was_byte<=0;mem_lane<=0;mem_rdata<=0;read_bank<=0;
   block_active<=0;block_finish<=0;block_response<=0;block_response_error<=0;
   block_bad<=0;block_left<=0;next_addr<=0;step_bytes<=0;turn_block<=1;fault<=0;
   write_commands<=0;write_completions<=0;write_service_cycles<=0;read_commands<=0;write_commits<=0;
  end else begin
   mem_pending<=take_mem;mem_response<=mem_pending;
   block_response<=block_finish;block_response_error<=block_bad;block_finish<=0;
   if(take_mem)begin
    mem_was_write<=mem_write;mem_was_byte<=mem_byte;mem_lane<=mem_addr[1:0];read_bank<=selected_bank;
    turn_block<=1;
    if(bad_mem)fault<=1;
    if(mem_write)write_commands<=write_commands+1'b1;else read_commands<=read_commands+1'b1;
   end
   if(mem_pending)mem_rdata<=mem_was_write ? 0 : mem_was_byte ?
    {{24{returned_word[mem_lane*8+7]}},returned_word[mem_lane*8+:8]} : returned_word;
   if(take_block)begin
    write_commands<=write_commands+1'b1;turn_block<=0;
    next_addr<=block_base;step_bytes<=block_stride;block_left<=block_words;block_bad<=bad_block;
    if(bad_block)block_finish<=1;else block_active<=1;
   end
   if(take_data)begin
    next_addr<=next_addr+step_bytes;block_left<=block_left-1'b1;
    if(block_left==1)begin block_active<=0;block_finish<=1;end
   end
   if((mem_response && mem_was_write) || block_response)write_completions<=write_completions+1'b1;
   if(commit_valid)write_commits<=write_commits+1'b1;
   if((take_mem && mem_write)||(mem_pending && mem_was_write)||(mem_response && mem_was_write)||
     take_block || block_active || block_finish || block_response)write_service_cycles<=write_service_cycles+1'b1;
   if(|comp_error)fault<=1;
  end
 end
endmodule
