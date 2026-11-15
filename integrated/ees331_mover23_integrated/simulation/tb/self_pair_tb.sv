`timescale 1ns/1ps
// Memory fabric/checker only: all arithmetic is performed by synthesizable RTL.
module self_pair_tb;
 localparam N=64, IW=6, NM=65536, NT=22, SLOT_BASE=32768, SLOT_PITCH=2112, SLOT_BYTES=2048;
 logic clk=0; always #5 clk=~clk;
 logic rst_n=0,clear=0,start=0,memory_fault=0;
 logic [1:0] engine_enable=3;
 logic program_valid=0; logic [IW-1:0] program_index=0,program_dep0=0,program_dep1=0;
 logic [511:0] program_command=0; logic [1:0] program_dep_valid=0;
 logic [IW:0] task_count=NT;
 logic program_allocate_valid=1; logic [2:0] program_allocate_slot=0;
 logic [N-1:0] program_hold_mask=0;
 logic [2:0] program_use_valid=0; logic [8:0] program_use_slots=0; logic [3*IW-1:0] program_use_owners=0;
 logic program_result_valid=0; logic [31:0] program_result_frame=0,program_result_addr=0,program_result_bytes=0;
 logic result_ready=0;
 wire result_valid,result_accept,outputs_pending,compute_done;
 wire [31:0] result_frame,result_addr,result_bytes; wire [7:0] result_error,external_hold;
 wire [7:0] buffer_live,buffer_release,buffer_allocate;
 wire [8*IW-1:0] buffer_owners; wire wait_buffer;
 wire program_ready,busy,done,error,cancel;
 wire [6:0] mem_valid,mem_write,mem_byte;
 wire [223:0] mem_addr,mem_wdata;
 logic [6:0] mem_ready=0,mem_response=0; logic [223:0] mem_rdata=0;
 wire [6:0] unit_start,unit_active,completion_pulse,operator_busy,operator_work;
 wire [6:0][IW-1:0] unit_node;
 wire [IW:0] completed_count; wire [N-1:0] completed_mask;
 wire [2:0][31:0] conv_input_reads,conv_weight_reads,conv_mac_count;
 wire dw7_mac;
 self_network_top dut(.*);
 reg [7:0] mem[0:NM-1],initial_mem[0:NM-1],expected[0:32767],output_bytes[0:15];
 reg [31:0] commands[0:NT*16-1],meta[0:NT*14-1];
 logic [6:0] pending=0, pwrite=0,pbyte=0,held=0;
 integer delay_left[7],pa[7],pd[7],pn[7];
 reg [65:0] held_fields[7];
 reg [2047:0] written[NT];
 integer launched[7],reads[7],writes[7],works[7],job_reads[NT],job_weights[NT],job_macs[NT];
 integer cycle=0,mode=0,round_robin=0,checks=0,dual_mac=0,cross_work=0,allocs=0,releases=0,results=0;
 integer read_wait=0,read_index=0,last_frame=0,last_addr=0,last_bytes=0,reader_node=0;
 integer compute_cycle=0,wait_buffer_cycles=0,fd,events,trace;
 logic checking=0,reading=0,finished_reader=0;
 string data_dir,mode_name;
 reg [3:0] banks;
 integer u,b,a,n,j,node;

 always_comb begin
  mem_ready=0;banks=0;
  for(integer q=0;q<7;q++)begin
   integer k,bank;
   k=(round_robin+q)%7;bank=(mem_addr[k*32+:32]>>2)%4;
   if(!cancel && rst_n && mem_valid[k] && !pending[k] && !banks[bank] &&
     (mode==0 || mode==2 || mode==3 || ((cycle+k*3)%7!=0 && (cycle+k)%11!=0)) &&
     !(mode==4 && k==0 && cycle%13<9))begin
    mem_ready[k]=1;banks[bank]=1;
   end
  end
 end

 always @(posedge clk)begin
  mem_response<=0;
  if(!rst_n || cancel)begin pending<=0;held<=0;end
  else begin
   // Nonblocking: ready arbitration must remain stable throughout this edge
   // while the DUT and fabric independently sample valid && ready.
   cycle<=cycle+1;round_robin<=(round_robin+1)%7;
   for(integer k=0;k<7;k++)begin
    if(held[k] && (!mem_valid[k] || held_fields[k]!=={mem_write[k],mem_byte[k],mem_addr[k*32+:32],mem_wdata[k*32+:32]}))
      $fatal(1,"unstable stalled request unit %0d",k);
    held[k]=mem_valid[k] && !mem_ready[k];
    held_fields[k]={mem_write[k],mem_byte[k],mem_addr[k*32+:32],mem_wdata[k*32+:32]};
    if(pending[k])begin
     if(delay_left[k]>0)delay_left[k]=delay_left[k]-1;
     else begin
      if(pwrite[k])begin
       for(integer z=0;z<(pbyte[k]?1:4);z++)begin
        if(written[pn[k]][pa[k]+z-meta[pn[k]*14+11]])$fatal(1,"duplicate write node %0d",pn[k]);
        written[pn[k]][pa[k]+z-meta[pn[k]*14+11]]=1;
        mem[pa[k]+z]=(pd[k]>>(8*z))&255;
       end
       writes[k]=writes[k]+(pbyte[k]?1:4);
      end else begin
       mem_rdata[k*32+:32]<=pbyte[k]?{24'b0,mem[pa[k]]}:{mem[pa[k]+3],mem[pa[k]+2],mem[pa[k]+1],mem[pa[k]]};
       reads[k]=reads[k]+(pbyte[k]?1:4);
      end
      mem_response[k]<=1;pending[k]<=0;
     end
    end
    if(mem_valid[k] && mem_ready[k])begin
     if(pending[k])$fatal(1,"more than one transaction on port");
     pa[k]=mem_addr[k*32+:32];pd[k]=mem_wdata[k*32+:32];pn[k]=unit_node[k];
     if(pa[k]<0 || pa[k]+(mem_byte[k]?1:4)>NM || (!mem_byte[k] && pa[k]%4))$fatal(1,"invalid address %0d unit%0d",pa[k],k);
     if(mem_write[k] && (!unit_active[k] || pa[k]<meta[pn[k]*14+11] || pa[k]+(mem_byte[k]?1:4)>meta[pn[k]*14+11]+meta[pn[k]*14+12]))$fatal(1,"write outside assigned output unit%0d node%0d addr%0d",k,pn[k],pa[k]);
     pending[k]<=1;pwrite[k]<=mem_write[k];pbyte[k]<=mem_byte[k];
     delay_left[k]=(mode==0 || mode==2 || mode==3)?0:(cycle+k)%5;
     if(mode==4 && k==0)delay_left[k]=delay_left[k]+9;
    end
   end
  end
  if(checking && !cancel)begin
   if(error)$fatal(1,"unexpected global error");
   if(operator_work[0] && operator_work[1])dual_mac=dual_mac+1;
   if((|operator_work[3:0]) && (|operator_work[6:4]))cross_work=cross_work+1;
   if(wait_buffer)wait_buffer_cycles=wait_buffer_cycles+1;
   if(compute_done && compute_cycle==0)compute_cycle=cycle;
   if(trace && mode==0)$fwrite(trace,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",cycle,unit_start,unit_active,operator_work,mem_valid,mem_ready,mem_response,completion_pulse,completed_count,buffer_live,result_valid,result_ready,compute_done,done,mem_write,result_frame,result_accept);
   for(integer k=0;k<7;k++)begin
    if(operator_work[k])works[k]=works[k]+1;
    if(unit_start[k])begin
     launched[k]=launched[k]+1;
     $fwrite(events,"%0d,launch,%0d,%0d,%0d\n",cycle,k,unit_node[k],meta[unit_node[k]*14+10]);
    end
    if(completion_pulse[k])begin
     node=unit_node[k];a=meta[node*14+11];n=meta[node*14+12];j=meta[node*14+13];
     if(pending[k] || mem_valid[k])$fatal(1,"completion before final transaction drained");
     for(integer z=0;z<n;z++)begin
      if(!written[node][z] || mem[a+z]!==expected[j+z])$fatal(1,"mismatch node=%0d unit=%0d offset=%0d actual=%0d expected=%0d",node,k,z,mem[a+z],expected[j+z]);
     end
     checks=checks+n;
     if(k<3)begin job_reads[node]=conv_input_reads[k];job_weights[node]=conv_weight_reads[k];job_macs[node]=conv_mac_count[k];end
     $fwrite(events,"%0d,done,%0d,%0d,%0d\n",cycle,k,node,meta[node*14+10]);
    end
   end
   for(integer s=0;s<8;s++)begin
    if(buffer_allocate[s])allocs=allocs+1;
    if(buffer_release[s])begin
     if(external_hold[s])$fatal(1,"released externally held result");
     releases=releases+1;
     for(integer z=0;z<SLOT_BYTES;z++)mem[SLOT_BASE+s*SLOT_PITCH+z]=8'hd7;
    end
   end
   if(result_valid && !reading)begin
    if(result_frame<100 || result_frame>101 || result_bytes!=8 || result_error)$fatal(1,"bad result descriptor");
    reading=1;finished_reader=0;last_frame=result_frame;last_addr=result_addr;last_bytes=result_bytes;read_index=0;
    read_wait=(mode==1)?50000:25;reader_node=20+(result_frame-100);
    if(result_addr!=meta[reader_node*14+11])$fatal(1,"result address belongs to wrong frame");
   end
   if(reading && !result_accept)begin
    if(!result_valid || result_frame!=last_frame || result_addr!=last_addr || result_bytes!=last_bytes)$fatal(1,"descriptor changed before reader ACK");
   end
   if(reading && !finished_reader)begin
    if(read_wait>0)read_wait=read_wait-1;
    else if(cycle%7==0)begin
     if(mem[last_addr+read_index]!==expected[meta[reader_node*14+13]+read_index])$fatal(1,"external result data changed");
     output_bytes[(last_frame-100)*8+read_index]=mem[last_addr+read_index];
     read_index=read_index+1;
     if(read_index==last_bytes)begin result_ready<=1;finished_reader=1;end
    end
   end
   if(result_valid && result_ready)begin results=results+1;result_ready<=0;end
   if(result_accept)begin reading=0;finished_reader=0;end
  end
 end

 task reset_state;
  begin
   checking=0;clear=1;program_valid=0;start=0;memory_fault=0;result_ready=0;
   repeat(3)@(negedge clk);
   clear=0;cycle=0;checks=0;dual_mac=0;cross_work=0;allocs=0;releases=0;results=0;reading=0;finished_reader=0;read_wait=0;compute_cycle=0;wait_buffer_cycles=0;
   for(integer k=0;k<NM;k++)mem[k]=initial_mem[k];
   for(integer k=0;k<NT;k++)begin written[k]=0;job_reads[k]=0;job_weights[k]=0;job_macs[k]=0;end
   for(integer k=0;k<7;k++)begin launched[k]=0;reads[k]=0;writes[k]=0;works[k]=0;end
  end
 endtask
 task load_program;
  begin
   for(integer k=0;k<NT;k++)begin
    @(negedge clk);
    if(!program_ready)$fatal(1,"program not ready");
    program_valid=1;program_index=k;
    for(integer z=0;z<16;z++)program_command[z*32+:32]=commands[k*16+z];
    program_dep_valid=meta[k*14];program_dep0=meta[k*14+1];program_dep1=meta[k*14+2];
    program_allocate_slot=meta[k*14+3];program_hold_mask={meta[k*14+5],meta[k*14+4]};
    program_use_valid=meta[k*14+6];program_use_slots=meta[k*14+7];program_use_owners=meta[k*14+8];
    program_result_valid=meta[k*14+9];program_result_frame=meta[k*14+10];program_result_addr=meta[k*14+11];program_result_bytes=meta[k*14+12];
   end
   @(negedge clk);program_valid=0;start=1;
   @(negedge clk);start=0;checking=1;
  end
 endtask
 initial begin
  if(!$value$plusargs("DATA=%s",data_dir))$fatal(1,"missing DATA");
  if(!$value$plusargs("MODE=%d",mode))mode=0;
  $readmemh({data_dir,"/memory.hex"},initial_mem);
  $readmemh({data_dir,"/commands.hex"},commands);
  $readmemh({data_dir,"/metadata.hex"},meta);
  $readmemh({data_dir,"/expected.hex"},expected);
  events=$fopen("events.csv","w");$fwrite(events,"cycle,event,unit,node,frame\n");
  trace=0;
  if(mode==0)begin trace=$fopen("trace.csv","w");$fwrite(trace,"cycle,start,active,work,valid,ready,response,complete,count,live,result_valid,result_ready,compute_done,done,write,result_frame,result_accept\n");end
  repeat(4)@(negedge clk);rst_n=1;
  reset_state();engine_enable=(mode==2)?1:((mode==3)?2:3);
  if(mode==7 || mode==8 || mode==9)begin
   @(negedge clk);program_valid=1;program_index=0;program_command=0;
   program_dep_valid=(mode==8)?1:0;program_dep0=0;
   program_result_valid=(mode==9);program_result_bytes=0;
   if(mode==7)program_command[31:0]=99;
   repeat(4)@(negedge clk);program_valid=0;
   if(!error || !cancel)$fatal(1,"invalid descriptor was not rejected");
   reset_state();
  end
  if(mode==5 || mode==6)begin
   load_program();wait((|pending) && completed_count>=2);
   @(negedge clk);checking=0;
   if(mode==6)begin
    memory_fault=1;repeat(3)@(negedge clk);
    if(!error || !cancel || result_valid)$fatal(1,"memory fault cancellation failed");
   end
   reset_state();
  end
  load_program();
  while(!done)begin
   @(negedge clk);
   if(error)$fatal(1,"unexpected error cycle%0d",cycle);
   if(cycle>3000000)$fatal(1,"watchdog count%0d live%h active%h",completed_count,buffer_live,unit_active);
  end
  repeat(2)@(negedge clk);checking=0;
  if(results!=2 || allocs!=NT || releases!=NT || completed_count!=NT || (|pending))$fatal(1,"end counts results%0d alloc%0d release%0d completed%0d",results,allocs,releases,completed_count);
  if(mode!=2 && mode!=3 && (dual_mac==0 || launched[0]==0 || launched[1]==0))$fatal(1,"no real dual MAC overlap");
  if(cross_work==0)$fatal(1,"no cross-class effective work overlap");
  if(mode==2 && launched[1]!=0)$fatal(1,"disabled engine1 used");
  if(mode==3 && launched[0]!=0)$fatal(1,"disabled engine0 used");
  for(integer k=2;k<7;k++)if(launched[k]==0)$fatal(1,"unused operator%0d",k);
  for(integer k=0;k<SLOT_BASE;k++)if(mem[k]!==initial_mem[k])$fatal(1,"readonly memory corrupted");
  for(integer s=0;s<8;s++)for(integer k=SLOT_BYTES;k<SLOT_PITCH;k++)if(mem[SLOT_BASE+s*SLOT_PITCH+k]!==8'ha5)$fatal(1,"slot guard corrupted");
  fd=$fopen("outputs.hex","w");for(integer k=0;k<16;k++)$fwrite(fd,"%02x\n",output_bytes[k]);$fclose(fd);
  fd=$fopen("metrics.json","w");
  $fwrite(fd,"{\"status\":\"PASS\",\"mode\":%0d,\"cycles\":%0d,\"checked_bytes\":%0d,\"dual_mac_cycles\":%0d,\"cross_work_cycles\":%0d,\"allocations\":%0d,\"releases\":%0d,\"results\":%0d,\"compute_done_cycle\":%0d,\"wait_buffer_cycles\":%0d,\"units\":[",mode,cycle,checks,dual_mac,cross_work,allocs,releases,results,compute_cycle,wait_buffer_cycles);
  for(integer k=0;k<7;k++)$fwrite(fd,"%s{\"unit\":%0d,\"tasks\":%0d,\"read_bytes\":%0d,\"write_bytes\":%0d,\"work_cycles\":%0d}",k==0?"":",",k,launched[k],reads[k],writes[k],works[k]);
  $fwrite(fd,"],\"conv_jobs\":[");
  b=0;
  for(integer k=0;k<NT;k++)if(job_macs[k]>0)begin
   $fwrite(fd,"%s{\"node\":%0d,\"input_bytes\":%0d,\"weight_bytes\":%0d,\"macs\":%0d}",b==0?"":",",k,job_reads[k],job_weights[k],job_macs[k]);b=b+1;
  end
  $fwrite(fd,"]}\n");$fclose(fd);$fclose(events);if(trace)$fclose(trace);
  $display("PASS SELF_PAIR mode=%0d cycles=%0d checked=%0d dual_mac=%0d cross=%0d",mode,cycle,checks,dual_mac,cross_work);
  $finish;
 end
endmodule
