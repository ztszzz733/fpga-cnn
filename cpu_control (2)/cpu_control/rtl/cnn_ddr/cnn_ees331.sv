// Zero-wait CPU-facing register bank and the compact four-image CNN.
// All offsets are local to this module; image_control_bridge owns the aperture.
module cnn_ees331 #(
 parameter integer STEPS=256,LW=$clog2(STEPS),IW=LW+2,
 parameter integer K3_UNITS=2,K1_UNITS=4,POST_UNITS=1,
 parameter integer UNITS=K3_UNITS+K1_UNITS+POST_UNITS+3
)(
 input logic clk,rst_n,
 input logic [31:0] cnn_mmio_addr,cnn_mmio_wdata,
 input logic cnn_mmio_re,cnn_mmio_we,
 output logic [31:0] cnn_mmio_rdata,output wire cnn_mmio_ready,
 output wire [UNITS-1:0] cnn_valid,cnn_write,cnn_byte,
 output wire [UNITS*32-1:0] cnn_addr,cnn_wdata,
 input logic [UNITS-1:0] cnn_ready,cnn_response,
 input logic [UNITS*32-1:0] cnn_rdata,
 output wire cnn_cancel,input logic cnn_mem_fault,
 output wire busy,done,error,
 output wire [UNITS-1:0] unit_start,unit_active,completion_pulse,operator_busy,operator_work,
 output wire [UNITS-1:0][IW-1:0] unit_node,
 output wire [IW:0] completed_count
);
 logic clear,start,template_valid,address_valid,frame_valid,result_ready;
 logic [31:0] staging[20];logic [4:0] word_index;
 logic [LW-1:0] template_index;
 logic [2:0] image_count;logic [UNITS-1:0] unit_enable;
 logic [1:0] address_slot;logic [31:0] image_base,workspace_base,address_frame;
 logic [31:0] epoch,ack_frame,ack_epoch,command_error;
 wire configuration_ready,frame_ready,core_error,compute_done,result_valid;
 wire [3:0] frames_ready;wire [LW:0] loaded_steps;
 wire [31:0] result_frame,result_addr,result_bytes,error_code;
 wire [511:0] template_command;
 for(genvar w=0;w<16;w++)assign template_command[w*32+:32]=staging[w];
 assign cnn_mmio_ready=1'b1;
 assign error=core_error || command_error!=0;
 always_comb begin
  cnn_mmio_rdata=0;
  if(cnn_mmio_re)case(cnn_mmio_addr)
   32'h00:cnn_mmio_rdata=32'h434E4E32;
   32'h04:cnn_mmio_rdata={25'b0,compute_done,result_valid,frame_ready,error,done,busy,configuration_ready};
   32'h0c:cnn_mmio_rdata={29'b0,image_count};
   32'h10:cnn_mmio_rdata=32'(unit_enable);
   32'h14:cnn_mmio_rdata=32'(template_index);
   32'h18:cnn_mmio_rdata={27'b0,word_index};
   32'h1c:cnn_mmio_rdata=staging[word_index];
   32'h20:cnn_mmio_rdata={30'b0,address_slot};
   32'h24:cnn_mmio_rdata=image_base;
   32'h28:cnn_mmio_rdata=workspace_base;
   32'h2c:cnn_mmio_rdata=address_frame;
   32'h30:cnn_mmio_rdata=result_frame;
   32'h34:cnn_mmio_rdata=result_addr;
   32'h38:cnn_mmio_rdata=result_bytes;
   32'h3c:cnn_mmio_rdata=command_error!=0?command_error:error_code;
   32'h40:cnn_mmio_rdata=32'(completed_count);
   32'h44:cnn_mmio_rdata={28'b0,frames_ready};
   32'h48:cnn_mmio_rdata=32'(loaded_steps);
   32'h4c:cnn_mmio_rdata=ack_frame;
   32'h50:cnn_mmio_rdata=ack_epoch;
   32'h54:cnn_mmio_rdata=epoch;
   default:;
  endcase
 end
 always_ff @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   clear<=0;start<=0;template_valid<=0;address_valid<=0;frame_valid<=0;result_ready<=0;
   word_index<=0;template_index<=0;image_count<=4;unit_enable<='1;
   address_slot<=0;image_base<=0;workspace_base<=0;address_frame<=0;epoch<=0;ack_frame<=0;ack_epoch<=0;command_error<=0;
   for(integer w=0;w<20;w++)staging[w]<=0;
  end else begin
   clear<=0;start<=0;template_valid<=0;address_valid<=0;frame_valid<=0;result_ready<=0;
   if(cnn_mmio_we)begin
    case(cnn_mmio_addr)
     32'h08:case(cnn_mmio_wdata)
      32'h01:begin clear<=1;epoch<=epoch+1;command_error<=0;word_index<=0;template_index<=0;end
      32'h02:if(configuration_ready)start<=1;else command_error<=32'h201;
      32'h04:if(configuration_ready)template_valid<=1;else command_error<=32'h202;
      32'h08:if(configuration_ready)address_valid<=1;else command_error<=32'h203;
      32'h10:if(frame_ready)frame_valid<=1;else command_error<=32'h204;
      32'h20:if(result_valid && ack_frame==result_frame && ack_epoch==epoch)result_ready<=1;else command_error<=32'h205;
      default:command_error<=32'h206;
     endcase
     32'h0c:if(configuration_ready && cnn_mmio_wdata>=1 && cnn_mmio_wdata<=4)image_count<=cnn_mmio_wdata[2:0];else command_error<=32'h207;
     32'h10:if(configuration_ready && (cnn_mmio_wdata>>UNITS)==0)unit_enable<=cnn_mmio_wdata[UNITS-1:0];else command_error<=32'h208;
     32'h14:if(configuration_ready && cnn_mmio_wdata<STEPS)template_index<=cnn_mmio_wdata[LW-1:0];else command_error<=32'h209;
     32'h18:if(configuration_ready && cnn_mmio_wdata<20)word_index<=cnn_mmio_wdata[4:0];else command_error<=32'h20a;
     32'h1c:if(configuration_ready)begin staging[word_index]<=cnn_mmio_wdata;word_index<=word_index==19?0:word_index+1;end else command_error<=32'h20b;
     32'h20:if(cnn_mmio_wdata<4)address_slot<=cnn_mmio_wdata[1:0];else command_error<=32'h20c;
     32'h24:if(configuration_ready)image_base<=cnn_mmio_wdata;else command_error<=32'h20d;
     32'h28:if(configuration_ready)workspace_base<=cnn_mmio_wdata;else command_error<=32'h20e;
     32'h2c:address_frame<=cnn_mmio_wdata;
     32'h4c:ack_frame<=cnn_mmio_wdata;
     32'h50:ack_epoch<=cnn_mmio_wdata;
     default:command_error<=32'h20f;
    endcase
   end
  end
 end
 fixed_schedule_compact #(.STEPS(STEPS),.LW(LW),.IW(IW),.K3_UNITS(K3_UNITS),.K1_UNITS(K1_UNITS),.POST_UNITS(POST_UNITS)) core(
  .clk(clk),.rst_n(rst_n),.clear(clear),.start(start),.unit_enable(unit_enable),.image_count(image_count),
  .template_valid(template_valid),.template_index(template_index),.template_command(template_command),
  .template_source_modes(staging[16][3:0]),.template_allocate_slot(staging[16][5:4]),
  .template_use_valid(staging[16][8:6]),.template_use_slots(staging[16][14:9]),.template_result_valid(staging[16][15]),
  .template_dep_valid(staging[16][17:16]),.template_dep0(staging[16][18+:LW]),.template_dep1(staging[17][0+:LW]),
  .template_use_owners({staging[17][24+:LW],staging[17][16+:LW],staging[17][8+:LW]}),
  .template_consumer_count(staging[18][17:16]),.template_consumer0(staging[18][0+:LW]),.template_consumer1(staging[18][8+:LW]),
  .template_result_bytes(staging[19]),.address_valid(address_valid),.address_slot(address_slot),
  .image_base(image_base),.workspace_base(workspace_base),.address_frame(address_frame),
  .configuration_ready(configuration_ready),.loaded_steps(loaded_steps),
  .frame_valid(frame_valid),.frame_slot(address_slot),.frame_id(address_frame),.frame_ready(frame_ready),.frames_ready(frames_ready),
  .result_ready(result_ready),.result_valid(result_valid),.result_accept(),.outputs_pending(),.compute_done(compute_done),
  .busy(busy),.done(done),.error(core_error),.cancel(cnn_cancel),.result_frame(result_frame),.result_addr(result_addr),.result_bytes(result_bytes),
  .result_error(),.error_code(error_code),.external_hold(),.buffer_live(),.buffer_release(),.buffer_allocate(),.buffer_owners(),.wait_buffer(),.wait_input(),
  .mem_valid(cnn_valid),.mem_write(cnn_write),.mem_byte(cnn_byte),.mem_addr(cnn_addr),.mem_wdata(cnn_wdata),
  .mem_ready(cnn_ready),.mem_response(cnn_response),.mem_rdata(cnn_rdata),.memory_fault(cnn_mem_fault),
  .unit_start(unit_start),.unit_active(unit_active),.completion_pulse(completion_pulse),.unit_command(),.unit_node(unit_node),
  .operator_busy(operator_busy),.operator_work(operator_work),.completed_count(completed_count),.completed_mask(),
  .conv_input_reads(),.conv_weight_reads(),.conv_mac_count());
endmodule
