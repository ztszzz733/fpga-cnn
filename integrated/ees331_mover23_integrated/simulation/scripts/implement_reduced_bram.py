"""Apply the user-authorized 12-unit, no-DW7, compact-BRAM configuration."""
from pathlib import Path
import hashlib,json,shutil,datetime
SIM=Path(__file__).resolve().parents[1];BASE=SIM.parent
stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
backup=SIM/'build'/('before_reduced_bram_'+stamp);backup.mkdir(parents=True)
changes={}
def edit(name,pairs):
 p=BASE/name;text=p.read_text(encoding='utf-8');old=text
 for a,b in pairs:
  if a not in text:raise RuntimeError(name+' missing anchor '+a[:100])
  text=text.replace(a,b)
 q=backup/name;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
 p.write_text(text,encoding='utf-8');changes[name]={'before':hashlib.sha256(old.encode()).hexdigest(),'after':hashlib.sha256(p.read_bytes()).hexdigest()}

edit('rtl/cnn_self/self_pw8_engine.sv',[
 ('logic [31:0] input_q[8],weight_q[2];','logic [63:0] pixel_q;logic [31:0] weight_word_q;\n logic [31:0] input_fill_word;logic [2:0] input_fill_left,input_fill_lane;logic [C_BITS-1:0] input_fill_c;'),
 ('input_q[p][pipe_offset*8+:8]','pixel_q[p*8+:8]'),('weight_q[compute_bank][pipe_offset*8+:8]','weight_word_q[pipe_offset*8+:8]'),
 ('// Independent banks give eight synchronous pixel reads without a 8-port RAM.', '// Packed channel rows supply all eight pixel bytes with one 64-bit read.\n // Incoming 32-bit words are committed over at most four local cycles.'),
 (' for(genvar p=0;p<8;p++)begin:pixel_banks\n', ' for(genvar p=0;p<8;p++)begin:pixel_banks\n'),
 ('  (* ram_style="block" *) logic [31:0] pixels[WORDS];\n  always_ff @(posedge clk)if(!clear)begin\n   if(input_response && load_lane==p)begin\n    // Constant byte slices infer a byte-enable RAM, not 32 one-bit RAMs.\n    for(integer b=0;b<4;b++)if(in_wide || load_c[1:0]==b)\n     pixels[load_c>>2][b*8+:8]<=in_wide?rdata[b*8+:8]:rdata[7:0];\n   end\n   if(state==MAC_RUN && issue_c<ci && lane_mask[p])input_q[p]<=pixels[issue_c>>2];\n  end\n end\n for(genvar bank=0;bank<2;bank++)begin:weight_banks\n  (* ram_style="block" *) logic [31:0] weights[WORDS];\n  always_ff @(posedge clk)if(!clear)begin\n   if(weight_response && fill_bank==bank)\n    for(integer b=0;b<4;b++)if(weight_wide || weight_c[1:0]==b)\n     weights[weight_c>>2][b*8+:8]<=weight_wide?rdata[b*8+:8]:rdata[7:0];\n   if(state==MAC_RUN && issue_c<ci && compute_bank==bank)weight_q[bank]<=weights[issue_c>>2];\n  end\n end',
 '''  // Kept only as a constant byte-enable selector, not a separate RAM.
 end
 (* ram_style="block" *) logic [63:0] pixels[0:MAX_CHANNELS-1];
 always @(posedge clk)if(!clear)begin
  for(integer p=0;p<8;p++)if(input_fill_left!=0 && input_fill_lane==p)
   pixels[input_fill_c][p*8+:8]<=input_fill_word[7:0];
  if(state==MAC_RUN && issue_c<ci)pixel_q<=pixels[issue_c];
 end
 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin input_fill_left<=0;input_fill_word<=0;input_fill_c<=0;input_fill_lane<=0;end
  else if(clear)input_fill_left<=0;
  else if(input_response)begin
   input_fill_word<=rdata;input_fill_left<=in_count;input_fill_c<=load_c;input_fill_lane<=load_lane;
  end else if(input_fill_left!=0)begin
   input_fill_word<=input_fill_word>>8;input_fill_left<=input_fill_left-1'b1;input_fill_c<=input_fill_c+1'b1;
  end
 end
 wire [3:0] weight_mask=weight_wide?4'hf:(4'b1<<weight_c[1:0]);
 compact_word_ram #(.DEPTH(2*WORDS)) weights(
  .clk(clk),.wr_en(weight_response && !clear),.rd_en(state==MAC_RUN && issue_c<ci && !clear),
  .wr_addr($clog2(2*WORDS)'((fill_bank?WORDS:0)+(weight_c>>2))),
  .rd_addr($clog2(2*WORDS)'((compute_bank?WORDS:0)+(issue_c>>2))),
  .wr_data(weight_wide?rdata:{4{rdata[7:0]}}),.wr_mask(weight_mask),.rd_data(weight_word_q));'''),
 ('if(state==IREQ)begin\n   offer_valid=1;', 'if(state==IREQ && input_fill_left==0)begin\n   offer_valid=1;'),
 ('WREQ:if(weight_loaded[compute_bank])begin','WREQ:if(weight_loaded[compute_bank] && input_fill_left==0)begin'),
])

