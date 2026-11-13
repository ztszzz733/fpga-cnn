// Simulation-only direct RTL control sampling. No datapath or RTL behavior changes.
// Samples settled values 1 ns after each clock edge. Detailed windows are marked;
// outside them the detailed nets are explicitly X (not retained fake values).
integer trace_fd, marker_fd;
longint trace_until=600;
bit trace_capture, trace_initialized=0;
bit [31:0] first_read_seen=0, first_write_seen=0;
bit hci_write_seen=0;
initial begin
 trace_fd=$fopen("controls.vcd","w");
 marker_fd=$fopen("control_markers.csv","w");
 $fwrite(marker_fd,"time_ns,cycle,event,task,lane,address,data\n");
 $fwrite(trace_fd,"$timescale 1ns $end\n$scope module control $end\n");
 $fwrite(trace_fd,"$var wire 1 s0 rst_n $end\n");
 $fwrite(trace_fd,"$var wire 3 s1 queue_state $end\n");
 $fwrite(trace_fd,"$var wire 32 s2 task_index $end\n");
 $fwrite(trace_fd,"$var wire 4 s3 task_opcode $end\n");
 $fwrite(trace_fd,"$var wire 1 s4 task_launch $end\n");
 $fwrite(trace_fd,"$var wire 1 s5 status_busy $end\n");
 $fwrite(trace_fd,"$var wire 1 s6 status_done $end\n");
 $fwrite(trace_fd,"$var wire 1 s7 status_error $end\n");
 $fwrite(trace_fd,"$var wire 4 s8 wrapper_state $end\n");
 $fwrite(trace_fd,"$var wire 1 s9 core_busy $end\n");
 $fwrite(trace_fd,"$var wire 6 s10 core_state $end\n");
 $fwrite(trace_fd,"$var wire 1 s11 dma_busy $end\n");
 $fwrite(trace_fd,"$var wire 6 s12 scalar_busy $end\n");
 $fwrite(trace_fd,"$var wire 1 s13 memory_idle $end\n");
 $fwrite(trace_fd,"$var wire 1 s14 detail_valid $end\n");
 $fwrite(trace_fd,"$var wire 1 s15 clk $end\n");
 $fwrite(trace_fd,"$var wire 1 s16 mmio_we $end\n");
 $fwrite(trace_fd,"$var wire 1 s17 mmio_re $end\n");
 $fwrite(trace_fd,"$var wire 1 s18 mmio_ready $end\n");
 $fwrite(trace_fd,"$var wire 32 s19 mmio_addr $end\n");
 $fwrite(trace_fd,"$var wire 32 s20 mmio_wdata $end\n");
 $fwrite(trace_fd,"$var wire 1 s21 cfg_req $end\n");
 $fwrite(trace_fd,"$var wire 1 s22 cfg_ready $end\n");
 $fwrite(trace_fd,"$var wire 1 s23 cfg_response $end\n");
 $fwrite(trace_fd,"$var wire 1 s24 hci_req $end\n");
 $fwrite(trace_fd,"$var wire 1 s25 hci_gnt $end\n");
 $fwrite(trace_fd,"$var wire 1 s26 hci_wen $end\n");
 $fwrite(trace_fd,"$var wire 1 s27 hci_rvalid $end\n");
 $fwrite(trace_fd,"$var wire 1 s28 hci_rready $end\n");
 $fwrite(trace_fd,"$var wire 32 s29 hci_addr $end\n");
 $fwrite(trace_fd,"$var wire 36 s30 hci_be $end\n");
 $fwrite(trace_fd,"$var wire 11 s31 cnn_req $end\n");
 $fwrite(trace_fd,"$var wire 11 s32 cnn_gnt $end\n");
 $fwrite(trace_fd,"$var wire 11 s33 cnn_write $end\n");
 $fwrite(trace_fd,"$var wire 11 s34 cnn_byte $end\n");
 $fwrite(trace_fd,"$var wire 11 s35 cnn_response $end\n");
 $fwrite(trace_fd,"$var wire 32 s36 lane0_addr $end\n");
 $fwrite(trace_fd,"$var wire 32 s37 lane0_wdata $end\n");
 $fwrite(trace_fd,"$var wire 32 s38 lane0_rdata $end\n");
 $fwrite(trace_fd,"$var wire 32 s39 dma_cfg_addr $end\n");
 $fwrite(trace_fd,"$var wire 32 s40 dma_cfg_wdata $end\n");
 $fwrite(trace_fd,"$var wire 32 s41 post_addr $end\n");
 $fwrite(trace_fd,"$var wire 32 s42 post_wdata $end\n");
 $fwrite(trace_fd,"$var wire 9 s43 bridge_pending $end\n");
 $fwrite(trace_fd,"$var wire 1 s44 mem_fault $end\n");
 $fwrite(trace_fd,"$var wire 1 s45 cpu_store $end\n");
 $fwrite(trace_fd,"$var wire 32 s46 cpu_store_addr $end\n");
 $fwrite(trace_fd,"$var wire 32 s47 cpu_store_data $end\n");
 $fwrite(trace_fd,"$upscope $end\n$enddefinitions $end\n");
