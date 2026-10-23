// Real dispatch/lease/result controllers, latency-only operator models.
// This proves control and lifetime behavior, NOT full-network arithmetic.
module tb_full_buffer_plan;
 logic clk=0;always #5 clk=~clk;
 logic rst_n=0,clear=0,start=0,memory_fault=0,program_valid=0;
 logic [1:0] engine_enable=3,program_dep_valid;
 logic [9:0] program_index,program_dep0,program_dep1;
 logic [511:0] program_command;logic [10:0] task_count=746;
 logic program_allocate_valid,program_result_valid;
 logic [2:0] program_allocate_slot,program_use_valid;
 logic [8:0] program_use_slots;logic [29:0] program_use_owners;
 logic [1023:0] program_hold_mask;
 logic [31:0] program_result_frame,program_result_addr,program_result_bytes;
 wire program_ready,compute_busy,compute_done,error,cancel,buffer_ready,reserve_commit,wait_buffer;
 wire [9:0] candidate_node;
 logic [4:0] unit_busy=0,unit_done=0,unit_error=0;
 wire [4:0] unit_start,unit_active,completion_pulse;
 wire [4:0][511:0] unit_command;wire [4:0][9:0] unit_node;
 wire [1023:0] completed_mask;wire [10:0] completed_count;
 wire [7:0] buffer_live,buffer_release,buffer_allocate,external_hold,result_error;
 wire [79:0] buffer_owners;
 wire result_valid,result_accept,outputs_pending,configuration_error;
 wire [31:0] result_frame,result_addr,result_bytes;
 logic result_ready=0;
 logic [511:0] commands[746];logic [1247:0] leases_data[746];logic [127:0] results_data[746];
 logic [1023:0] seen=0,issued=0;
 integer remain[5],assignments[5],count=0,overlap=0,cycles=0,allocations=0,releases=0,acks=0,held_cycles=0;
 logic [1:0] accepted=0;logic stalled=0;logic [95:0] descriptor;
 wire done=compute_done && !outputs_pending && !(|buffer_live);
 network_dispatch_buffered dispatch(.*,.busy(compute_busy),.done(compute_done),.memory_fault(memory_fault || configuration_error));
 network_buffer_leases buffers(.*,.program_accept(program_valid && program_ready));
 network_result_handoff handoff(.*,.program_accept(program_valid && program_ready));
 always @(negedge clk)begin
  if(!rst_n || clear)begin
   unit_busy=0;unit_done=0;seen=0;issued=0;count=0;overlap=0;
   allocations=0;releases=0;acks=0;accepted=0;held_cycles=0;stalled=0;result_ready=0;
   for(integer u=0;u<5;u++)begin remain[u]=0;assignments[u]=0;end
  end else if(!cancel)begin
   cycles++;
   for(integer u=0;u<5;u++)begin
    if(completion_pulse[u])begin
     assert(!seen[unit_node[u]] && issued[unit_node[u]])else $fatal(1,"bad completion");
     seen[unit_node[u]]=1;count++;
    end
    if(unit_start[u])begin
     assert(!issued[unit_node[u]] && !unit_busy[u])else $fatal(1,"double launch");
     assert(unit_command[u]===commands[unit_node[u]])else $fatal(1,"payload changed");
     if(unit_command[u][479:448]!=32'hffffffff)
      assert(seen[unit_command[u][457:448]])else $fatal(1,"dependency incomplete");
     issued[unit_node[u]]=1;assignments[u]++;
     remain[u]=70+int'(unit_node[u]%17)+(u==0 ? 130:0);unit_busy[u]=1;unit_done[u]=0;
    end else if(remain[u]>0)begin
     remain[u]--;
     if(remain[u]==0)begin unit_busy[u]=0;unit_done[u]=1;end
    end
   end
   if(result_accept)begin
    assert(result_frame<2 && !accepted[result_frame] && held_cycles>=500)else $fatal(1,"bad acknowledgement");
    accepted[result_frame]=1;acks++;held_cycles=0;stalled=0;
   end
   if(result_valid)begin
    assert(result_frame<2 && seen[744+result_frame] && result_bytes==128 && result_error==0)else $fatal(1,"result before completion");
    assert(result_addr==results_data[744+result_frame][95:64])else $fatal(1,"result address");
    if(stalled)assert(descriptor=={result_frame,result_addr,result_bytes})else $fatal(1,"unstable descriptor");
    descriptor={result_frame,result_addr,result_bytes};stalled=1;held_cycles++;
   end
   result_ready=result_valid && held_cycles>=500 && completed_count==746;
   for(integer b=0;b<8;b++)begin
    if(buffer_allocate[b])allocations++;
    if(buffer_release[b])begin
     assert((leases_data[buffer_owners[b*10+:10]][1247:224]&seen)==leases_data[buffer_owners[b*10+:10]][1247:224])else $fatal(1,"released before all writers/consumers");
     if(buffer_owners[b*10+:10]>=744)assert(accepted[buffer_owners[b*10+:10]-744])else $fatal(1,"final result released before ack");
     releases++;
    end
   end
   if(unit_busy[0] && unit_busy[1])overlap++;
   if(error || cycles>2000000)$fatal(1,"controller failure or watchdog");
  end
 end
 task tick;@(posedge clk);#1;endtask
 task load_all;
  for(integer i=0;i<746;i++)begin
   program_valid=1;program_index=10'(i);program_command=commands[i];
   program_dep_valid={commands[i][511:480]!=32'hffffffff,commands[i][479:448]!=32'hffffffff};
   program_dep0=commands[i][457:448];program_dep1=commands[i][489:480];
   program_allocate_valid=leases_data[i][31:0]!=32'hffffffff;program_allocate_slot=leases_data[i][2:0];
   program_use_valid=0;program_use_slots=0;program_use_owners=0;
   for(integer k=0;k<3;k++)begin
    program_use_valid[k]=leases_data[i][32+k*32+:32]!=32'hffffffff;
    program_use_slots[k*3+:3]=leases_data[i][32+k*32+:3];program_use_owners[k*10+:10]=leases_data[i][128+k*32+:10];
   end
   program_hold_mask=leases_data[i][1247:224];program_result_valid=results_data[i][0];
   program_result_frame=results_data[i][63:32];program_result_addr=results_data[i][95:64];program_result_bytes=results_data[i][127:96];tick();
  end
  program_valid=0;start=1;tick();start=0;
 endtask
 initial begin
  $readmemh("commands.hex",commands);$readmemh("leases.hex",leases_data);$readmemh("results.hex",results_data);
  repeat(3)tick();rst_n=1;tick();load_all();
  wait(completed_count>=20);tick();clear=1;tick();clear=0;tick();load_all();
  wait(done);tick();
  assert(count==746 && completed_count==746 && overlap>0 && allocations==262 && releases==262 && acks==2 && accepted==3)else $fatal(1,"accounting");
  for(integer u=0;u<5;u++)assert(assignments[u]>0)else $fatal(1,"unused unit");
  $display("PASS full plan CONTROL ONLY: commands=%0d allocations=%0d releases=%0d results=%0d overlap=%0d",count,allocations,releases,acks,overlap);
  $display("assignments=%0d/%0d/%0d/%0d/%0d cycles=%0d",assignments[0],assignments[1],assignments[2],assignments[3],assignments[4],cycles);$finish;
 end
endmodule
