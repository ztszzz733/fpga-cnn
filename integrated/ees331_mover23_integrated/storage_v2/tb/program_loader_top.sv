module program_loader_top(
 input logic clk,rst_n,app_reset,app_halted,
 input logic bus_valid,bus_write,
 output wire bus_ready,
 input logic [31:0] bus_addr,bus_wdata,
 input logic [3:0] bus_wstrb,
 output wire bus_rsp_valid,
 input logic bus_rsp_ready,
 output wire [31:0] bus_rdata,bus_status,
 input logic [31:0] imem_cpu_addr,ram_cpu_addr,
 input logic imem_cpu_re,ram_cpu_re,ram_cpu_we,
 input logic [31:0] ram_cpu_wdata,
 input logic [3:0] ram_cpu_wstrb,
 output wire [31:0] imem_cpu_rdata,ram_cpu_rdata,
 output wire imem_cpu_error,ram_cpu_error
);
 wire imem_valid,imem_write,imem_ready,imem_rsp_valid,imem_error,imem_rsp_ready;
 wire ram_valid,ram_write,ram_ready,ram_rsp_valid,ram_error,ram_rsp_ready;
 wire [31:0] imem_addr,imem_wdata,imem_rdata,ram_addr,ram_wdata,ram_rdata;
 wire [3:0] imem_wstrb,ram_wstrb;
 program_loader_csr loader(
  .clk,.rst_n,.app_halted,.bus_valid,.bus_write,.bus_ready,
  .bus_addr,.bus_wdata,.bus_wstrb,.bus_rsp_valid,.bus_rsp_ready,
  .bus_rdata,.bus_status,
  .imem_valid,.imem_write,.imem_ready,.imem_rsp_valid,.imem_error,
  .imem_addr,.imem_wdata,.imem_wstrb,.imem_rsp_ready,.imem_rdata,
  .ram_valid,.ram_write,.ram_ready,.ram_rsp_valid,.ram_error,
  .ram_addr,.ram_wdata,.ram_wstrb,.ram_rsp_ready,.ram_rdata
 );
 download_ram #(.BYTES(65536),.BASE(0),.READ_ONLY_CPU(1)) imem(
  .clk,.rst_n,.app_reset,.app_halted,.cpu_addr(imem_cpu_addr),
  .cpu_wdata(32'b0),.cpu_re(imem_cpu_re),.cpu_we(1'b0),
  .cpu_wstrb(4'b0),.cpu_rdata(imem_cpu_rdata),.cpu_error(imem_cpu_error),
  .ld_valid(imem_valid),.ld_write(imem_write),.ld_ready(imem_ready),
  .ld_addr(imem_addr),.ld_wdata(imem_wdata),.ld_wstrb(imem_wstrb),
  .ld_rsp_valid(imem_rsp_valid),.ld_error(imem_error),
  .ld_rsp_ready(imem_rsp_ready),.ld_rdata(imem_rdata)
 );
 download_ram #(.BYTES(16384),.BASE(32'h10000)) cpu_ram(
  .clk,.rst_n,.app_reset,.app_halted,.cpu_addr(ram_cpu_addr),
  .cpu_wdata(ram_cpu_wdata),.cpu_re(ram_cpu_re),.cpu_we(ram_cpu_we),
  .cpu_wstrb(ram_cpu_wstrb),.cpu_rdata(ram_cpu_rdata),.cpu_error(ram_cpu_error),
  .ld_valid(ram_valid),.ld_write(ram_write),.ld_ready(ram_ready),
  .ld_addr(ram_addr),.ld_wdata(ram_wdata),.ld_wstrb(ram_wstrb),
  .ld_rsp_valid(ram_rsp_valid),.ld_error(ram_error),
  .ld_rsp_ready(ram_rsp_ready),.ld_rdata(ram_rdata)
 );
endmodule
