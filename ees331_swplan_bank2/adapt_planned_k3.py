from pathlib import Path
root = Path(__file__).resolve().parent
p = root / 'source/rtl/cnn_self/self_conv_spatial4_engine.sv'
s = p.read_text()
s = s.replace('input logic [31:0] width,height,in_channels,out_channels,kernel,stride,',
'''input logic [31:0] width,height,in_channels,out_channels,kernel,stride,
 input logic [31:0] plan_flags,plan_input_row_bytes,plan_weight_per_channel,
 input logic [31:0] plan_input_extent,plan_weight_extent,''')
s = s.replace(' logic dw,stride_two;', ' logic dw,stride_two;\n logic planned_input_word,planned_weight_word,planned_reuse;')
s = s.replace('wire layer_cached=dw_cached || (WEIGHT_LAYER_REUSE && !dw && (ow>TILE || oh>TILE) && weight_extent<=WEIGHT_BYTES);',
              'wire layer_cached=planned_reuse;')
s = s.replace("wire input_wide=(load_addr[1:0]==0 && load_c[1:0]==0 && ({1'b0,load_c}+(C_BITS+1)'(4)<={1'b0,ci}));", 'wire input_wide=planned_input_word;')
s = s.replace('wire weight_wide=(weight_addr[1:0]==0 && weight_load_index[1:0]==0 && (weight_load_index>>2)<weight_full_words);', 'wire weight_wide=planned_weight_word;')
s = s.replace('    setup_step<=0;mul_bit<=0;mul_acc<=0;\n    mul_lhs<={32\'d0,width};mul_rhs<=in_channels;', '''    // Software has already planned read geometry; only output setup remains.
    input_row_bytes<=plan_input_row_bytes;weight_per_channel<=plan_weight_per_channel;
    input_extent<={32'd0,plan_input_extent};weight_extent<={32'd0,plan_weight_extent};
    planned_input_word<=plan_flags[8];planned_weight_word<=plan_flags[9];planned_reuse<=plan_flags[10];
    setup_step<=4;mul_bit<=0;mul_acc<=0;
    mul_lhs<={32'd0,(((width-kernel)>>((stride==2)?1:0))+32'd1)};mul_rhs<=out_channels;''')
s = s.replace('if(MAX_CHANNELS<1', "if(!plan_flags[31] || (plan_flags & 32'h7ffff8fe)!=0 ||\n       plan_input_row_bytes==0 || plan_weight_per_channel==0 || plan_input_extent==0 || plan_weight_extent==0 ||\n       (plan_flags[8] && ((input_base[1:0]!=0) || in_channels[1:0]!=0)) ||\n       MAX_CHANNELS<1")
s = s.replace("if(input_end>64'h100000000", '''if(weight_load_bytes==0 || (layer_cached?weight_extent:{32'd0,weight_per_channel})>WEIGHT_BYTES ||
       (planned_weight_word && (wb[1:0]!=0 || weight_load_bytes[1:0]!=0)) ||
       input_end>64'h100000000''')
# Remove unselected descriptor multiplication cases, not merely bypass them.
a = s.index('      0:begin input_row_bytes<=')
b = s.index('      4:begin output_row_bytes<=', a)
s = s[:a] + s[b:]
a = s.index(' generate if(READ_WORD_BUFFER)begin:read_word_buffers')
b = s.index('`ifndef SYNTHESIS', a)
s = s[:a] + ''' // Planned segments replace both generic read-word widening and the
 // address-tagged prefetch adapter. No legacy branch enters this netlist.
 wire [31:0] segment_bytes=state==WREQ?32'(weight_load_bytes):32'(ci);
 wire [31:0] segment_beats=segment_bytes>>(core_byte_access?0:2);
 planned_read_adapter #(.DEPTH(4)) planned_reads(
  .clk,.rst_n,.clear(clear || (state==IDLE && start)),
  .c_valid(core_valid),.c_write(core_write),.c_byte(core_byte_access),
  .c_addr(core_addr),.c_wdata(core_wdata),.segment_beats,
  .c_ready(core_ready),.c_response(core_response),.c_rdata(core_rdata),
  .m_valid(valid),.m_write(write),.m_byte(byte_access),.m_addr(addr),.m_wdata(wdata),
  .m_ready(ready),.m_response(response),.m_rdata(rdata),.idle(prefetch_idle),.fault(prefetch_fault));
''' + s[b:]
p.write_text(s)
p = root / 'source/rtl/cnn_ddr/fixed_schedule_compact.sv'
s = p.read_text()
point = '   self_conv_spatial4_engine #'
start = s.index(point)
end = s.index('  end else if', start)
part = s[start:end]
part = part.replace('.input_base(cmd[e][1]),', '''.plan_flags(cmd[e][11]),.plan_input_row_bytes(cmd[e][4]),
   .plan_weight_per_channel(cmd[e][5]),.plan_input_extent(cmd[e][12]),.plan_weight_extent(cmd[e][15]),
   .input_base(cmd[e][1]),''')
s = s[:start] + part + s[end:]
p.write_text(s)
p = root / 'source/rtl/filelists/system_ees331_reduced.f'
s = p.read_text().replace('rtl/cnn_self/self_conv_spatial4_engine.sv', 'rtl/cnn_self/planned_read_adapter.sv\nrtl/cnn_self/self_conv_spatial4_engine.sv')
p.write_text(s)
print('Converted K3 to software-planned segments')
