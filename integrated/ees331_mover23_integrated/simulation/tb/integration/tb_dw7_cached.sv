`timescale 1ns/1ps
module tb_dw7_cached;
 localparam SIZE=262144;
 logic clk=0;always #5 clk=~clk;
 logic rst_n=0,clear=0,start=0,reuse_weights=0;
 logic [31:0] input_base,weight_base,output_base,width,height,channels;
 wire busy,done,error,valid,write,byte_access,cancel,mac_fire,weights_cached;
 wire [3:0] phase;wire cache_hit;
 wire [31:0] addr,wdata;wire ready;logic response=0;logic [31:0] rdata=0;
 dw7_cached_engine dut(.*);
 logic post_start=0,use_post=0;
 logic [31:0] post_dst,parameter_base,count;
 wire pv,pw,pbyte,pbusy,pdone,perror;wire [31:0] pa,pd;
 quant_post_engine post(.clk(clk),.rst_n(rst_n),.clear(clear),.start(post_start),.mode_add(1'b0),
  .src_a(output_base),.src_b(32'b0),.destination(post_dst),.parameter_base(parameter_base),.count(count),.channels(channels),
  .busy(pbusy),.done(pdone),.error(perror),.valid(pv),.write(pw),.byte_access(pbyte),.addr(pa),.wdata(pd),
  .ready(ready && use_post),.response(response && use_post),.rdata(rdata));
 wire mv=use_post ? pv:valid,mw=use_post ? pw:write,mb=use_post ? pbyte:byte_access;
 wire [31:0] ma=use_post ? pa:addr,md=use_post ? pd:wdata;
 logic [7:0] mem[SIZE],initial_mem[SIZE],gold[SIZE];
 logic [31:0] jobs[18];
 bit mutable_byte[SIZE],seen_input[SIZE];
 logic pending=0;integer delay_left=0,cycle=0,stall=0;
 logic [31:0] saved_addr,saved_data;logic saved_write,saved_byte;
 integer input_reads=0,weight_reads=0,raw_writes=0,mac_cycles=0,checked=0,frame=0,logfile;
 integer start_cycle,elapsed[2],all_cycles[2],read_counts[2],weight_counts[2];
 bit measuring=0,holding=0;logic [65:0] held_request;
 assign ready=!pending && !response && !clear && (stall==0 || cycle%5>=2);
 always @(posedge clk)begin
  cycle<=cycle+1;response<=0;
  if(cycle>1000000)$fatal(1,"watchdog");
  if(!rst_n || clear)begin pending<=0;response<=0;holding<=0;end
  else begin
   if(holding && (!mv || {mw,mb,ma,md}!==held_request))$fatal(1,"request changed under backpressure");
   holding<=mv && !ready;held_request<={mw,mb,ma,md};
   if(mv && ready)begin
    if(ma>=SIZE || (!mb && (ma[1:0]!=0 || ma+3>=SIZE)))$fatal(1,"bad address");
    pending<=1;delay_left<=stall==0 ? 0:cycle%4;saved_addr<=ma;saved_data<=md;saved_write<=mw;saved_byte<=mb;
    if(measuring && !use_post)begin
     if(phase==1)weight_reads++;
     if(phase==3)begin
      if(ma<input_base || ma+4>input_base+width*height*channels || seen_input[ma])$fatal(1,"duplicate/outside input read");
      seen_input[ma]=1;input_reads++;
     end
     if(mw)raw_writes++;
    end
   end
   if(pending)begin
    if(delay_left!=0)delay_left<=delay_left-1;
    else begin
     pending<=0;response<=1;
     if(saved_write)begin
      if(!mutable_byte[saved_addr])$fatal(1,"write to immutable area");
      if(saved_byte)mem[saved_addr]<=saved_data[7:0];
      else for(integer b=0;b<4;b++)mem[saved_addr+b]<=saved_data[b*8+:8];
      rdata<=0;
     end else rdata<=saved_byte ? {{24{mem[saved_addr][7]}},mem[saved_addr]}:{mem[saved_addr+3],mem[saved_addr+2],mem[saved_addr+1],mem[saved_addr]};
    end
   end
   if(measuring && mac_fire)mac_cycles++;
  end
 end
 task automatic setup_job(input integer j);
  input_base=jobs[j*9];weight_base=jobs[j*9+1];output_base=jobs[j*9+2];post_dst=jobs[j*9+3];parameter_base=jobs[j*9+4];
  width=jobs[j*9+5];height=jobs[j*9+6];channels=jobs[j*9+7];count=jobs[j*9+8];
 endtask
 task automatic check_bytes(input integer a,n);
  for(integer b=0;b<n;b++)if(mem[a+b]!==gold[a+b])$fatal(1,"mismatch frame=%0d addr=%h got=%h want=%h",frame,a+b,mem[a+b],gold[a+b]);
  checked+=n;
 endtask
 task automatic launch;
  @(negedge clk);start=1;@(negedge clk);start=0;
 endtask
 initial begin
  integer fd,n,out;
  n=$value$plusargs("stall=%d",stall);
  $readmemh("jobs.hex",jobs);fd=$fopen("memory.bin","rb");n=$fread(initial_mem,fd);$fclose(fd);if(n!=SIZE)$fatal(1,"input size");
  fd=$fopen("golden.bin","rb");n=$fread(gold,fd);$fclose(fd);if(n!=SIZE)$fatal(1,"gold size");
  for(integer a=0;a<SIZE;a++)mem[a]=initial_mem[a];
  for(integer j=0;j<2;j++)begin
   for(integer b=0;b<jobs[j*9+8]*4;b++)mutable_byte[jobs[j*9+2]+b]=1;
   for(integer b=0;b<jobs[j*9+8];b++)mutable_byte[jobs[j*9+3]+b]=1;
  end
  repeat(5)@(negedge clk);rst_n=1;setup_job(0);
  if($test$plusargs("restart"))begin
   launch();wait(pending);@(negedge clk);clear=1;repeat(3)@(negedge clk);
   if(valid || busy || weights_cached || pending || response)$fatal(1,"clear/cancel failed");
   clear=0;
  end
  logfile=$fopen("metrics.json","w");out=$fopen("outputs.bin","wb");
  for(frame=0;frame<2;frame++)begin
   @(negedge clk);setup_job(frame);reuse_weights=frame==1;use_post=0;
   input_reads=0;weight_reads=0;raw_writes=0;mac_cycles=0;measuring=1;start_cycle=cycle;
   launch();wait(done || error);@(negedge clk);
   if(error || cache_hit!=(frame==1))$fatal(1,"engine/cache failure");
   elapsed[frame]=cycle-start_cycle;read_counts[frame]=input_reads;weight_counts[frame]=weight_reads;
   if(input_reads!=width*height*channels/4 || weight_reads!=(frame==0 ? 49*channels/4:0) || raw_writes!=count || mac_cycles!=49*count/8)$fatal(1,"reuse/MAC counters wrong");
   check_bytes(output_base,count*4);
   use_post=1;post_start=1;@(negedge clk);post_start=0;wait(pdone || perror);@(negedge clk);
   if(perror)$fatal(1,"post failed");check_bytes(post_dst,count);all_cycles[frame]=cycle-start_cycle;
   for(integer b=0;b<count;b++)$fwrite(out,"%c",mem[post_dst+b]);
   measuring=0;repeat(3)@(negedge clk);
  end
  for(integer a=0;a<SIZE;a++)if(!mutable_byte[a] && mem[a]!==initial_mem[a])$fatal(1,"guard corruption");
  // Invalid configurations must fail without launching a memory request.
  use_post=0;setup_job(0);width=6;launch();wait(error || done);if(!error || valid || pending)$fatal(1,"bad width accepted");
  repeat(2)@(negedge clk);setup_job(0);channels=7;launch();wait(error || done);if(!error || valid || pending)$fatal(1,"unaligned channels accepted");
  $fwrite(logfile,"{\"checked_bytes\":%0d,\"conv_cycles\":[%0d,%0d],\"chain_cycles\":[%0d,%0d],\"input_word_reads\":[%0d,%0d],\"weight_word_reads\":[%0d,%0d]}\n",checked,elapsed[0],elapsed[1],all_cycles[0],all_cycles[1],read_counts[0],read_counts[1],weight_counts[0],weight_counts[1]);
  $fclose(logfile);$fclose(out);$display("PASS tb_dw7_cached checked=%0d",checked);$finish;
 end
 initial begin $dumpfile("control.vcd");$dumpvars(1,tb_dw7_cached);end
endmodule