edit('rtl/cnn_self/self_conv_spatial4_engine.sv',[
 ('logic [1:0] bx,by;', 'logic [1:0] bx,by,bank;'),
 ('bank_offset=(by*3+bx)*MAX_CHANNELS+ch;', 'bank=spatial_bank(x,y,s2);\n   bank_offset=(by*(bank[0]?2:3)+bx)*MAX_CHANNELS+ch;'),
 (' (* ram_style="block" *) logic [31:0] weight_mem[0:(WEIGHT_BYTES+3)/4-1];',' // Weight and input caches use compact synchronous RAM below.'),
 ('  (* ram_style="block" *) logic [31:0] mem[0:(BANK_BYTES+3)/4-1];\n  always_ff @(posedge clk)begin\n   if(!clear)begin\n    for(integer byte_lane=0;byte_lane<4;byte_lane=byte_lane+1)\n     if(input_response && load_bank==b && (input_wide || load_bank_index[1:0]==byte_lane))\n      mem[load_bank_index>>2][byte_lane*8+:8]<=input_wide?rdata[byte_lane*8+:8]:rdata[7:0];\n    if(state==MAC_READ)input_word_q[b]<=mem[bank_read_index[b]>>2];\n   end\n  end',
 '''  localparam integer BANK_DEPTH=((b%2?2:3)*(b/2?2:3)*MAX_CHANNELS+3)/4;
  compact_word_ram #(.DEPTH(BANK_DEPTH)) mem(
   .clk(clk),.wr_en(input_response && load_bank==b && !clear),.rd_en(state==MAC_READ && !clear),
   .wr_addr($clog2(BANK_DEPTH)'(load_bank_index>>2)),.rd_addr($clog2(BANK_DEPTH)'(bank_read_index[b]>>2)),
   .wr_data(input_wide?rdata:{4{rdata[7:0]}}),
   .wr_mask(input_wide?4'hf:(4'b1<<load_bank_index[1:0])),.rd_data(input_word_q[b]));'''),
 (' always_ff @(posedge clk)begin\n  if(!clear)begin\n   for(integer lane=0;lane<4;lane=lane+1)\n    if(weight_response && (weight_wide || weight_load_index[1:0]==lane))\n     weight_mem[weight_load_index>>2][lane*8+:8]<=weight_wide?rdata[lane*8+:8]:rdata[7:0];',
 ''' compact_word_ram #(.DEPTH((WEIGHT_BYTES+3)/4)) weights(
  .clk(clk),.wr_en(weight_response && !clear),.rd_en(state==MAC_READ && !clear),
  .wr_addr($clog2((WEIGHT_BYTES+3)/4)'(weight_load_index>>2)),.rd_addr($clog2((WEIGHT_BYTES+3)/4)'(weight_index>>2)),
  .wr_data(weight_wide?rdata:{4{rdata[7:0]}}),
  .wr_mask(weight_wide?4'hf:(4'b1<<weight_load_index[1:0])),.rd_data(weight_word_q));
 always_ff @(posedge clk)begin
  if(!clear)begin'''),
 ('    weight_word_q<=weight_mem[weight_index>>2];weight_lane_q<=weight_index[1:0];','    weight_lane_q<=weight_index[1:0];'),
])

edit('rtl/cnn_quant/quant_post_pipe_engine.sv',[
 (' (* ram_style="block" *) logic [31:0] bias_mem[0:MAX_CHANNELS-1];\n (* ram_style="block" *) logic [31:0] ma_mem[0:MAX_CHANNELS-1];\n (* ram_style="block" *) logic [31:0] mb_mem[0:MAX_CHANNELS-1];\n (* ram_style="block" *) logic [31:0] cfg_mem[0:MAX_CHANNELS-1];\n (* ram_style="block" *) logic [15:0] clamp_mem[0:MAX_CHANNELS-1];',
 ' (* ram_style="block" *) logic [143:0] parameter_mem[0:MAX_CHANNELS-1];\n logic [127:0] parameter_staging;'),
 ('0:bias_mem[param_ch]<=rdata;','0:parameter_staging[0+:32]<=rdata;'),
 ('1:ma_mem[param_ch]<=rdata;','1:parameter_staging[32+:32]<=rdata;'),
 ('2:mb_mem[param_ch]<=rdata;','2:parameter_staging[64+:32]<=rdata;'),
 ('3:cfg_mem[param_ch]<=rdata;','3:parameter_staging[96+:32]<=rdata;'),
 ('4:clamp_mem[param_ch]<=rdata[15:0];','4:parameter_mem[param_ch]<={rdata[15:0],parameter_staging};'),
 ('    bias0<=bias_mem[ch];ma0<=ma_mem[ch];mb0<=mb_mem[ch];cfg0<=cfg_mem[ch];\n    low[0]<=clamp_mem[ch][7:0];high[0]<=clamp_mem[ch][15:8];',
 '    {high[0],low[0],cfg0,mb0,ma0,bias0}<=parameter_mem[ch];'),
])

