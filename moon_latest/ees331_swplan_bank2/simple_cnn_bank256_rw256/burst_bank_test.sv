module burst_bank_test #(parameter bit BURST_READ=1, parameter bit READ64=1, parameter bit BULK=READ64, parameter bit PACKED_WRITE=1, parameter integer LOCAL_BYTES=192*1024,
 parameter integer WRITE_BITS=256,
 parameter bit K3_FIFO=1,K1_EXTRA=1,K3_WIDE=1,
 parameter integer K1_WEIGHT_CACHE_BYTES=2048, parameter bit K3_CI_PAIR=1, K3_CI_QUAD=1, READ256=1,
 localparam integer READ_BITS=(READ256 && PACKED_WRITE && WRITE_BITS==256)?256:64
)(
 input wire clk,rst_n,mmio_re,mmio_we,input wire [31:0] mmio_addr,mmio_wdata,
 output wire [31:0] mmio_rdata,output wire [3:0] unit_done,unit_error,unit_busy,unit_work,
 output wire [3:0] span_accept,span_weight,output wire [51:0] span_bytes,
 output wire [3:0] cnn_valid,cnn_ready,cnn_write,cnn_byte,cnn_double,cnn_wide,cnn_response,
 `ifndef SYNTHESIS
 output wire [1:0] used_bank,dma_banks,
 output wire [5:0] native_write_bytes,
 output wire [1:0] k3_writing,k3_fifo_stall,k1_small_panel,
 output wire [21:0] k3_fifo_level,
 output wire [15:0] operator_phase,
 output wire [3:0] read_active,write_active,mem_write_beat,
 output wire [2:0] pager_phase,
 output wire [1:0] k1_layer_cached,k3_pair_mode,k3_quad_mode,
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
 wire [4*WRITE_BITS-1:0] cnn_wdata;
 wire [4*READ_BITS-1:0] cnn_rdata;
 cnn_simple_top #(.BURST_READ(BURST_READ),.READ64(READ64),.BULK(BULK),.PACKED_WRITE(PACKED_WRITE),.WRITE_BITS(WRITE_BITS),.K3_FIFO(K3_FIFO),.K1_EXTRA(K1_EXTRA),.K3_WIDE(K3_WIDE),.K1_WEIGHT_CACHE_BYTES(K1_WEIGHT_CACHE_BYTES),.K3_CI_PAIR(K3_CI_PAIR),.K3_CI_QUAD(K3_CI_QUAD),.READ256(READ256)) cnn(.clk,.rst_n,.memory_fault(cnn_mem_fault),
  .mmio_re,.mmio_we,.mmio_addr,.mmio_wdata,.mmio_rdata,.mmio_ready(),
  .mem_valid(cnn_valid),.mem_ready(cnn_ready),.mem_write(cnn_write),.mem_byte(cnn_byte),.mem_double(cnn_double),.mem_wide(cnn_wide),
  .mem_response(cnn_response),.mem_addr(cnn_addr),.mem_rdata(cnn_rdata),.mem_wdata(cnn_wdata),
  .unit_done,.unit_error,.unit_busy,.unit_work,
`ifdef SYNTHESIS
  .operator_phase(),
`else
  .operator_phase,
`endif
  .memory_phase(),.mac_counts(),
  .busy(),.done(),.error(),.span_accept,.span_weight,.span_bytes);
 cnn_paged_mover #(.READ64(READ64),.PACKED_WRITE(PACKED_WRITE),.WRITE_BITS(WRITE_BITS),.CLIENTS(4),.LOCAL_BYTES(LOCAL_BYTES),.READ256(READ256)) pager(.cnn_cancel(1'b0),.cache_csr_ready(),.*);
`ifndef SYNTHESIS
 // The regression requires compute and DMA activity in both banks.
 assign used_bank=pager.comp_req;
 assign pager_phase=pager.state;
 assign k3_quad_mode={cnn.unit[1].k3.engine.quad_mode,cnn.unit[0].k3.engine.quad_mode};
 assign k3_pair_mode={cnn.unit[1].k3.engine.pair_mode,cnn.unit[0].k3.engine.pair_mode};
 assign k1_layer_cached={cnn.unit[3].k1.engine.layer_cached,cnn.unit[2].k1.engine.layer_cached};
 assign mem_write_beat=cnn_valid & cnn_ready & cnn_write;
 for(genvar u=0;u<4;u++)begin:captures
  assign read_active[u]=cnn.unit[u].long_reads.read_busy;
  assign write_active[u]=cnn.unit[u].long_reads.write_busy;
 end
 assign k3_writing={cnn.unit[1].long_reads.write_busy,cnn.unit[0].long_reads.write_busy};
 if(K3_FIFO)begin:result_stalls
  assign k3_fifo_stall={cnn.cw[1] && cnn.cv[1] && !cnn.unit[1].long_reads.buffered_result.space,
                        cnn.cw[0] && cnn.cv[0] && !cnn.unit[0].long_reads.buffered_result.space};
  assign k3_fifo_level={cnn.unit[1].long_reads.buffered_result.results.count,
                        cnn.unit[0].long_reads.buffered_result.results.count};
 end else begin
  assign k3_fifo_stall=0;
  assign k3_fifo_level=0;
 end
 assign k1_small_panel={cnn.unit[3].k1.engine.tile_start && cnn.unit[3].k1.engine.small_result_slot,
                        cnn.unit[2].k1.engine.tile_start && cnn.unit[2].k1.engine.small_result_slot};
 assign native_write_bytes=6'(WRITE_BITS/8);
 assign dma_banks={2{pager.local_valid && pager.local_ready}} &
   (pager.local_addr>=32'(LOCAL_BYTES/2)?2'b10:2'b01);
`endif
endmodule
