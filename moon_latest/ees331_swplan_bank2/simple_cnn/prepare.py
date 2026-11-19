from pathlib import Path
import hashlib,json
from finalize_k3 import split_bounds
BASE=Path(__file__).resolve().parent
MOON=Path('D:/code/FPGA1/moon_latest/ees331_swplan_bank2')
out=BASE/'rtl';out.mkdir(exist_ok=True)
hashes={}
for name in ['compact_word_ram.sv','self_conv_spatial4_engine.sv','self_pw8_engine.sv']:
    path=MOON/'source/rtl/cnn_self'/name
    raw=path.read_bytes();hashes[name]=hashlib.sha256(raw).hexdigest()
    text=raw.decode('utf-8').replace('\r\n','\n')
    if name=='self_conv_spatial4_engine.sv':
        text=text.replace('module self_conv_spatial4_engine #(', 'module simple_k3_engine #(',1)
        start=text.index(' // Planned segments replace both generic')
        end=text.index('`ifndef SYNTHESIS',start)
        text=text[:start]+''' // Simple baseline: direct request port. The outer registered bridge
 // accepts and completes one request before this core can issue another.
 assign valid=core_valid;assign write=core_write;assign byte_access=core_byte_access;
 assign addr=core_addr;assign wdata=core_wdata;
 assign core_ready=ready;assign core_response=response;assign core_rdata=rdata;
 assign prefetch_idle=1'b1;assign prefetch_fault=1'b0;
'''+text[end:]
        text=text.replace('// READ_AHEAD defaults off; opt-in fabrics support four ordered reads.',
                          '// This derivative has no prefetch adapter; one registered transaction is outstanding.')
        text=text.replace('logic read_valid,product_valid,read_last,product_last;',
          'logic read_valid,selected_valid,product_valid,read_last,selected_last,product_last;\n logic [7:0] selected_input[0:3];\n logic signed [7:0] selected_weight;')
        text=text.replace("product[l]=$signed({1'b0,input_word_q[bank_select_q[l]][input_lane_q*8+:8]})*$signed(weight_q);",
                          "product[l]=$signed({1'b0,selected_input[l]})*$signed(selected_weight);")
        text=text.replace('read_valid<=0;product_valid<=0;read_last<=0;product_last<=0;',
                          'read_valid<=0;selected_valid<=0;product_valid<=0;read_last<=0;selected_last<=0;product_last<=0;')
        text=text.replace('product_valid<=read_valid;','selected_valid<=read_valid;\n   product_valid<=selected_valid;')
        text=text.replace('if(read_valid)begin\n    for(integer l=0;l<4;l=l+1)if(active_mask[l])product_q[l]<=product[l];\n    product_last<=read_last;',
          'if(read_valid)begin\n    for(integer l=0;l<4;l=l+1)selected_input[l]<=input_word_q[bank_select_q[l]][input_lane_q*8+:8];\n    selected_weight<=weight_q;selected_last<=read_last;\n   end\n   if(selected_valid)begin\n    for(integer l=0;l<4;l=l+1)if(active_mask[l])product_q[l]<=product[l];\n    product_last<=selected_last;')
        text=text.replace('// Issue one tap/channel each cycle. The last marker drains with its product,',
          '// Register bank/byte selection before multiplying. One extra drain cycle.\n // Issue one tap/channel each cycle. The last marker drains with its product,')
        name='simple_k3_engine.sv'
    elif name=='self_pw8_engine.sv':
        text=text.replace('module self_pw8_engine #(', 'module simple_k1_engine #(',1)
        start=text.index(' wire [C_BITS:0] input_remaining=')
        end=text.index('`ifndef SYNTHESIS',start)
        text=text[:start]+''' // No address-tagged prefetch, automatic stream restart or bypass path.
 assign valid=a_valid;assign write=a_write;assign byte_access=a_byte;
 assign addr=a_addr;assign wdata=a_wdata;
 assign a_ready=ready;assign a_response=response;assign a_rdata=rdata;
 assign prefetch_idle=1'b1;assign prefetch_fault=1'b0;
'''+text[end:]
        # Apply the K1 timing changes only to the expected moon source.
        for old, new in [
            (' logic held,held_byte;',
             """ logic held,held_byte;
 // Channel indices at which the last byte or full word of a pixel starts.
 logic [C_BITS-1:0] input_last_byte,input_last_word;
 logic held_input_last;"""),
            ("wire [2:0] in_count=in_wide?3'd4:3'd1,weight_count=",
             """// The reply consumes the width recorded with this request, also after stalls.
 wire [2:0] in_count=held_byte?3'd1:3'd4,weight_count="""),
            ('held_kind<=offer_kind;held_addr<=offer_addr;held_data<=offer_data;held_byte<=offer_byte;',
             """held_kind<=offer_kind;held_addr<=offer_addr;held_data<=offer_data;held_byte<=offer_byte;
    // Sample with the offer. Only an input response consumes this marker.
    held_input_last<=in_wide ? load_c==input_last_word : load_c==input_last_byte;"""),
            ("""   CHECK:begin
    layer_cached""",
             """   CHECK:begin
    input_last_byte<=ci-1'b1;
    input_last_word<=ci-4;
    layer_cached"""),
            ('end else if(load_c+4<ci)begin',
             'end else if(!held_input_last)begin'),
            ('if(LINEAR_GROUPS && load_c+in_count>=ci)begin',
             'if(LINEAR_GROUPS && held_input_last)begin'),
            ('if(load_c+in_count<ci)begin',
             'if(!held_input_last)begin'),
            ('OWAIT,DRAIN,FINISH,FAIL}',
             'OWAIT,DRAIN,FINISH,FAIL,CAPTURE_ENDS}'),
            (""" wire [63:0] input_end={32'd0,ib}+input_extent;
 wire [63:0] weight_end={32'd0,wb}+weight_extent;
 wire [63:0] output_end={32'd0,ob}+output_extent;""",
             """ // In linear mode the pixel-count multiply leaves time to register all three
 // exclusive ends. The rectangular mode captures them in a single setup cycle.
 logic [63:0] input_end,weight_end,output_end;
 always_ff @(posedge clk)if((state==SETUP && setup_step==5) || state==CAPTURE_ENDS)begin
  input_end<={32'd0,ib}+input_extent;
  weight_end<={32'd0,wb}+weight_extent;
  output_end<={32'd0,ob}+output_extent;
 end"""),
            ('       else state<=CHECK;',
             '       else state<=CAPTURE_ENDS;'),
            ('   CHECK:begin',
             """   CAPTURE_ENDS:state<=CHECK;
   CHECK:begin"""),
        ]:
            if text.count(old) != 1:
                raise ValueError(f"Unexpected K1 source near {old!r}")
            text=text.replace(old,new,1)
        name='simple_k1_engine.sv'
    if name=='simple_k3_engine.sv':text=split_bounds(text)
    (out/name).write_text(text,encoding='utf-8')
(BASE/'origin.json').write_text(json.dumps({'base_commit':'f26d4af97754faa9d6a1d20faf72f1f6b36ddbdf','base_project':str(MOON),'source_sha256':hashes,'changes':['New manual four-unit command frontend','New registered single-outstanding completion bridge','Retain tested arithmetic/RAM reuse, remove both prefetch paths','Register K3 bank/byte selection before multiplication','K1 uses OUTPUT_PAR=1, INPUT_PREFETCH=0, READ_AHEAD=0','K1 records width and last-channel metadata with input requests','Register K1 range ends during setup']},indent=2),encoding='utf-8')
print('Prepared source derivatives; original moon files unchanged.')
