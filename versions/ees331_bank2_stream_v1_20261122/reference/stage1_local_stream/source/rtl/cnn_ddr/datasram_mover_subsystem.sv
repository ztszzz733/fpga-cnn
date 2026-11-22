// New 23-client system memory path: one-cycle CPU RAM and paged CNN tile RAM.
// DATA MOVER is the only HP0 master in this variant.
module datasram_mover_subsystem #(
 parameter integer CLIENTS=23,
 parameter integer LOCAL_BYTES=32768,
 parameter integer CPU_RAM_BYTES=16384,
 parameter logic [31:0] LOGICAL_BYTES=32'h01000000,
 parameter logic [31:0] DDR_BASE=32'h10000000
)(
 input logic clk,rst_n,
 input logic [31:0] dmem_addr,dmem_wdata,
 input logic [3:0] dmem_wstrb,
 input logic dmem_re,dmem_we,
 output wire [31:0] dmem_rdata,
 input wire [CLIENTS-1:0] cnn_valid,cnn_write,cnn_byte,
 input wire [CLIENTS*32-1:0] cnn_addr,cnn_wdata,
 output wire [CLIENTS-1:0] cnn_ready,cnn_response,
 output wire [CLIENTS*32-1:0] cnn_rdata,
 input wire cnn_cancel,
 output wire cnn_mem_fault,
 input logic [31:0] cache_csr_addr,cache_csr_wdata,
 input logic cache_csr_re,cache_csr_we,
 output wire [31:0] cache_csr_rdata,
 output wire cache_csr_ready,
 output wire [31:0] S_AXI_HP0_AWADDR,S_AXI_HP0_ARADDR,
 output wire [63:0] S_AXI_HP0_WDATA,
 input wire [63:0] S_AXI_HP0_RDATA,
 output wire [5:0] S_AXI_HP0_AWID,S_AXI_HP0_ARID,S_AXI_HP0_WID,
 input wire [5:0] S_AXI_HP0_BID,S_AXI_HP0_RID,
 output wire [3:0] S_AXI_HP0_AWLEN,S_AXI_HP0_ARLEN,
 output wire [2:0] S_AXI_HP0_AWSIZE,S_AXI_HP0_ARSIZE,
 output wire [1:0] S_AXI_HP0_AWBURST,S_AXI_HP0_ARBURST,
 output wire [1:0] S_AXI_HP0_AWLOCK,S_AXI_HP0_ARLOCK,
 output wire [3:0] S_AXI_HP0_AWCACHE,S_AXI_HP0_ARCACHE,
 output wire [2:0] S_AXI_HP0_AWPROT,S_AXI_HP0_ARPROT,
 output wire [3:0] S_AXI_HP0_AWQOS,S_AXI_HP0_ARQOS,
 output wire [7:0] S_AXI_HP0_WSTRB,
 output wire S_AXI_HP0_AWVALID,S_AXI_HP0_WVALID,S_AXI_HP0_WLAST,
 output wire S_AXI_HP0_BREADY,S_AXI_HP0_ARVALID,S_AXI_HP0_RREADY,
 input wire S_AXI_HP0_AWREADY,S_AXI_HP0_WREADY,S_AXI_HP0_BVALID,
 input wire S_AXI_HP0_ARREADY,S_AXI_HP0_RVALID,S_AXI_HP0_RLAST,
 input wire [1:0] S_AXI_HP0_BRESP,S_AXI_HP0_RRESP
);
 download_ram #(.BYTES(CPU_RAM_BYTES),.BASE(32'h00000000)) cpu_ram(
  .clk,.rst_n,.app_reset(1'b0),.app_halted(1'b0),
  .cpu_addr(dmem_addr),.cpu_wdata(dmem_wdata),.cpu_re(dmem_re),
  .cpu_we(dmem_we),.cpu_wstrb(dmem_wstrb),.cpu_rdata(dmem_rdata),
  .cpu_error(),.ld_valid(1'b0),.ld_write(1'b0),.ld_ready(),
  .ld_addr(32'b0),.ld_wdata(32'b0),.ld_wstrb(4'b0),
  .ld_rsp_valid(),.ld_error(),.ld_rsp_ready(1'b0),.ld_rdata()
 );
 cnn_paged_mover #(.CLIENTS(CLIENTS),.LOCAL_BYTES(LOCAL_BYTES),
  .LOGICAL_BYTES(LOGICAL_BYTES),.DDR_BASE(DDR_BASE)) cache(.*);
`ifndef SYNTHESIS
 initial assert(CPU_RAM_BYTES>=8 && (CPU_RAM_BYTES & (CPU_RAM_BYTES-1))==0)
  else $fatal(1,"CPU local RAM geometry");
`endif
endmodule