for name in ['rtl/cnn_ddr/fixed_schedule_compact.sv','rtl/cnn_ddr/cnn_ees331.sv']:
 pairs=[('parameter bit LATEST_OPERATORS=0,','parameter bit LATEST_OPERATORS=0,ENABLE_DW7=1,'),
        ('UNITS=K3_UNITS+K1_UNITS+POST_UNITS+3','UNITS=K3_UNITS+K1_UNITS+POST_UNITS+2+ENABLE_DW7')]
 if 'fixed_schedule' in name:
  pairs += [('POST=DW+1','POST=DW+ENABLE_DW7'),
   ('template_command[31:0]<=5 &&','template_command[31:0]<=5 && (ENABLE_DW7 || template_command[31:0]!=3) &&'),
   ('3:if(enabled[DW]', '3:if(ENABLE_DW7 && enabled[DW]'),
   ('|| !unit_enable[DW] ||','|| (ENABLE_DW7 && !unit_enable[DW]) ||'),
   (' dw7_bram_engine #(', ' if(ENABLE_DW7)begin:with_dw7\n dw7_bram_engine #('),
   (' for(genvar e=POST;e<=ADD;e++)begin:postprocessing',' end\n for(genvar e=POST;e<=ADD;e++)begin:postprocessing')]
 else:pairs += [('.LATEST_OPERATORS(LATEST_OPERATORS)) core(','.LATEST_OPERATORS(LATEST_OPERATORS),.ENABLE_DW7(ENABLE_DW7)) core(')]
 edit(name,pairs)

edit('rtl/soc/ees331/face_soc_ees331_mover_top.sv',[
 ('parameter integer LOCAL_BYTES=32768,','parameter integer LOCAL_BYTES=32768,\n parameter integer K3_UNITS=2,K1_UNITS=6,POST_UNITS=2,\n parameter bit ENABLE_DW7=0,'),
 ('CNN_K3=POOL23 ? 4 : 2','CNN_K3=K3_UNITS'),('CNN_K1=POOL23 ? 12 : 4','CNN_K1=K1_UNITS'),('CNN_POST=POOL23 ? 4 : 1','CNN_POST=POST_UNITS'),
 ('CNN_CLIENTS=CNN_K3+CNN_K1+CNN_POST+3','CNN_CLIENTS=CNN_K3+CNN_K1+CNN_POST+2+ENABLE_DW7'),
 ('.FRAME_CONTEXTS(CNN_FRAMES),.K3_UNITS(CNN_K3)', '.FRAME_CONTEXTS(CNN_FRAMES),.ENABLE_DW7(ENABLE_DW7),.K3_UNITS(CNN_K3)'),
])

# Accept an integral number of pages/words; explicit victim wrap also supports
# non-power-of-two capacities when BRAM budgeting leaves a fractional power.
edit('storage_v2/rtl/tile_local_ram.sv',[('BYTES>=8 && BYTES%4==0 && (BYTES&(BYTES-1))==0','BYTES>=8 && BYTES%4==0')])
edit('rtl/cnn_ddr/cnn_paged_mover.sv',[
 ("victim_turn<=victim_turn+1'b1;", "victim_turn<=victim_turn==SB'(SLOTS-1)?'0:victim_turn+1'b1;"),
 ('LOCAL_BYTES==32768 && PAGE_BYTES==1024 && SLOTS==32','LOCAL_BYTES>=PAGE_BYTES*2 && LOCAL_BYTES%PAGE_BYTES==0 && PAGE_BYTES>=4 && (PAGE_BYTES&(PAGE_BYTES-1))==0')])

for file in ['rtl/filelists/system_ees331_mover23.f','rtl/filelists/cnn_ees331.f']:
 edit(file,[('rtl/cnn_self/self_conv_engine.sv','rtl/cnn_self/compact_word_ram.sv\nrtl/cnn_self/self_conv_engine.sv')])
new_list=(BASE/'rtl/filelists/system_ees331_mover23.f').read_text().replace('rtl/cnn_ddr/dw7_bram_engine.sv\n','')
(BASE/'rtl/filelists/system_ees331_reduced.f').write_text(new_list)
(backup/'changes.json').write_text(json.dumps(changes,indent=2)+'\n')
(SIM/'build/reduced_bram_source_backup.json').write_text(json.dumps({'backup':str(backup),'changes':changes},indent=2)+'\n')
print(backup)
