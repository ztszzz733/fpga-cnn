module cnn_storage_top(
 input wire clk,rst_n,memory_fault,
 input wire [31:0] mmio_addr,mmio_wdata,
 input wire mmio_re,mmio_we,output wire [31:0] mmio_rdata,output wire mmio_ready,
 input wire [31:0] cache_csr_addr,cache_csr_wdata,input wire cache_csr_re,cache_csr_we,
 output wire [31:0] cache_csr_rdata,output wire cache_csr_ready,
 output wire [3:0] unit_busy,unit_done,unit_error,unit_work,
 output wire [15:0] operator_phase,output wire [11:0] memory_phase,
 output wire [3:0] mem_valid,mem_write,mem_byte,mem_ready,mem_response,
 output wire [127:0] mem_addr,mem_wdata,
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
 wire [127:0] mem_rdata;
 wire cnn_mem_fault;
 cnn_simple_top cnn(.clk,.rst_n,.memory_fault(memory_fault|cnn_mem_fault),
  .mmio_addr,.mmio_wdata,.mmio_re,.mmio_we,.mmio_rdata,.mmio_ready,
  .mem_valid,.mem_write,.mem_byte,.mem_ready,.mem_response,.mem_addr,.mem_wdata,.mem_rdata,
  .unit_busy,.unit_done,.unit_error,.unit_work,.operator_phase,.memory_phase,.mac_counts(),.busy(),.done(),.error());
 cnn_paged_mover #(.CLIENTS(4),.LOCAL_BYTES(401408),.LOGICAL_BYTES(32'h04000000)) cache(
  .clk,.rst_n,.cnn_cancel(1'b0),.cnn_mem_fault,
  .cnn_valid(mem_valid),.cnn_write(mem_write),.cnn_byte(mem_byte),.cnn_addr(mem_addr),.cnn_wdata(mem_wdata),
  .cnn_ready(mem_ready),.cnn_response(mem_response),.cnn_rdata(mem_rdata),
  .cache_csr_addr,.cache_csr_wdata,.cache_csr_re,.cache_csr_we,.cache_csr_rdata,.cache_csr_ready,.*);
 endmodule
