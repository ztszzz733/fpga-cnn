module shared_post_mmio_top(
 input wire clk,rst_n,input wire [31:0] cnn_mmio_addr,cnn_mmio_wdata,
 input wire cnn_mmio_re,cnn_mmio_we,output wire [31:0] cnn_mmio_rdata,output wire cnn_mmio_ready,
 output wire [11:0] mem_valid,mem_write,mem_byte,output wire [383:0] mem_addr,mem_wdata,
 input wire [11:0] mem_ready,mem_response,input wire [383:0] mem_rdata,input wire cnn_mem_fault,
 output wire cnn_cancel,busy,done,error,
 output wire [11:0] unit_start,unit_active,completion_pulse,operator_busy,operator_work,
 output wire [10:0] completed_count,
 output wire [7:0] waiting,output wire [1:0] owned,output wire [5:0] owner_id,output wire [7:0] fifo_level
);
 cnn_ees331 #(.K3_UNITS(2),.K1_UNITS(6),.POST_UNITS(2),.LATEST_OPERATORS(1),.ENABLE_DW7(0),.SHARED_POST_STREAM(1)) dut(
  .clk(clk),.rst_n(rst_n),.cnn_mmio_addr(cnn_mmio_addr),.cnn_mmio_wdata(cnn_mmio_wdata),.cnn_mmio_re(cnn_mmio_re),.cnn_mmio_we(cnn_mmio_we),
  .cnn_mmio_rdata(cnn_mmio_rdata),.cnn_mmio_ready(cnn_mmio_ready),.cnn_valid(mem_valid),.cnn_write(mem_write),.cnn_byte(mem_byte),
  .cnn_addr(mem_addr),.cnn_wdata(mem_wdata),.cnn_ready(mem_ready),.cnn_response(mem_response),.cnn_rdata(mem_rdata),
  .cnn_cancel(cnn_cancel),.cnn_mem_fault(cnn_mem_fault),.busy(busy),.done(done),.error(error),
  .unit_start(unit_start),.unit_active(unit_active),.completion_pulse(completion_pulse),.operator_busy(operator_busy),.operator_work(operator_work),
  .unit_node(),.completed_count(completed_count));
 assign waiting=dut.core.shared_backend.pool.waiting;assign owned=dut.core.shared_backend.pool.owned;
 assign owner_id=dut.core.shared_backend.pool.owner_id;assign fifo_level=dut.core.shared_backend.pool.fifo_level;
endmodule
