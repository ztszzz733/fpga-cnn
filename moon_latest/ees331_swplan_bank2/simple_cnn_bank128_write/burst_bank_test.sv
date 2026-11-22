module burst_bank_test #(parameter bit BURST_READ=1, parameter bit READ64=1, parameter bit BULK=READ64, parameter bit WRITE128=1, parameter integer LOCAL_BYTES=192*1024)(
 input wire clk,rst_n,mmio_re,mmio_we,input wire [31:0] mmio_addr,mmio_wdata,
 output wire [31:0] mmio_rdata,output wire [3:0] unit_done,unit_error,unit_busy,unit_work,
 output wire [3:0] span_accept,span_weight,output wire [51:0] span_bytes,
 output wire [3:0] cnn_valid,cnn_ready,cnn_write,cnn_byte,cnn_double,cnn_quad,cnn_response,
 `ifndef SYNTHESIS
 output wire [1:0] used_bank,dma_banks,
`endif
 output wire cnn_mem_fault,input wire [31:0] cache_csr_addr,cache_csr_wdata,
 input wire cache_csr_we,cache_csr_re,output wire [31:0] cache_csr_rdata,
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
 wire [127:0] cnn_addr;
 wire [511:0] cnn_wdata;
 wire [255:0] cnn_rdata;
 cnn_simple_top #(.BURST_READ(BURST_READ),.READ64(READ64),.BULK(BULK),.WRITE128(WRITE128)) cnn(.clk,.rst_n,.memory_fault(cnn_mem_fault),
  .mmio_re,.mmio_we,.mmio_addr,.mmio_wdata,.mmio_rdata,.mmio_ready(),
  .mem_valid(cnn_valid),.mem_ready(cnn_ready),.mem_write(cnn_write),.mem_byte(cnn_byte),.mem_double(cnn_double),.mem_quad(cnn_quad),
  .mem_response(cnn_response),.mem_addr(cnn_addr),.mem_rdata(cnn_rdata),.mem_wdata(cnn_wdata),
  .unit_done,.unit_error,.unit_busy,.unit_work,.operator_phase(),.memory_phase(),.mac_counts(),
  .busy(),.done(),.error(),.span_accept,.span_weight,.span_bytes);
 cnn_paged_mover #(.READ64(READ64),.WRITE128(WRITE128),.CLIENTS(4),.LOCAL_BYTES(LOCAL_BYTES)) pager(.cnn_cancel(1'b0),.cache_csr_ready(),.*);
`ifndef SYNTHESIS
 // The regression requires compute and DMA activity in both banks.
 assign used_bank=pager.comp_req;
 assign dma_banks={2{pager.local_valid && pager.local_ready}} &
   (pager.local_addr>=32'(LOCAL_BYTES/2)?2'b10:2'b01);
`endif
endmodule
