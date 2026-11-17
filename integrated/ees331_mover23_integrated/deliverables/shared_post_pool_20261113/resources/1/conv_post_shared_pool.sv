// Shared backend for all K3/PW8 producers and the existing post processors.
// Types 0/5 are ordinary stored convolutions; types 6/7 are software-validated
// convolution+affine-post jobs. For fused jobs word3 is final UINT8 address,
// word12 is a virtual INT32 producer base, word4 parameters, word5 elements.
// Caller retains each unit_command from unit_start through unit_done.
// Only two layer-owned FIFOs are instantiated in the normal 2/6/2 build.
module conv_post_shared_pool #(
 parameter integer K3_UNITS=2,K1_UNITS=6,POST_UNITS=2,MAX_CHANNELS=512,FIFO_DEPTH=8,
 parameter integer CONVS=K3_UNITS+K1_UNITS,UNITS=CONVS+POST_UNITS,
 parameter integer CW=$clog2(CONVS),QW=$clog2(FIFO_DEPTH),CHW=$clog2(MAX_CHANNELS+1)
)(
 input wire clk,rst_n,clear,
 input wire [UNITS-1:0] unit_start,
 input wire [UNITS-1:0][511:0] unit_command,
 input wire [POST_UNITS-1:0] post_enable,
 output wire [UNITS-1:0] unit_busy,unit_done,unit_error,unit_work,
 output wire [UNITS-1:0] mem_valid,mem_write,mem_byte,
 output wire [UNITS*32-1:0] mem_addr,mem_wdata,
 input wire [UNITS-1:0] mem_ready,mem_response,input wire [UNITS*32-1:0] mem_rdata,
 output wire [CONVS-1:0][31:0] conv_input_reads,conv_weight_reads,conv_mac_count,
 output wire [CONVS-1:0] waiting,stream_jobs,
 output wire [POST_UNITS-1:0] owned,fifo_push,fifo_pop,post_retire,
 output wire [POST_UNITS-1:0][CW-1:0] owner_id,
 output wire [POST_UNITS-1:0][QW:0] fifo_level,
 output wire [POST_UNITS-1:0] final_write_ack
);
 wire [UNITS-1:0][15:0][31:0] cmd=unit_command;
 wire [CONVS-1:0] cv,cwrite,cbyte,cready,cresponse,cbusy,cdone,cerror,cwork;
 wire [CONVS-1:0][31:0] ca,cd,channel;
 wire [POST_UNITS-1:0] pbusy,pdone,perror,pready;
 logic [CONVS-1:0] jobs,fused,conv_seen;
 logic [CONVS-1:0] fused_done;
 logic [POST_UNITS-1:0] owner_valid,post_seen,stream_start,pending_write;
 logic [POST_UNITS-1:0][CW-1:0] owner;
 logic [CW-1:0] turn,next_turn;
 logic [POST_UNITS-1:0] grant;
 logic [POST_UNITS-1:0][CW-1:0] choice;
 wire [POST_UNITS-1:0][31:0] forwarded_counts;
 logic [CONVS-1:0] attached,claimed;
 logic failed;
 wire kill=clear || failed || (|cerror) || (|perror);
 assign owned=owner_valid;assign owner_id=owner;assign stream_jobs=fused;
 always_comb begin
  attached=0;
  for(integer p=0;p<POST_UNITS;p++)if(owner_valid[p])attached[owner[p]]=1;
 end
 assign waiting=jobs & fused & ~attached & cv & cwrite;
 // Round-robin on producers that already have a real first output. A slow
 // producer cannot reserve an idle post while still loading its input.
 always_comb begin
  grant=0;choice=0;claimed=attached;next_turn=turn;
  for(integer p=0;p<POST_UNITS;p++)begin
   if(!kill && post_enable[p] && !owner_valid[p] && !pbusy[p] && !unit_start[CONVS+p] && !stream_start[p])begin
    for(integer i=0;i<CONVS;i++)begin
     integer c;c=int'(turn)+i;if(c>=CONVS)c=c-CONVS;
     if(!grant[p] && waiting[c] && !claimed[c])begin
      grant[p]=1;choice[p]=CW'(c);claimed[c]=1;
      next_turn=c==CONVS-1?'0:CW'(c+1);
     end
    end
   end
  end
 end
 for(genvar c=0;c<CONVS;c++)begin:convs
  wire is_new_fused=cmd[c][0]==6 || cmd[c][0]==7;
  wire [31:0] raw_base=is_new_fused?cmd[c][12]:cmd[c][3];
  if(c<K3_UNITS)begin:k3
   self_conv_spatial4_engine #(.MAX_CHANNELS(MAX_CHANNELS),.MAX_KERNEL(3),.TILE(2),.DW_CACHE(1)) convolution(
    .clk(clk),.rst_n(rst_n),.clear(kill),.start(unit_start[c]),.depthwise(cmd[c][11][0]),
    .input_base(cmd[c][1]),.weight_base(cmd[c][2]),.output_base(raw_base),.width(cmd[c][7]),.height(cmd[c][8]),
    .in_channels(cmd[c][6]),.out_channels(cmd[c][9]),.kernel(32'd3),.stride(cmd[c][10]),
    .busy(cbusy[c]),.done(cdone[c]),.error(cerror[c]),.valid(cv[c]),.write(cwrite[c]),.byte_access(cbyte[c]),
    .addr(ca[c]),.wdata(cd[c]),.ready(cready[c]),.response(cresponse[c]),.rdata(mem_rdata[c*32+:32]),
    .mac_fire(cwork[c]),.phase(),.input_reads(conv_input_reads[c]),.weight_reads(conv_weight_reads[c]),
    .mac_count(conv_mac_count[c]),.result_channel(channel[c]));
  end else begin:k1
   self_pw8_engine #(.MAX_CHANNELS(MAX_CHANNELS)) convolution(
    .clk(clk),.rst_n(rst_n),.clear(kill),.start(unit_start[c]),.depthwise(cmd[c][11][0]),
    .input_base(cmd[c][1]),.weight_base(cmd[c][2]),.output_base(raw_base),.width(cmd[c][7]),.height(cmd[c][8]),
    .in_channels(cmd[c][6]),.out_channels(cmd[c][9]),.kernel(32'd1),.stride(cmd[c][10]),
    .busy(cbusy[c]),.done(cdone[c]),.error(cerror[c]),.valid(cv[c]),.write(cwrite[c]),.byte_access(cbyte[c]),
    .addr(ca[c]),.wdata(cd[c]),.ready(cready[c]),.response(cresponse[c]),.rdata(mem_rdata[c*32+:32]),
    .mac_fire(cwork[c]),.phase(),.input_reads(conv_input_reads[c]),.weight_reads(conv_weight_reads[c]),
    .mac_count(conv_mac_count[c]),.result_channel(channel[c]));
  end
  wire route=fused[c] && cwrite[c];
  wire [POST_UNITS-1:0] accepts;
  for(genvar p=0;p<POST_UNITS;p++)assign accepts[p]=owner_valid[p] && owner[p]==c && fifo_push[p];
  wire take=|accepts;
  assign mem_valid[c]=cv[c] && !route && !kill;
  assign mem_write[c]=cwrite[c];assign mem_byte[c]=cbyte[c];
  assign mem_addr[c*32+:32]=ca[c];assign mem_wdata[c*32+:32]=cd[c];
  assign cready[c]=route?take:mem_ready[c];
  assign cresponse[c]=route?take:mem_response[c];
  assign unit_busy[c]=jobs[c] || cbusy[c];
  assign unit_done[c]=fused_done[c] || (cdone[c] && !fused[c]);
  assign unit_error[c]=cerror[c] || failed;
  assign unit_work[c]=cwork[c];
 end
 for(genvar p=0;p<POST_UNITS;p++)begin:links
  localparam integer U=CONVS+p;
  (* ram_style="registers" *) logic [31:0] q_data[0:FIFO_DEPTH-1],q_index[0:FIFO_DEPTH-1];
  (* ram_style="registers" *) logic [CHW-1:0] q_channel[0:FIFO_DEPTH-1];
  logic [QW-1:0] wp,rp;logic [QW:0] used;
  logic [31:0] forwarded;
  assign forwarded_counts[p]=forwarded;
  wire [CW-1:0] c=owner[p];
  wire [31:0] expected=cmd[c][5];
  assign fifo_level[p]=used;
  assign fifo_push[p]=owner_valid[p] && cv[c] && cwrite[c] && used<FIFO_DEPTH && !kill;
  assign fifo_pop[p]=owner_valid[p] && used!=0 && pready[p] && !kill;
  always_ff @(posedge clk)if(fifo_push[p])begin
   q_data[wp]<=cd[c];q_index[wp]<=(ca[c]-cmd[c][12])>>2;q_channel[wp]<=CHW'(channel[c]);
  end
  always_ff @(posedge clk or negedge rst_n)begin
   if(!rst_n)begin wp<=0;rp<=0;used<=0;forwarded<=0;end
   else if(kill || grant[p])begin wp<=0;rp<=0;used<=0;forwarded<=0;end
   else begin
    if(fifo_push[p])begin wp<=wp+1'b1;forwarded<=forwarded+1;end
    if(fifo_pop[p])rp<=rp+1'b1;
    case({fifo_push[p],fifo_pop[p]})2'b10:used<=used+1'b1;2'b01:used<=used-1'b1;default:;endcase
   end
  end
  wire [31:0] src=owner_valid[p]?cmd[c][12]:cmd[U][1];
  wire [31:0] dst=owner_valid[p]?cmd[c][3]:cmd[U][3];
  wire [31:0] par=owner_valid[p]?cmd[c][4]:cmd[U][4];
  wire [31:0] n=owner_valid[p]?cmd[c][5]:cmd[U][5];
  wire [31:0] nch=owner_valid[p]?cmd[c][9]:cmd[U][6];
  quant_post_pipe_engine #(.MAX_CHANNELS(MAX_CHANNELS),.GROUP_BYTES(16),.STREAM_SUPPORT(1)) post(
   .clk(clk),.rst_n(rst_n),.clear(kill),.start(stream_start[p] || unit_start[U]),.mode_add(1'b0),
   .src_a(src),.src_b(32'd0),.destination(dst),.parameter_base(par),.count(n),.channels(nch),
   .busy(pbusy[p]),.done(pdone[p]),.error(perror[p]),.valid(mem_valid[U]),.write(mem_write[U]),.byte_access(mem_byte[U]),
   .addr(mem_addr[U*32+:32]),.wdata(mem_wdata[U*32+:32]),.ready(mem_ready[U]),.response(mem_response[U]),.rdata(mem_rdata[U*32+:32]),
   .stream_mode(owner_valid[p]),.s_valid(owner_valid[p] && used!=0),.s_data(q_data[rp]),.s_index(q_index[rp]),
   .s_channel(32'(q_channel[rp])),.s_ready(pready[p]),.stream_work(post_retire[p]));
  // Include combinational reservation in busy: the global dispatcher must
  // see a stream grant before it can issue an ordinary post to the same unit.
  assign unit_busy[U]=pbusy[p] || pdone[p] || owner_valid[p] || grant[p] || stream_start[p];
  assign unit_done[U]=pdone[p] && !owner_valid[p];
  assign unit_error[U]=perror[p] || failed;
  assign unit_work[U]=mem_valid[U] && mem_ready[U] && mem_write[U];
  wire accepted=mem_valid[U] && mem_ready[U];
  assign final_write_ack[p]=mem_response[U] && (pending_write[p] || (accepted && mem_write[U])) && !kill;
  always_ff @(posedge clk or negedge rst_n)begin
   if(!rst_n)pending_write[p]<=0;
   else if(kill)pending_write[p]<=0;
   else if(mem_response[U])pending_write[p]<=0;
   else if(accepted)pending_write[p]<=mem_write[U];
  end
  always_ff @(posedge clk or negedge rst_n)begin
   if(!rst_n)begin owner_valid[p]<=0;owner[p]<=0;post_seen[p]<=0;end
   else if(kill)begin owner_valid[p]<=0;post_seen[p]<=0;end
   else begin
    if(grant[p])begin owner_valid[p]<=1;owner[p]<=choice[p];post_seen[p]<=0;end
    if(owner_valid[p] && pdone[p])post_seen[p]<=1;
    if(owner_valid[p] && (post_seen[p] || pdone[p]) && (conv_seen[c] || cdone[c]) && used==0)begin
     owner_valid[p]<=0;post_seen[p]<=0;
    end
   end
  end
 end
 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin jobs<=0;fused<=0;conv_seen<=0;fused_done<=0;stream_start<=0;turn<=0;failed<=0;end
  else if(clear)begin jobs<=0;fused<=0;conv_seen<=0;fused_done<=0;stream_start<=0;turn<=0;failed<=0;end
  else if(kill)begin jobs<=0;fused<=0;conv_seen<=0;fused_done<=0;stream_start<=0;failed<=1;end
  else begin
   fused_done<=0;stream_start<=grant;turn<=next_turn;
   for(integer c=0;c<CONVS;c++)begin
    if(unit_start[c])begin
     if(jobs[c])failed<=1;
     jobs[c]<=1;fused[c]<=cmd[c][0]==6 || cmd[c][0]==7;conv_seen[c]<=0;
    end
    if(cdone[c])begin conv_seen[c]<=1;if(!fused[c])jobs[c]<=0;end
   end
   for(integer p=0;p<POST_UNITS;p++)begin
    if(unit_start[CONVS+p] && (owner_valid[p] || pbusy[p]))failed<=1;
    if(owner_valid[p])begin
     if(cv[owner[p]] && cwrite[owner[p]] && forwarded_counts[p]>=cmd[owner[p]][5])failed<=1;
     if(cdone[owner[p]] && forwarded_counts[p]!=cmd[owner[p]][5])failed<=1;
     if((post_seen[p] || pdone[p]) && (conv_seen[owner[p]] || cdone[owner[p]]) && fifo_level[p]==0)begin
      fused_done[owner[p]]<=1;jobs[owner[p]]<=0;fused[owner[p]]<=0;
     end
    end
   end
  end
 end
endmodule
