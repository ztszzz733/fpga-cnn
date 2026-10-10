`timescale 1ns/1ps
module tb_neureka_benchmark;
 `include "bench.svh"
 reg [31:0] config_words[0:5];
 wire [31:0] INIT_BYTES=config_words[0],CONV_ADDR=config_words[1],RELU_ADDR=config_words[2],POOL_ADDR=config_words[3],CONV_N=config_words[4],POOL_N=config_words[5];
 reg clk=0;always #5 clk=~clk;
 reg rst_n=0;
 wire [31:0] imem_addr,imem_rdata,dmem_addr,dmem_wdata,dmem_rdata;
 wire [3:0] dmem_wstrb;wire imem_re,dmem_re,dmem_we;
 wire [31:0] mmio_addr,mmio_wdata,mmio_rdata;wire mmio_re,mmio_we,mmio_ready,load_req;
 wire [10:0] cnn_valid,cnn_write,cnn_byte,cnn_ready,cnn_response;
 wire [351:0] cnn_addr,cnn_wdata,cnn_rdata;wire cnn_cancel,cnn_mem_fault;
 wire status_busy,status_done,status_error;
`ifdef NEW_NEUREKA
 wire [31:0] task_index=cnn.completed;
 wire [3:0] task_opcode=cnn.task_op;
 wire core_active=cnn.core_busy;
 wire [5:0] core_state=cnn.convolution.core.i_ctrl.i_ctrl_fsm.state_q;
`else
 wire [31:0] task_index=cnn.queue_completed;
 wire [3:0] task_opcode=cnn.task_op;
 wire core_active=cnn.array_running;
 wire [5:0] core_state=0;
`endif
 wire sram_read_fire=|(cnn_valid & cnn_ready & ~cnn_write);
 wire sram_write_fire=|(cnn_valid & cnn_ready & cnn_write);
 cpu_core_autoload #(.SRAM_SIZE(SRAM_BYTES)) cpu(.clk(clk),.rst_n(rst_n),
  .load_req(load_req),.load_complete(1'b0),.load_error(1'b0),.*);
 imem_rom #(.INIT_FILE("program.hex")) imem(.*);
 datasram_banked #(.SRAM_SIZE(SRAM_BYTES),.BANKS(4)) mem(.io_mem_req(1'b0),.io_mem_we(1'b0),
  .io_mem_addr(32'b0),.io_mem_wdata(32'b0),.io_mem_be(4'b0),.io_mem_gnt(),.io_mem_rvalid(),.io_mem_rdata(),.io_mem_error(),.*);
`ifdef NEW_NEUREKA
 mobilefacenet_neureka_top cnn(.*);
`else
 mobilefacenet_overlap_top cnn(.*);
`endif
 reg [7:0] init_mem[0:SRAM_BYTES-1];reg [7:0] golden[0:SRAM_BYTES-1];
 longint cycles=0,start_cycle=0,read_words=0,write_words=0,wait_cycles=0;
 integer events,fd,n,errors=0;
 function automatic [7:0] peek(input integer a);
  return mem.mem[(a/4)%4][(a/4)/4][(a%4)*8+:8];
 endfunction
 initial begin
  $readmemh("bench_config.hex",config_words);
  #1;
  fd=$fopen("memory.bin","rb");n=$fread(init_mem,fd,0,INIT_BYTES);$fclose(fd);
  if(n!=INIT_BYTES) $fatal(1,"input file length");
  for(int a=0;a<INIT_BYTES;a++) mem.mem[(a/4)%4][(a/4)/4][(a%4)*8+:8]=init_mem[a];
  $readmemh("golden.hex",golden,0,CONV_N*2+POOL_N-1);
  events=$fopen("events.csv","w");$fwrite(events,"cycle,event,task\n");
  repeat(8) @(negedge clk);rst_n=1;
 end
`ifdef DUMP_WAVES
 initial if($test$plusargs("waves")) begin $dumpfile("wave.vcd");$dumpvars(1,tb_neureka_benchmark);end
`endif
 always @(posedge clk) if(rst_n) begin
  cycles<=cycles+1;
  if(mmio_we && mmio_ready && mmio_addr==32'h40000000 && mmio_wdata[0]) begin
   start_cycle<=cycles;$fwrite(events,"%0d,start,-1\n",cycles);$fflush(events);
  end
  if(status_busy) begin
   for(int i=0;i<11;i++) if(cnn_valid[i] && cnn_ready[i]) begin
    if(cnn_write[i]) write_words=write_words+1;else read_words=read_words+1;
   end
   if(|(cnn_valid & ~cnn_ready)) wait_cycles<=wait_cycles+1;
  end
`ifdef NEW_NEUREKA
  if(cnn.launch) begin $fwrite(events,"%0d,dispatch,%0d\n",cycles,cnn.completed);$fflush(events);end
  if(cnn.state==cnn.ADVANCE) begin $fwrite(events,"%0d,complete,%0d\n",cycles,cnn.completed-1);$fflush(events);end
  if(cycles%100000==0) begin
   $display("PROGRESS cycle=%0d queue=%0d task=%0d wrapper=%0d core=%0d pending=%h remaining=%h",cycles,cnn.state,cnn.completed,
    cnn.convolution.state,cnn.convolution.core.i_ctrl.i_ctrl_fsm.state_q,cnn.convolution.bridge.pending,cnn.convolution.bridge.remaining);
   $fflush();
  end
`else
  if(cnn.exec_start) $fwrite(events,"%0d,dispatch,%0d\n",cycles,cnn.dispatch_id);
  for(int u=0;u<8;u++) if(cnn.unit_done[u]) $fwrite(events,"%0d,complete,%0d\n",cycles,cnn.unit_task_ids[u*32+:32]);
`endif
  if(cnn_mem_fault || status_error) $fatal(1,"accelerator fault cycle=%0d",cycles);
  if(status_done) begin
   for(int i=0;i<CONV_N;i++) begin
    if(peek(CONV_ADDR+i)!==golden[i]) begin
     if(errors<12) $display("CONV mismatch %0d got %0d expected %0d",i,$signed(peek(CONV_ADDR+i)),$signed(golden[i]));errors++;
    end
    if(peek(RELU_ADDR+i)!==golden[CONV_N+i]) errors++;
   end
   for(int i=0;i<POOL_N;i++) if(peek(POOL_ADDR+i)!==golden[2*CONV_N+i]) errors++;
   if(errors) $fatal(1,"result mismatches=%0d",errors);
   $display("METRICS cnn_cycles=%0d read_transactions=%0d write_transactions=%0d bank_wait_cycles=%0d checked_bytes=%0d",cycles-start_cycle,read_words,write_words,wait_cycles,CONV_N*2+POOL_N);
  end
  if(dmem_we && dmem_addr==32'h80) begin
   if(dmem_wdata!=32'h600d) $fatal(1,"CPU reported failure");
   $fclose(events);$display("PASS tb_neureka_benchmark CPU completion cycle=%0d",cycles);$finish;
  end
  if(cycles>CONV_N*500+100000) $fatal(1,"timeout");
 end
endmodule
