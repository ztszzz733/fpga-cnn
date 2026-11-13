// Scheduling-only test: latency models are NOT arithmetic engines.
module tb_network_dispatch;
 logic clk=0;always #5 clk=~clk;
 logic rst_n=0,clear=0,start=0,memory_fault=0,program_valid=0;
 logic [1:0] engine_enable=3,program_dep_valid;
 logic [9:0] program_index,program_dep0,program_dep1;
 logic [511:0] program_command;
 logic [10:0] task_count=746;
 wire program_ready,busy,done,error,cancel;
 logic [4:0] unit_busy=0,unit_done=0,unit_error=0;
 wire [4:0] unit_start,unit_active,completion_pulse;
 wire [4:0][511:0] unit_command;
 wire [4:0][9:0] unit_node;
 wire [1023:0] completed_mask;
 wire [10:0] completed_count;
 logic [511:0] commands[746];
 logic [1023:0] seen=0,issued=0;
 integer remain[5],assignments[5],count=0,overlap=0,cycles=0;
 network_dispatch dut(.*);
 always @(negedge clk)begin
  if(!rst_n || clear)begin
   unit_busy=0;unit_done=0;seen=0;issued=0;count=0;overlap=0;
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
      assert(seen[unit_command[u][457:448]])else $fatal(1,"dependency not complete");
     if(unit_command[u][511:480]!=32'hffffffff)
      assert(seen[unit_command[u][489:480]])else $fatal(1,"second dependency not complete");
     issued[unit_node[u]]=1;assignments[u]++;
     remain[u]=70+int'(unit_node[u]%17)+(u==0 ? 70:0);unit_busy[u]=1;unit_done[u]=0;
    end else if(remain[u]>0)begin
     remain[u]--;
     if(remain[u]==0)begin unit_busy[u]=0;unit_done[u]=1;end
    end
   end
   if(unit_busy[0] && unit_busy[1])overlap++;
   if(cycles>2000000)$fatal(1,"watchdog");
  end
 end
 task tick;@(posedge clk);#1;endtask
 task load_all;
  for(integer i=0;i<task_count;i++)begin
   program_valid=1;program_index=10'(i);program_command=commands[i];
   program_dep_valid={commands[i][511:480]!=32'hffffffff,commands[i][479:448]!=32'hffffffff};
   program_dep0=commands[i][457:448];program_dep1=commands[i][489:480];tick();
  end
  program_valid=0;start=1;tick();start=0;
 endtask
 initial begin
  $readmemh("commands.hex",commands);repeat(3)tick();rst_n=1;tick();
  load_all();wait(completed_count>=20);tick();clear=1;tick();
  assert(cancel && !busy)else $fatal(1,"clear");clear=0;tick();
  load_all();wait(done);tick();
  assert(count==746 && completed_count==746 && overlap>0)else $fatal(1,"capacity/count");
  for(integer u=0;u<5;u++)assert(assignments[u]>0)else $fatal(1,"unused unit");
  $display("PASS capacity 746 commands, overlap=%0d, assignments=%0d/%0d/%0d/%0d/%0d",overlap,assignments[0],assignments[1],assignments[2],assignments[3],assignments[4]);
  clear=1;tick();clear=0;tick();
  task_count=3;commands[0]=0;commands[1]=0;commands[2]=0;
  commands[0][511:448]='1;commands[1][511:448]='1;
  commands[2][31:0]=2;commands[2][479:448]=0;commands[2][511:480]=1;
  load_all();wait(done);tick();assert(count==3)else $fatal(1,"join");
  $display("PASS two-input join");
  clear=1;tick();clear=0;tick();
  program_valid=1;program_index=0;program_command=0;program_dep_valid=1;program_dep0=0;tick();program_valid=0;
  assert(error)else $fatal(1,"self dependency accepted");
  clear=1;tick();clear=0;tick();memory_fault=1;tick();
  assert(error && cancel && !busy)else $fatal(1,"fault cancellation");
  $display("PASS clear/restart, self-dependency rejection, memory fault");$finish;
 end
endmodule
