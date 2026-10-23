`timescale 1ns/1ps
// Drivers + independent checker only. Memory storage, arbitration, byte lanes,
// responses and every arithmetic operator are actual RTL in self_stream_top.
module self_stream_tb #(
 parameter K3_UNITS=3,K1_UNITS=1,POST_UNITS=1
);
 localparam NU=K3_UNITS+K1_UNITS+POST_UNITS+3,DW=K3_UNITS+K1_UNITS,
  POST=DW+1,ADD=POST+POST_UNITS,PAD=ADD+1,NT=44,NM=262144,
  SLOT_BASE=32768,SLOT_PITCH=2112,SLOT_BYTES=2048,INIT_BYTES=SLOT_BASE+16*SLOT_PITCH;
 logic clk=0;always #5 clk=~clk;
 logic rst_n=0,clear=0,start=0;
 logic [NU-1:0] unit_enable='1;
 wire frame_valid,frame_ready;wire [1:0] frame_slot;wire [31:0] frame_id;wire [3:0] frames_ready;
 logic [2:0] image_count=4;
 logic template_valid=0;logic [3:0] template_index=0,template_dep0=0,template_dep1=0;
 logic [511:0] template_command=0;logic [3:0] template_source_modes=0;logic [1:0] template_dep_valid=0,template_allocate_slot=0;
 logic [15:0] template_hold_mask=0;logic [2:0] template_use_valid=0;logic [5:0] template_use_slots=0;
 logic [11:0] template_use_owners=0;logic template_result_valid=0;logic [31:0] template_result_bytes=0;
 logic address_valid=0;logic [1:0] address_slot=0;logic [31:0] image_base=0,workspace_base=0,address_frame=0;
 wire configuration_ready;
 wire result_ready,result_valid,result_accept,outputs_pending,compute_done;
 wire [31:0] result_frame,result_addr,result_bytes;wire [7:0] result_error;
 wire [15:0] external_hold,buffer_live,buffer_release,buffer_allocate;
 wire [95:0] buffer_owners;wire wait_buffer,wait_input,busy,done,error,cancel,memory_fault;
 logic [31:0] dmem_addr=0,dmem_wdata=0;logic [3:0] dmem_wstrb=0;logic dmem_re=0,dmem_we=0;
 wire [31:0] dmem_rdata;
 logic io_mem_req,io_mem_we;logic [31:0] io_mem_addr,io_mem_wdata;logic [3:0] io_mem_be;
 wire io_mem_gnt,io_mem_rvalid,io_mem_error;wire [31:0] io_mem_rdata;
 wire [NU-1:0] mem_valid,mem_write,mem_byte,mem_ready,mem_response;
 wire [NU*32-1:0] mem_addr,mem_wdata,mem_rdata;
 wire [NU-1:0] unit_start,unit_active,completion_pulse,operator_busy,operator_work;
 wire [NU-1:0][5:0] unit_node;wire [6:0] completed_count;wire [63:0] completed_mask;
 wire [DW-1:0][31:0] conv_input_reads,conv_weight_reads,conv_mac_count;
 self_fixed_network_top #(.K3_UNITS(K3_UNITS),.K1_UNITS(K1_UNITS),.POST_UNITS(POST_UNITS)) dut(.*);
 reg [7:0] initial_mem[0:NM-1],expected[0:28811],images[0:587],outputs[0:31];
 reg [31:0] commands[0:NT*16-1],meta[0:NT*14-1],image_info[0:11];
 reg [31:0] templates[0:175],template_info[0:120];
 reg [2047:0] written[NT];
 reg [NU-1:0] pending=0,held=0;
 reg [65:0] held_fields[NU];
 integer accept_addr[NU],accept_len[NU],accept_data[NU];logic [NU-1:0] accept_write=0;
 integer launched[NU],active_cycles[NU],work_cycles[NU],read_bytes[NU],write_bytes[NU],wait_cycles[NU];
 integer frame_begin[4],frame_commit[4],frame_first[4],frame_result[4];
 integer cycle=0,mode=0,pace=80,send_frame=0,send_offset=0,send_wait=80;
 logic commit_pending=0,checking=0;
 logic reader_active=0,reader_pending=0,reader_done=0;
 integer reader_frame=0,reader_addr=0,reader_bytes=0,reader_offset=0,reader_wait=0;
 logic [3:0] result_seen=0;logic reader_want,writer_want;
 integer checks=0,allocs=0,releases=0,results=0,compute_cycle=0,expanded=0;
 integer overlap_frames=0,dual_mac=0,input_compute=0,input_mac=0,io_write_compute=0,peak_frames=0,peak_k3=0,cpu_reads=0,multi_frame_work=0,cross_operator_work=0;
 integer enable_mask=-1;
 integer fd,events,trace=0;string data_dir;
 function automatic [7:0] peek(input integer addr);
  peek=8'(dut.core.storage.mem[(addr>>2)&3][addr>>4]>>(8*(addr&3)));
 endfunction
 assign frame_valid=checking && commit_pending && !cancel;
 assign frame_slot=2'(send_frame);assign frame_id=100+send_frame;
 assign result_ready=checking && reader_active && reader_done && !cancel;
 always_comb begin
  reader_want=checking && !cancel && reader_active && !reader_pending && !reader_done && reader_wait==0;
  writer_want=checking && mode!=6 && !cancel && send_frame<4 && !commit_pending && send_wait==0 && !reader_pending &&
   (mode!=1 || send_frame==0 || result_seen[send_frame-1]);
  io_mem_req=reader_want || writer_want;io_mem_we=!reader_want;io_mem_addr=0;io_mem_wdata=0;io_mem_be=0;
  if(reader_want)io_mem_addr=reader_addr+reader_offset;
  else if(writer_want)begin
   io_mem_addr=image_info[send_frame*3]+send_offset;
   for(integer b=0;b<4;b++)if(send_offset+b<image_info[send_frame*3+1])begin
    io_mem_be[b]=1;io_mem_wdata[b*8+:8]=images[image_info[send_frame*3+2]+send_offset+b];
   end
  end
 end
 // Drive CPU port away from the acceptance edge. In stress mode it creates
 // exact-word read collisions; bai SRAM must backpressure B, not corrupt data.
 always @(negedge clk)if(checking)begin
  dmem_re=0;dmem_we=0;dmem_wstrb=0;
  if(mode==2 && cycle%11<5 && (|mem_valid))begin
   for(integer k=NU-1;k>=0;k--)if(mem_valid[k])begin dmem_re=1;dmem_addr=mem_addr[k*32+:32]&32'hfffffffc;end
  end else if(cycle%17==0)begin dmem_re=1;dmem_addr=1024;end
 end
 always @(posedge clk)begin
  if(!rst_n || clear || !checking)begin
   cycle<=0;send_frame<=0;send_offset<=0;send_wait<=pace;commit_pending<=0;
   reader_active<=0;reader_pending<=0;reader_done<=0;reader_wait<=0;reader_offset<=0;result_seen<=0;
   pending<=0;held<=0;
  end else begin
   cycle<=cycle+1;
   if(dut.program_valid && dut.program_ready)begin
    integer n;n=dut.program_index;
    for(integer w=0;w<16;w++)if(dut.program_command[w*32+:32]!==commands[n*16+w])$fatal(1,"CNN address expansion mismatch node%0d word%0d",n,w);
    if(dut.program_hold_mask!=={meta[n*14+5],meta[n*14+4]} || dut.program_allocate_slot!=meta[n*14+3] || dut.program_dep_valid!=meta[n*14] || dut.program_use_valid!=meta[n*14+6])$fatal(1,"CNN lifetime expansion mismatch");
    if((dut.program_dep_valid[0] && dut.program_dep0!=meta[n*14+1]) || (dut.program_dep_valid[1] && dut.program_dep1!=meta[n*14+2]))$fatal(1,"CNN dependency expansion mismatch");
    for(integer u=0;u<3;u++)if(dut.program_use_valid[u])begin
     if(dut.program_use_slots[u*4+:4]!=((meta[n*14+7]>>(u*4))&15) || dut.program_use_owners[u*6+:6]!=((meta[n*14+8]>>(u*6))&63))$fatal(1,"CNN owner expansion mismatch");
    end
    expanded=expanded+1;
   end
   if(mode==6 && send_frame<4 && !commit_pending)begin commit_pending<=1;frame_begin[send_frame]=cycle;end
   if(send_wait>0)send_wait<=send_wait-1;
   if(frame_valid && frame_ready)begin
    frame_commit[send_frame]=cycle;send_frame<=send_frame+1;send_offset<=0;send_wait<=pace;commit_pending<=0;
    $fwrite(events,"%0d,input_commit,-1,-1,%0d\n",cycle,frame_id);
   end
   if(io_mem_req && io_mem_gnt)begin
    if(io_mem_error)$fatal(1,"image IO error");
    if(io_mem_we)begin
     if(send_offset==0)begin frame_begin[send_frame]=cycle;$fwrite(events,"%0d,input_begin,-1,-1,%0d\n",cycle,100+send_frame);end
     if(|operator_work)io_write_compute=io_write_compute+1;
     if(send_offset+4>=image_info[send_frame*3+1])commit_pending<=1;
     else begin send_offset<=send_offset+4;send_wait<=pace;end
    end else reader_pending<=1;
   end
   if(result_valid && !reader_active)begin
    if(result_frame<100 || result_frame>103 || result_bytes!=8 || result_error || result_seen[result_frame-100])$fatal(1,"bad result descriptor");
    if(result_addr!=meta[(40+result_frame-100)*14+11])$fatal(1,"wrong result address");
    reader_active<=1;reader_done<=0;reader_frame<=result_frame;reader_addr<=result_addr;reader_bytes<=result_bytes;
    reader_offset<=0;reader_wait<=(mode==2)?30000:40;
   end
   if(reader_wait>0)reader_wait<=reader_wait-1;
   if(reader_active && !result_accept && (result_frame!=reader_frame || result_addr!=reader_addr || result_bytes!=reader_bytes || !result_valid))$fatal(1,"unstable held result");
   if(io_mem_rvalid)begin
    if(!reader_pending || io_mem_error)$fatal(1,"unexpected IO response");
    for(integer b=0;b<4;b++)begin
     if(io_mem_rdata[b*8+:8]!==expected[meta[(40+reader_frame-100)*14+13]+reader_offset+b])$fatal(1,"wrong external result frame%0d",reader_frame);
     outputs[(reader_frame-100)*8+reader_offset+b]=io_mem_rdata[b*8+:8];
    end
    reader_offset<=reader_offset+4;reader_pending<=0;
    if(reader_offset+4==reader_bytes)reader_done<=1;
   end
   if(result_valid && result_ready)begin
    result_seen[result_frame-100]<=1;results=results+1;frame_result[result_frame-100]=cycle;
    $fwrite(events,"%0d,result_ack,-1,-1,%0d\n",cycle,result_frame);
   end
   if(result_accept)begin reader_active<=0;reader_done<=0;end
   if(cancel)begin pending<=0;held<=0;end
   else begin
    logic [3:0] active_frames,work_frames;logic [5:0] work_kinds;integer k3_work;
    active_frames=0;work_frames=0;work_kinds=0;k3_work=0;
    if(dmem_re)cpu_reads=cpu_reads+1;
    for(integer k=0;k<NU;k++)begin
     integer node,a,n,off;
     node=unit_node[k];
     if(unit_active[k])active_frames[node%4]=1;
     if(operator_work[k])begin
      work_frames[node%4]=1;
      if(k<K3_UNITS)work_kinds[0]=1;else if(k<DW)work_kinds[1]=1;else if(k==DW)work_kinds[2]=1;else if(k<ADD)work_kinds[3]=1;else if(k==ADD)work_kinds[4]=1;else work_kinds[5]=1;
     end
     if(k<K3_UNITS && operator_work[k])k3_work++;
     if(held[k] && (!mem_valid[k] || held_fields[k]!=={mem_write[k],mem_byte[k],mem_addr[k*32+:32],mem_wdata[k*32+:32]}))$fatal(1,"stalled request changed unit%0d",k);
     held[k]<=mem_valid[k] && !mem_ready[k];held_fields[k]<={mem_write[k],mem_byte[k],mem_addr[k*32+:32],mem_wdata[k*32+:32]};
     if(mem_response[k])begin
      if(!pending[k])$fatal(1,"unsolicited CNN response unit%0d",k);
      pending[k]<=0;
      if(accept_write[k])begin
       for(integer b=0;b<accept_len[k];b++)if(peek(accept_addr[k]+b)!==8'(accept_data[k]>>(8*b)))$fatal(1,"bai SRAM write/byte lane mismatch");
      end
     end
     if(mem_valid[k] && mem_ready[k])begin
      a=mem_addr[k*32+:32];n=mem_byte[k]?1:4;
      if(pending[k] && !mem_response[k])$fatal(1,"multiple outstanding requests");
      if(!unit_active[k] || !frames_ready[node%4])$fatal(1,"read before image commit");
      if(a<0 || a+n>NM || (!mem_byte[k] && a%4))$fatal(1,"invalid memory transaction");
      pending[k]<=1;accept_addr[k]=a;accept_len[k]=n;accept_data[k]=mem_wdata[k*32+:32];accept_write[k]<=mem_write[k];
      if(mem_write[k])begin
       if(a<meta[node*14+11] || a+n>meta[node*14+11]+meta[node*14+12])$fatal(1,"out of output bounds");
       for(integer b=0;b<n;b++)begin
        off=a+b-meta[node*14+11];if(written[node][off])$fatal(1,"duplicate output write");written[node][off]=1;
       end
       write_bytes[k]=write_bytes[k]+n;
      end else read_bytes[k]=read_bytes[k]+n;
     end
     if(operator_busy[k])active_cycles[k]=active_cycles[k]+1;
     if(operator_work[k])work_cycles[k]=work_cycles[k]+1;
     if(mem_valid[k] && !mem_ready[k])wait_cycles[k]=wait_cycles[k]+1;
     if(unit_start[k])begin
      if(!frames_ready[node%4] || frame_commit[node%4]<0)$fatal(1,"launch before image commit");
      if(frame_first[node%4]<0)frame_first[node%4]=cycle;
      launched[k]=launched[k]+1;$fwrite(events,"%0d,launch,%0d,%0d,%0d\n",cycle,k,node,100+node%4);
     end
     if(completion_pulse[k])begin
      if(pending[k] || mem_valid[k])$fatal(1,"completion before drained response");
      a=meta[node*14+11];n=meta[node*14+12];off=meta[node*14+13];
      for(integer b=0;b<n;b++)if(!written[node][b] || peek(a+b)!==expected[off+b])$fatal(1,"checkpoint mismatch node%0d offset%0d actual%0d expected%0d",node,b,peek(a+b),expected[off+b]);
      checks=checks+n;$fwrite(events,"%0d,done,%0d,%0d,%0d\n",cycle,k,node,100+node%4);
     end
    end
    if($countones(active_frames)>1)overlap_frames=overlap_frames+1;
    if($countones(work_frames)>1)multi_frame_work=multi_frame_work+1;
    if($countones(work_kinds)>1)cross_operator_work=cross_operator_work+1;
    if($countones(active_frames)>peak_frames)peak_frames=$countones(active_frames);
    if(k3_work>1)dual_mac=dual_mac+1;if(k3_work>peak_k3)peak_k3=k3_work;
    if(send_frame>0 && send_frame<4 && frame_begin[send_frame]>=0 && !commit_pending)begin
     if(|operator_work)input_compute=input_compute+1;
     if(|operator_work[DW:0])input_mac=input_mac+1;
    end
    for(integer s=0;s<16;s++)begin
     if(buffer_allocate[s])allocs=allocs+1;
     if(buffer_release[s])begin if(external_hold[s])$fatal(1,"held output released");releases=releases+1;end
    end
    if(compute_done && compute_cycle==0)compute_cycle=cycle;
    if(trace)$fwrite(trace,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",cycle,send_frame,io_mem_req&&io_mem_gnt&&io_mem_we,frames_ready,unit_active,operator_work,mem_valid,mem_ready,mem_response,completed_count,result_valid,result_ready,result_frame,compute_done,done,buffer_live,active_frames,mem_write,unit_start);
   end
  end
 end
 task reset_metrics;
  begin
   checks=0;allocs=0;releases=0;results=0;compute_cycle=0;expanded=0;overlap_frames=0;dual_mac=0;input_compute=0;input_mac=0;io_write_compute=0;peak_frames=0;peak_k3=0;cpu_reads=0;multi_frame_work=0;cross_operator_work=0;
   for(integer k=0;k<NU;k++)begin launched[k]=0;active_cycles[k]=0;work_cycles[k]=0;read_bytes[k]=0;write_bytes[k]=0;wait_cycles[k]=0;end
   for(integer k=0;k<4;k++)begin frame_begin[k]=-1;frame_commit[k]=-1;frame_first[k]=-1;frame_result[k]=-1;end
   for(integer k=0;k<NT;k++)written[k]=0;
  end
 endtask
 task load_program;
  begin
   for(integer k=0;k<11;k++)begin
    @(negedge clk);if(!configuration_ready)$fatal(1,"configuration not ready");template_valid=1;template_index=k;
    for(integer b=0;b<16;b++)template_command[b*32+:32]=templates[k*16+b];
    template_source_modes=template_info[k*11];template_dep_valid=template_info[k*11+1];template_dep0=template_info[k*11+2];template_dep1=template_info[k*11+3];
    template_allocate_slot=template_info[k*11+4];template_hold_mask=template_info[k*11+5];template_use_valid=template_info[k*11+6];
    template_use_slots=template_info[k*11+7];template_use_owners=template_info[k*11+8];template_result_valid=template_info[k*11+9];template_result_bytes=template_info[k*11+10];
   end
   for(integer f=0;f<4;f++)begin
    @(negedge clk);template_valid=0;address_valid=1;address_slot=f;image_base=image_info[f*3];workspace_base=SLOT_BASE+4*f*SLOT_PITCH;address_frame=100+f;
   end
   @(negedge clk);address_valid=0;start=1;
   @(negedge clk);start=0;checking=1;
  end
 endtask
 initial begin
  if(!$value$plusargs("DATA=%s",data_dir))$fatal(1,"missing DATA");
  if(!$value$plusargs("MODE=%d",mode))mode=0;
  if(!$value$plusargs("PACE=%d",pace))pace=80;
  if($value$plusargs("ENABLE=%d",enable_mask))unit_enable=NU'(enable_mask);
  $readmemh({data_dir,"/memory.hex"},initial_mem);$readmemh({data_dir,"/expected.hex"},expected);
  $readmemh({data_dir,"/commands.hex"},commands);$readmemh({data_dir,"/metadata.hex"},meta);
  $readmemh({data_dir,"/images.hex"},images);$readmemh({data_dir,"/image_info.hex"},image_info);
  $readmemh({data_dir,"/template_commands.hex"},templates);$readmemh({data_dir,"/template_meta.hex"},template_info);
  if(mode==6)for(integer f=0;f<4;f++)for(integer b=0;b<147;b++)initial_mem[image_info[f*3]+b]=images[image_info[f*3+2]+b];
  events=$fopen("events.csv","w");$fwrite(events,"cycle,event,unit,node,frame\n");
  if(mode==0)begin trace=$fopen("trace.csv","w");$fwrite(trace,"cycle,input_frame,input_write,frames_ready,active,work,valid,ready,response,count,result_valid,result_ready,result_frame,compute_done,done,live,active_frames,write,start\n");end
  repeat(4)@(negedge clk);rst_n=1;
  // Initialize only fixture address space, through real CPU port A. Images
  // remain poison until later IO writes; never assign directly to SRAM arrays.
  for(integer a=0;a<INIT_BYTES;a=a+4)begin
   @(negedge clk);dmem_we=1;dmem_addr=a;dmem_wstrb=15;dmem_wdata={initial_mem[a+3],initial_mem[a+2],initial_mem[a+1],initial_mem[a]};
  end
  @(negedge clk);dmem_we=0;dmem_wstrb=0;
  reset_metrics();
  if(mode==5)unit_enable[0]=0;
  if(mode==4)begin templates[1]=NM+16-image_info[0];for(integer f=0;f<4;f++)commands[f*16+1]=image_info[f*3]+templates[1];end
  load_program();
  if(mode==3 || mode==4)begin
   if(mode==3)wait(send_frame==1 && send_offset>=32 && (|pending));else wait(memory_fault);
   @(negedge clk);checking=0;clear=1;dmem_re=0;dmem_we=0;
   if(mode==4)begin rst_n=0;templates[1]=0;for(integer f=0;f<4;f++)commands[f*16+1]=image_info[f*3];end
   repeat(4)@(negedge clk);rst_n=1;clear=0;
   reset_metrics();load_program();
  end
  while(!done)begin
   @(negedge clk);if(error)$fatal(1,"unexpected CNN error cycle%0d",cycle);
   if(cycle>2000000)$fatal(1,"watchdog completed%0d frames%h live%h",completed_count,frames_ready,buffer_live);
  end
  repeat(2)@(negedge clk);checking=0;dmem_re=0;
  if(expanded!=44 || checks!=28812 || allocs!=44 || releases!=44 || results!=4 || result_seen!=15 || (|pending))$fatal(1,"incomplete checks %0d alloc%0d free%0d results%0d expanded%0d",checks,allocs,releases,results,expanded);
  if(mode==1)begin if(overlap_frames!=0)$fatal(1,"serial mode overlapped frames");end
  else if(overlap_frames==0 || dual_mac==0 || multi_frame_work==0 || cross_operator_work==0 || (mode!=6 && (input_compute==0 || input_mac==0 || io_write_compute==0)))$fatal(1,"missing real input/compute overlap");
  for(integer f=0;f<4;f++)begin
   if(frame_first[f]<=frame_commit[f] || frame_result[f]<=frame_first[f])$fatal(1,"frame lifecycle order");
   if(f>0 && frame_begin[f]<=frame_commit[f-1])$fatal(1,"images not sequential");
  end
  for(integer a=0;a<SLOT_BASE;a++)begin
   reg [7:0] want;want=initial_mem[a];
   for(integer f=0;f<4;f++)if(a>=image_info[f*3] && a<image_info[f*3]+image_info[f*3+1])want=images[image_info[f*3+2]+a-image_info[f*3]];
   if(peek(a)!==want)$fatal(1,"input/readonly corrupted addr%0d",a);
  end
  for(integer s=0;s<16;s++)for(integer b=SLOT_BYTES;b<SLOT_PITCH;b++)if(peek(SLOT_BASE+s*SLOT_PITCH+b)!==8'ha5)$fatal(1,"guard overwritten");
  fd=$fopen("outputs.hex","w");for(integer b=0;b<32;b++)$fwrite(fd,"%02x\n",outputs[b]);$fclose(fd);
  fd=$fopen("metrics.json","w");
  $fwrite(fd,"{\"status\":\"PASS\",\"mode\":%0d,\"cycles\":%0d,\"checked_bytes\":%0d,\"allocations\":%0d,\"releases\":%0d,\"results\":%0d,\"multi_frame_cycles\":%0d,\"multi_k3_mac_cycles\":%0d,\"peak_active_frames\":%0d,\"peak_simultaneous_k3_mac\":%0d,\"input_compute_cycles\":%0d,\"input_mac_cycles\":%0d,\"input_write_compute_cycles\":%0d,\"cpu_reads\":%0d,\"compute_done_cycle\":%0d,\"frames\":[",mode,cycle,checks,allocs,releases,results,overlap_frames,dual_mac,peak_frames,peak_k3,input_compute,input_mac,io_write_compute,cpu_reads,compute_cycle);
  for(integer f=0;f<4;f++)$fwrite(fd,"%s{\"frame\":%0d,\"input_begin\":%0d,\"input_commit\":%0d,\"first_launch\":%0d,\"read_complete\":%0d}",f==0?"":",",100+f,frame_begin[f],frame_commit[f],frame_first[f],frame_result[f]);
  $fwrite(fd,"],\"multi_frame_work_cycles\":%0d,\"cross_operator_work_cycles\":%0d,\"expanded_commands\":%0d,\"units\":[",multi_frame_work,cross_operator_work,expanded);
  for(integer k=0;k<NU;k++)$fwrite(fd,"%s{\"unit\":%0d,\"tasks\":%0d,\"active_cycles\":%0d,\"work_cycles\":%0d,\"read_bytes\":%0d,\"write_bytes\":%0d,\"arbitration_wait_cycles\":%0d}",k==0?"":",",k,launched[k],active_cycles[k],work_cycles[k],read_bytes[k],write_bytes[k],wait_cycles[k]);
  $fwrite(fd,"]}\n");$fclose(fd);$fclose(events);if(trace)$fclose(trace);
  $display("PASS SELF_STREAM K3=%0d K1=%0d POST=%0d mode=%0d cycles=%0d overlap=%0d",K3_UNITS,K1_UNITS,POST_UNITS,mode,cycle,overlap_frames);$finish;
 end
endmodule
