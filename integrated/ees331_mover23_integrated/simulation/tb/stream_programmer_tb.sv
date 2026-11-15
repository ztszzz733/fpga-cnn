`timescale 1ns/1ps
module stream_programmer_tb;
 logic clk=0;always #5 clk=~clk;
 logic rst_n=0,clear=0,start=0;logic [2:0] image_count=0;
 logic template_valid=0;logic [3:0] template_index=0;
 logic [511:0] template_command=0;logic [3:0] template_source_modes=0;
 logic [1:0] template_dep_valid=0,template_allocate_slot=0;
 logic [3:0] template_dep0=0,template_dep1=0;logic [15:0] template_hold_mask=0;
 logic [2:0] template_use_valid=0;logic [5:0] template_use_slots=0;
 logic [11:0] template_use_owners=0;logic template_result_valid=0;logic [31:0] template_result_bytes=0;
 logic address_valid=0;logic [1:0] address_slot=0;logic [31:0] image_base=0,workspace_base=0,address_frame=0;
 wire configuration_ready,configuration_error,expanding;logic program_ready=1;
 wire program_valid;wire [5:0] program_index,program_dep0,program_dep1;
 wire [511:0] program_command;wire [1:0] program_dep_valid;wire [6:0] task_count;
 wire program_allocate_valid;wire [3:0] program_allocate_slot;wire [63:0] program_hold_mask;
 wire [2:0] program_use_valid;wire [11:0] program_use_slots;wire [17:0] program_use_owners;
 wire program_result_valid;wire [31:0] program_result_frame,program_result_addr,program_result_bytes;
 wire core_start;
 stream_fixed_programmer dut(.*);
 integer tick=0,seen=0,checks=0;logic check_run=0,stalled=0;logic [511:0] held_command;
 always @(negedge clk)begin tick=tick+1;program_ready=tick%3!=0;end
 always @(posedge clk)if(check_run)begin
  if(stalled && (!program_valid || program_command!==held_command))$fatal(1,"program changed under backpressure");
  stalled<=program_valid && !program_ready;held_command<=program_command;
  if(program_valid && program_ready)begin
   integer f,s;reg [63:0] want_hold;
   f=seen%image_count;s=seen/image_count;want_hold=64'(1)<<seen;if(s==0)want_hold|=64'(1)<<(image_count+f);
   if(program_index!=seen || task_count!=2*image_count || program_allocate_slot!=4*f+s || program_hold_mask!==want_hold)$fatal(1,"batch metadata");
   if(program_command[32+:32]!=(s==0?1024*(f+1)+12:32768+16384*f+88))$fatal(1,"source relocation");
   if(program_command[64+:32]!=1024 || program_command[96+:32]!=32768+16384*f+(s==0?32:96))$fatal(1,"shared weights/destination relocation");
   if(program_command[416+:32]!=991+17*f || program_command[448+:32]!=f)$fatal(1,"frame tag/slot");
   if(s==1 && (program_dep_valid!=1 || program_dep0!=f || program_use_valid!=1 || program_use_slots[3:0]!=4*f || program_use_owners[5:0]!=f))$fatal(1,"dependency/owner relocation");
   if(program_result_valid!=(s==1) || program_result_frame!=991+17*f || program_result_addr!=program_command[96+:32] || program_result_bytes!=64)$fatal(1,"result descriptor");
   seen=seen+1;checks=checks+1;
  end
 end
 task configure(input integer count);
  begin
   @(negedge clk);clear=1;check_run=0;stalled=0;seen=0;
   @(negedge clk);clear=0;image_count=count;
   for(integer s=0;s<2;s++)begin
    @(negedge clk);template_valid=1;template_index=s;template_command=0;
    template_command[31:0]=s==0?4:5;template_command[32+:32]=s==0?12:88;
    template_command[64+:32]=1024;template_command[96+:32]=s==0?32:96;
    template_source_modes=s==0?1:2;template_dep_valid=s==0?0:1;template_dep0=0;
    template_allocate_slot=s;template_hold_mask=s==0?3:2;
    template_use_valid=s==0?0:1;template_use_slots=0;template_use_owners=0;
    template_result_valid=s==1;template_result_bytes=64;
   end
   for(integer f=0;f<count;f++)begin
    @(negedge clk);template_valid=0;address_valid=1;address_slot=f;
    image_base=1024*(f+1);workspace_base=32768+16384*f;address_frame=991+17*f;
   end
   @(negedge clk);template_valid=0;address_valid=0;
  end
 endtask
 initial begin
  repeat(3)@(negedge clk);rst_n=1;
  for(integer n=1;n<=4;n++)begin
   configure(n);start=1;check_run=1;
   @(negedge clk);start=0;
   wait(core_start);@(negedge clk);if(configuration_error || seen!=2*n)$fatal(1,"incorrect batch count");
   @(negedge clk);check_run=0;
  end
  configure(1);image_count=0;start=1;@(negedge clk);start=0;
  if(!configuration_error || expanding || program_valid)$fatal(1,"zero count accepted");
  configure(1);image_count=2;start=1;@(negedge clk);start=0;
  if(!configuration_error)$fatal(1,"missing address accepted");
  configure(1);address_valid=1;address_slot=0;@(negedge clk);address_valid=0;
  if(!configuration_error)$fatal(1,"duplicate address slot accepted");
  configure(1);template_valid=1;template_index=2;template_dep_valid=1;template_dep0=2;
  @(negedge clk);template_valid=0;if(!configuration_error)$fatal(1,"self-dependency accepted");
  $display("PASS STREAM_PROGRAMMER 1..4 frames, %0d expanded commands, stalls, 4 invalid configurations",checks);$finish;
 end
 initial begin #100000;$fatal(1,"watchdog");end
endmodule