end
always @(posedge clk) if(rst_n) begin
 if(cnn.launch) begin
  trace_until=cycles+600;
  $fwrite(marker_fd,"%0d,%0d,dispatch,%0d,-1,0,0\n",$time/1ns,cycles,task_index);
 end
 if(cnn.convolution.tcdm.req && !cnn.convolution.tcdm.wen && !hci_write_seen) begin
  hci_write_seen=1;trace_until=cycles+400;
  $fwrite(marker_fd,"%0d,%0d,first_hci_store,%0d,-1,%h,0\n",$time/1ns,cycles,task_index,cnn.convolution.tcdm.add);
 end
 for(int lane=0;lane<11;lane++) if(cnn_valid[lane] && cnn_ready[lane] && task_index<32) begin
  if(!cnn_write[lane] && !first_read_seen[task_index]) begin
   first_read_seen[task_index]=1;
   $fwrite(marker_fd,"%0d,%0d,first_sram_read,%0d,%0d,%h,0\n",$time/1ns,cycles,task_index,lane,cnn_addr[lane*32+:32]);
  end
  if(cnn_write[lane] && !first_write_seen[task_index]) begin
   first_write_seen[task_index]=1;trace_until=cycles+400;
   $fwrite(marker_fd,"%0d,%0d,first_sram_write,%0d,%0d,%h,%h\n",$time/1ns,cycles,task_index,lane,cnn_addr[lane*32+:32],cnn_wdata[lane*32+:32]);
  end
 end
 if(status_done) begin
  trace_until=cycles+300;
  $fwrite(marker_fd,"%0d,%0d,all_done,%0d,-1,0,0\n",$time/1ns,cycles,task_index);
 end
 if(dmem_we && dmem_addr==32'h80)
  $fwrite(marker_fd,"%0d,%0d,cpu_completion,%0d,-1,%h,%h\n",$time/1ns,cycles,task_index,dmem_addr,dmem_wdata);
end
logic [0:0] trace_prev_s0, trace_now_s0;
logic [2:0] trace_prev_s1, trace_now_s1;
logic [31:0] trace_prev_s2, trace_now_s2;
logic [3:0] trace_prev_s3, trace_now_s3;
logic [0:0] trace_prev_s4, trace_now_s4;
logic [0:0] trace_prev_s5, trace_now_s5;
logic [0:0] trace_prev_s6, trace_now_s6;
logic [0:0] trace_prev_s7, trace_now_s7;
logic [3:0] trace_prev_s8, trace_now_s8;
logic [0:0] trace_prev_s9, trace_now_s9;
logic [5:0] trace_prev_s10, trace_now_s10;
logic [0:0] trace_prev_s11, trace_now_s11;
logic [5:0] trace_prev_s12, trace_now_s12;
logic [0:0] trace_prev_s13, trace_now_s13;
logic [0:0] trace_prev_s14, trace_now_s14;
logic [0:0] trace_prev_s15, trace_now_s15;
logic [0:0] trace_prev_s16, trace_now_s16;
logic [0:0] trace_prev_s17, trace_now_s17;
logic [0:0] trace_prev_s18, trace_now_s18;
logic [31:0] trace_prev_s19, trace_now_s19;
logic [31:0] trace_prev_s20, trace_now_s20;
logic [0:0] trace_prev_s21, trace_now_s21;
logic [0:0] trace_prev_s22, trace_now_s22;
logic [0:0] trace_prev_s23, trace_now_s23;
logic [0:0] trace_prev_s24, trace_now_s24;
logic [0:0] trace_prev_s25, trace_now_s25;
logic [0:0] trace_prev_s26, trace_now_s26;
logic [0:0] trace_prev_s27, trace_now_s27;
logic [0:0] trace_prev_s28, trace_now_s28;
logic [31:0] trace_prev_s29, trace_now_s29;
logic [35:0] trace_prev_s30, trace_now_s30;
logic [10:0] trace_prev_s31, trace_now_s31;
logic [10:0] trace_prev_s32, trace_now_s32;
logic [10:0] trace_prev_s33, trace_now_s33;
logic [10:0] trace_prev_s34, trace_now_s34;
logic [10:0] trace_prev_s35, trace_now_s35;
logic [31:0] trace_prev_s36, trace_now_s36;
logic [31:0] trace_prev_s37, trace_now_s37;
logic [31:0] trace_prev_s38, trace_now_s38;
logic [31:0] trace_prev_s39, trace_now_s39;
logic [31:0] trace_prev_s40, trace_now_s40;
logic [31:0] trace_prev_s41, trace_now_s41;
logic [31:0] trace_prev_s42, trace_now_s42;
logic [8:0] trace_prev_s43, trace_now_s43;
logic [0:0] trace_prev_s44, trace_now_s44;
logic [0:0] trace_prev_s45, trace_now_s45;
logic [31:0] trace_prev_s46, trace_now_s46;
logic [31:0] trace_prev_s47, trace_now_s47;
bit trace_changed, trace_previous_capture=0;
always @(clk) begin
 #1;
 trace_capture=cycles<=trace_until;
 trace_changed=!trace_initialized || trace_capture != trace_previous_capture;
 trace_now_s0=rst_n;
 trace_changed |= trace_now_s0 !== trace_prev_s0;
 trace_now_s1=cnn.state;
 trace_changed |= trace_now_s1 !== trace_prev_s1;
 trace_now_s2=task_index;
 trace_changed |= trace_now_s2 !== trace_prev_s2;
 trace_now_s3=task_opcode;
 trace_changed |= trace_now_s3 !== trace_prev_s3;
 trace_now_s4=cnn.launch;
 trace_changed |= trace_now_s4 !== trace_prev_s4;
 trace_now_s5=status_busy;
 trace_changed |= trace_now_s5 !== trace_prev_s5;
 trace_now_s6=status_done;
 trace_changed |= trace_now_s6 !== trace_prev_s6;
 trace_now_s7=status_error;
 trace_changed |= trace_now_s7 !== trace_prev_s7;
 trace_now_s8=cnn.convolution.state;
 trace_changed |= trace_now_s8 !== trace_prev_s8;
 trace_now_s9=core_active;
 trace_changed |= trace_now_s9 !== trace_prev_s9;
 trace_now_s10=core_state;
 trace_changed |= trace_now_s10 !== trace_prev_s10;
 trace_now_s11=cnn.lbusy;
 trace_changed |= trace_now_s11 !== trace_prev_s11;
 trace_now_s12=cnn.sbusy;
 trace_changed |= trace_now_s12 !== trace_prev_s12;
 trace_now_s13=cnn.memory_idle;
 trace_changed |= trace_now_s13 !== trace_prev_s13;
 trace_now_s14=trace_capture;
 trace_changed |= trace_now_s14 !== trace_prev_s14;
 trace_now_s15=trace_capture ? clk : 'x;
 trace_changed |= trace_now_s15 !== trace_prev_s15;
 trace_now_s16=trace_capture ? mmio_we : 'x;
 trace_changed |= trace_now_s16 !== trace_prev_s16;
 trace_now_s17=trace_capture ? mmio_re : 'x;
 trace_changed |= trace_now_s17 !== trace_prev_s17;
 trace_now_s18=trace_capture ? mmio_ready : 'x;
 trace_changed |= trace_now_s18 !== trace_prev_s18;
 trace_now_s19=trace_capture ? mmio_addr : 'x;
 trace_changed |= trace_now_s19 !== trace_prev_s19;
 trace_now_s20=trace_capture ? mmio_wdata : 'x;
 trace_changed |= trace_now_s20 !== trace_prev_s20;
 trace_now_s21=trace_capture ? cnn.cv : 'x;
 trace_changed |= trace_now_s21 !== trace_prev_s21;
 trace_now_s22=trace_capture ? cnn_ready[9] : 'x;
 trace_changed |= trace_now_s22 !== trace_prev_s22;
 trace_now_s23=trace_capture ? cnn_response[9] : 'x;
 trace_changed |= trace_now_s23 !== trace_prev_s23;
 trace_now_s24=trace_capture ? cnn.convolution.tcdm.req : 'x;
 trace_changed |= trace_now_s24 !== trace_prev_s24;
 trace_now_s25=trace_capture ? cnn.convolution.tcdm.gnt : 'x;
 trace_changed |= trace_now_s25 !== trace_prev_s25;
 trace_now_s26=trace_capture ? cnn.convolution.tcdm.wen : 'x;
 trace_changed |= trace_now_s26 !== trace_prev_s26;
 trace_now_s27=trace_capture ? cnn.convolution.tcdm.r_valid : 'x;
 trace_changed |= trace_now_s27 !== trace_prev_s27;
 trace_now_s28=trace_capture ? cnn.convolution.tcdm.r_ready : 'x;
 trace_changed |= trace_now_s28 !== trace_prev_s28;
 trace_now_s29=trace_capture ? cnn.convolution.tcdm.add : 'x;
 trace_changed |= trace_now_s29 !== trace_prev_s29;
 trace_now_s30=trace_capture ? cnn.convolution.tcdm.be : 'x;
 trace_changed |= trace_now_s30 !== trace_prev_s30;
 trace_now_s31=trace_capture ? cnn_valid : 'x;
 trace_changed |= trace_now_s31 !== trace_prev_s31;
 trace_now_s32=trace_capture ? cnn_ready : 'x;
 trace_changed |= trace_now_s32 !== trace_prev_s32;
 trace_now_s33=trace_capture ? cnn_write : 'x;
 trace_changed |= trace_now_s33 !== trace_prev_s33;
 trace_now_s34=trace_capture ? cnn_byte : 'x;
 trace_changed |= trace_now_s34 !== trace_prev_s34;
 trace_now_s35=trace_capture ? cnn_response : 'x;
 trace_changed |= trace_now_s35 !== trace_prev_s35;
 trace_now_s36=trace_capture ? cnn_addr[0+:32] : 'x;
 trace_changed |= trace_now_s36 !== trace_prev_s36;
 trace_now_s37=trace_capture ? cnn_wdata[0+:32] : 'x;
 trace_changed |= trace_now_s37 !== trace_prev_s37;
 trace_now_s38=trace_capture ? cnn_rdata[0+:32] : 'x;
 trace_changed |= trace_now_s38 !== trace_prev_s38;
 trace_now_s39=trace_capture ? cnn_addr[288+:32] : 'x;
 trace_changed |= trace_now_s39 !== trace_prev_s39;
 trace_now_s40=trace_capture ? cnn_wdata[288+:32] : 'x;
 trace_changed |= trace_now_s40 !== trace_prev_s40;
 trace_now_s41=trace_capture ? cnn_addr[320+:32] : 'x;
 trace_changed |= trace_now_s41 !== trace_prev_s41;
 trace_now_s42=trace_capture ? cnn_wdata[320+:32] : 'x;
 trace_changed |= trace_now_s42 !== trace_prev_s42;
 trace_now_s43=trace_capture ? cnn.convolution.bridge.pending : 'x;
 trace_changed |= trace_now_s43 !== trace_prev_s43;
 trace_now_s44=trace_capture ? cnn_mem_fault : 'x;
 trace_changed |= trace_now_s44 !== trace_prev_s44;
 trace_now_s45=trace_capture ? dmem_we : 'x;
 trace_changed |= trace_now_s45 !== trace_prev_s45;
 trace_now_s46=trace_capture ? dmem_addr : 'x;
 trace_changed |= trace_now_s46 !== trace_prev_s46;
 trace_now_s47=trace_capture ? dmem_wdata : 'x;
 trace_changed |= trace_now_s47 !== trace_prev_s47;
 if(trace_changed) begin
  $fwrite(trace_fd,"#%0d\n",$time/1ns);
  if(!trace_initialized || trace_now_s0 !== trace_prev_s0) $fwrite(trace_fd,"b%b s0\n",trace_now_s0);
  if(!trace_initialized || trace_now_s1 !== trace_prev_s1) $fwrite(trace_fd,"b%b s1\n",trace_now_s1);
  if(!trace_initialized || trace_now_s2 !== trace_prev_s2) $fwrite(trace_fd,"b%b s2\n",trace_now_s2);
  if(!trace_initialized || trace_now_s3 !== trace_prev_s3) $fwrite(trace_fd,"b%b s3\n",trace_now_s3);
  if(!trace_initialized || trace_now_s4 !== trace_prev_s4) $fwrite(trace_fd,"b%b s4\n",trace_now_s4);
  if(!trace_initialized || trace_now_s5 !== trace_prev_s5) $fwrite(trace_fd,"b%b s5\n",trace_now_s5);
  if(!trace_initialized || trace_now_s6 !== trace_prev_s6) $fwrite(trace_fd,"b%b s6\n",trace_now_s6);
  if(!trace_initialized || trace_now_s7 !== trace_prev_s7) $fwrite(trace_fd,"b%b s7\n",trace_now_s7);
  if(!trace_initialized || trace_now_s8 !== trace_prev_s8) $fwrite(trace_fd,"b%b s8\n",trace_now_s8);
  if(!trace_initialized || trace_now_s9 !== trace_prev_s9) $fwrite(trace_fd,"b%b s9\n",trace_now_s9);
  if(!trace_initialized || trace_now_s10 !== trace_prev_s10) $fwrite(trace_fd,"b%b s10\n",trace_now_s10);
  if(!trace_initialized || trace_now_s11 !== trace_prev_s11) $fwrite(trace_fd,"b%b s11\n",trace_now_s11);
  if(!trace_initialized || trace_now_s12 !== trace_prev_s12) $fwrite(trace_fd,"b%b s12\n",trace_now_s12);
  if(!trace_initialized || trace_now_s13 !== trace_prev_s13) $fwrite(trace_fd,"b%b s13\n",trace_now_s13);
  if(!trace_initialized || trace_now_s14 !== trace_prev_s14) $fwrite(trace_fd,"b%b s14\n",trace_now_s14);
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s15 !== trace_prev_s15) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s15\n",trace_now_s15);
   else $fwrite(trace_fd,"bx s15\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s16 !== trace_prev_s16) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s16\n",trace_now_s16);
   else $fwrite(trace_fd,"bx s16\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s17 !== trace_prev_s17) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s17\n",trace_now_s17);
   else $fwrite(trace_fd,"bx s17\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s18 !== trace_prev_s18) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s18\n",trace_now_s18);
   else $fwrite(trace_fd,"bx s18\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s19 !== trace_prev_s19) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s19\n",trace_now_s19);
   else $fwrite(trace_fd,"bxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx s19\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s20 !== trace_prev_s20) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s20\n",trace_now_s20);
   else $fwrite(trace_fd,"bxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx s20\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s21 !== trace_prev_s21) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s21\n",trace_now_s21);
   else $fwrite(trace_fd,"bx s21\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s22 !== trace_prev_s22) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s22\n",trace_now_s22);
   else $fwrite(trace_fd,"bx s22\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s23 !== trace_prev_s23) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s23\n",trace_now_s23);
   else $fwrite(trace_fd,"bx s23\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s24 !== trace_prev_s24) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s24\n",trace_now_s24);
   else $fwrite(trace_fd,"bx s24\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s25 !== trace_prev_s25) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s25\n",trace_now_s25);
   else $fwrite(trace_fd,"bx s25\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s26 !== trace_prev_s26) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s26\n",trace_now_s26);
   else $fwrite(trace_fd,"bx s26\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s27 !== trace_prev_s27) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s27\n",trace_now_s27);
   else $fwrite(trace_fd,"bx s27\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s28 !== trace_prev_s28) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s28\n",trace_now_s28);
   else $fwrite(trace_fd,"bx s28\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s29 !== trace_prev_s29) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s29\n",trace_now_s29);
   else $fwrite(trace_fd,"bxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx s29\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s30 !== trace_prev_s30) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s30\n",trace_now_s30);
   else $fwrite(trace_fd,"bxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx s30\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s31 !== trace_prev_s31) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s31\n",trace_now_s31);
   else $fwrite(trace_fd,"bxxxxxxxxxxx s31\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s32 !== trace_prev_s32) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s32\n",trace_now_s32);
   else $fwrite(trace_fd,"bxxxxxxxxxxx s32\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s33 !== trace_prev_s33) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s33\n",trace_now_s33);
   else $fwrite(trace_fd,"bxxxxxxxxxxx s33\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s34 !== trace_prev_s34) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s34\n",trace_now_s34);
   else $fwrite(trace_fd,"bxxxxxxxxxxx s34\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s35 !== trace_prev_s35) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s35\n",trace_now_s35);
   else $fwrite(trace_fd,"bxxxxxxxxxxx s35\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s36 !== trace_prev_s36) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s36\n",trace_now_s36);
   else $fwrite(trace_fd,"bxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx s36\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s37 !== trace_prev_s37) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s37\n",trace_now_s37);
   else $fwrite(trace_fd,"bxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx s37\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s38 !== trace_prev_s38) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s38\n",trace_now_s38);
   else $fwrite(trace_fd,"bxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx s38\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s39 !== trace_prev_s39) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s39\n",trace_now_s39);
   else $fwrite(trace_fd,"bxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx s39\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s40 !== trace_prev_s40) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s40\n",trace_now_s40);
   else $fwrite(trace_fd,"bxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx s40\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s41 !== trace_prev_s41) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s41\n",trace_now_s41);
   else $fwrite(trace_fd,"bxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx s41\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s42 !== trace_prev_s42) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s42\n",trace_now_s42);
   else $fwrite(trace_fd,"bxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx s42\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s43 !== trace_prev_s43) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s43\n",trace_now_s43);
   else $fwrite(trace_fd,"bxxxxxxxxx s43\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s44 !== trace_prev_s44) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s44\n",trace_now_s44);
   else $fwrite(trace_fd,"bx s44\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s45 !== trace_prev_s45) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s45\n",trace_now_s45);
   else $fwrite(trace_fd,"bx s45\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s46 !== trace_prev_s46) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s46\n",trace_now_s46);
   else $fwrite(trace_fd,"bxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx s46\n");
  end
  if(!trace_initialized || trace_capture != trace_previous_capture || trace_now_s47 !== trace_prev_s47) begin
   if(trace_capture) $fwrite(trace_fd,"b%b s47\n",trace_now_s47);
   else $fwrite(trace_fd,"bxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx s47\n");
  end
 end
 trace_prev_s0=trace_now_s0;
 trace_prev_s1=trace_now_s1;
 trace_prev_s2=trace_now_s2;
 trace_prev_s3=trace_now_s3;
 trace_prev_s4=trace_now_s4;
 trace_prev_s5=trace_now_s5;
 trace_prev_s6=trace_now_s6;
 trace_prev_s7=trace_now_s7;
 trace_prev_s8=trace_now_s8;
 trace_prev_s9=trace_now_s9;
 trace_prev_s10=trace_now_s10;
 trace_prev_s11=trace_now_s11;
 trace_prev_s12=trace_now_s12;
 trace_prev_s13=trace_now_s13;
 trace_prev_s14=trace_now_s14;
 trace_prev_s15=trace_now_s15;
 trace_prev_s16=trace_now_s16;
 trace_prev_s17=trace_now_s17;
 trace_prev_s18=trace_now_s18;
 trace_prev_s19=trace_now_s19;
 trace_prev_s20=trace_now_s20;
 trace_prev_s21=trace_now_s21;
 trace_prev_s22=trace_now_s22;
 trace_prev_s23=trace_now_s23;
 trace_prev_s24=trace_now_s24;
 trace_prev_s25=trace_now_s25;
 trace_prev_s26=trace_now_s26;
 trace_prev_s27=trace_now_s27;
 trace_prev_s28=trace_now_s28;
 trace_prev_s29=trace_now_s29;
 trace_prev_s30=trace_now_s30;
 trace_prev_s31=trace_now_s31;
 trace_prev_s32=trace_now_s32;
 trace_prev_s33=trace_now_s33;
 trace_prev_s34=trace_now_s34;
 trace_prev_s35=trace_now_s35;
 trace_prev_s36=trace_now_s36;
 trace_prev_s37=trace_now_s37;
 trace_prev_s38=trace_now_s38;
 trace_prev_s39=trace_now_s39;
 trace_prev_s40=trace_now_s40;
 trace_prev_s41=trace_now_s41;
 trace_prev_s42=trace_now_s42;
 trace_prev_s43=trace_now_s43;
 trace_prev_s44=trace_now_s44;
 trace_prev_s45=trace_now_s45;
 trace_prev_s46=trace_now_s46;
 trace_prev_s47=trace_now_s47;
 trace_initialized=1;trace_previous_capture=trace_capture;
end
final begin $fclose(trace_fd);$fclose(marker_fd);end

