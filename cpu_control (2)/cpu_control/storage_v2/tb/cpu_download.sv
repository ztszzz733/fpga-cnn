// Integration fixture, not a production halt controller. app_run is switched
// only at cold start or after the program has entered its final idle loop.
module cpu_download(
 input logic clk,rst_n,app_run,
 input logic target_data,ld_valid,ld_write,ld_rsp_ready,
 input logic [31:0] ld_addr,ld_wdata,
 input logic [3:0] ld_wstrb,
 output wire ld_ready,ld_rsp_valid,ld_error,
 output wire [31:0] ld_rdata,
 output logic done,
 output wire memory_error
);
 wire [31:0] imem_addr,imem_rdata,dmem_addr,dmem_wdata,dmem_rdata,mmio_addr,mmio_wdata;
 wire imem_re,dmem_re,dmem_we,mmio_re,mmio_we;
 wire [3:0] dmem_wstrb;
 wire i_ready,i_valid,i_error,cpu_ierror,d_ready,d_valid,d_error,cpu_derror;
 wire [31:0] i_data,d_data;
 cpu_core #(.SRAM_BASE(32'h10000),.SRAM_SIZE(32'h4000)) cpu(
  .clk(clk),.rst_n(rst_n&&app_run),.imem_addr(imem_addr),.imem_re(imem_re),.imem_rdata(imem_rdata),
  .dmem_addr(dmem_addr),.dmem_wdata(dmem_wdata),.dmem_rdata(dmem_rdata),.dmem_wstrb(dmem_wstrb),.dmem_re(dmem_re),.dmem_we(dmem_we),
  .mmio_addr(mmio_addr),.mmio_wdata(mmio_wdata),.mmio_re(mmio_re),.mmio_we(mmio_we),.mmio_rdata(32'b0),.mmio_ready(1'b1));
 download_ram #(.BYTES(8192),.BASE(0),.READ_ONLY_CPU(1)) imem(
  .clk(clk),.rst_n(rst_n),.app_reset(!app_run),.app_halted(!app_run),
  .cpu_addr(imem_addr),.cpu_re(imem_re),.cpu_we(1'b0),.cpu_wdata(32'b0),.cpu_wstrb(4'b0),.cpu_rdata(imem_rdata),.cpu_error(cpu_ierror),
  .ld_valid(ld_valid&&!target_data),.ld_write(ld_write),.ld_addr(ld_addr),.ld_wdata(ld_wdata),.ld_wstrb(ld_wstrb),
  .ld_ready(i_ready),.ld_rsp_valid(i_valid),.ld_rsp_ready(ld_rsp_ready),.ld_error(i_error),.ld_rdata(i_data));
 download_ram #(.BYTES(16384),.BASE(32'h10000)) data_ram(
  .clk(clk),.rst_n(rst_n),.app_reset(!app_run),.app_halted(!app_run),
  .cpu_addr(dmem_addr),.cpu_re(dmem_re),.cpu_we(dmem_we),.cpu_wdata(dmem_wdata),.cpu_wstrb(dmem_wstrb),.cpu_rdata(dmem_rdata),.cpu_error(cpu_derror),
  .ld_valid(ld_valid&&target_data),.ld_write(ld_write),.ld_addr(ld_addr),.ld_wdata(ld_wdata),.ld_wstrb(ld_wstrb),
  .ld_ready(d_ready),.ld_rsp_valid(d_valid),.ld_rsp_ready(ld_rsp_ready),.ld_error(d_error),.ld_rdata(d_data));
 assign ld_ready=target_data?d_ready:i_ready;assign ld_rsp_valid=target_data?d_valid:i_valid;
 assign ld_error=target_data?d_error:i_error;assign ld_rdata=target_data?d_data:i_data;
 assign memory_error=cpu_ierror||cpu_derror;
 always_ff @(posedge clk) begin
  if(!rst_n || !app_run) done<=0;
  else if(dmem_we && dmem_addr==32'h1000c && dmem_wdata==1) done<=1;
 end
endmodule
