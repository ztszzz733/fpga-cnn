from pathlib import Path
def split_bounds(text):
 assert 'CHECK_BOUNDS' not in text
 text=text.replace('IDLE,SETUP,CHECK,TILE_BEGIN,','IDLE,SETUP,CHECK,CHECK_BOUNDS,TILE_BEGIN,',1)
 old=''' wire [63:0] input_end={32'd0,ib}+input_extent;
 wire [63:0] weight_end={32'd0,wb}+weight_extent;
 wire [63:0] output_end={32'd0,ob}+output_extent;'''
 new=''' // Compute range ends one cycle before comparing ranges/control decisions.
 logic [63:0] input_end,weight_end,output_end;
 always_ff @(posedge clk)if(state==CHECK)begin
  input_end<={32'd0,ib}+input_extent;
  weight_end<={32'd0,wb}+weight_extent;
  output_end<={32'd0,ob}+output_extent;
 end'''
 assert old in text;text=text.replace(old,new,1)
 text=text.replace('always_ff @(posedge clk)if(state==CHECK)begin\n  input_limit_q',
                   'always_ff @(posedge clk)if(state==CHECK_BOUNDS)begin\n  input_limit_q',1)
 old='''    weight_full_words<=weight_load_bytes>>2;
    // Intervals are half-open'''
 new='''    weight_full_words<=weight_load_bytes>>2;
    state<=CHECK_BOUNDS;
   end
   CHECK_BOUNDS:begin
    // Intervals are half-open'''
 assert old in text;text=text.replace(old,new,1)
 return text
if __name__=='__main__':
 p=Path(__file__).resolve().parent/'rtl/simple_k3_engine.sv'
 p.write_text(split_bounds(p.read_text(encoding='utf-8')),encoding='utf-8')
