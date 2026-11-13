// Isolated CNN replacement boundary. Build ONLY with generated nv_small RTL.
// Existing SoC's 11-client SRAM boundary is retained; clients 0/1 are used.
module nvdla_cnn_top #(
    parameter logic [31:0] MMIO_BASE=32'h40000000,
    parameter logic [31:0] SRAM_BASE=0,SRAM_SIZE=32'h40000
)(
    input logic clk,rst_n,
    input logic [31:0] mmio_addr,mmio_wdata,input logic mmio_re,mmio_we,
    output logic [31:0] mmio_rdata,output logic mmio_ready,
    output wire [10:0] cnn_valid,cnn_write,cnn_byte,
    output wire [351:0] cnn_addr,cnn_wdata,
    input wire [10:0] cnn_ready,cnn_response,input wire [351:0] cnn_rdata,
    input logic cnn_mem_fault,output wire cnn_cancel,
    output logic irq,fault,
    output logic [1:0] config_state,output logic [2:0] read_state,write_state,
    output logic [31:0] read_beats,write_beats
);
    wire csb_valid,csb_ready,csb_write,csb_nposted,csb_rvalid,csb_wr_complete;
    wire [15:0] csb_addr;
    wire [31:0] csb_wdata,csb_rdata;
    wire config_fault,bridge_fault;
    wire arvalid,arready,rvalid,rready,rlast,awvalid,awready,wvalid,wready,wlast,bvalid,bready;
    wire [7:0] arid,rid,awid,bid,wstrb;
    wire [3:0] arlen,awlen;
    wire [31:0] araddr,awaddr;
    wire [63:0] rdata,wdata;
    assign fault=config_fault||bridge_fault||cnn_mem_fault;
    assign cnn_cancel=bridge_fault;
    assign cnn_valid[10:2]=0;
    assign cnn_write[10:2]=0;
    assign cnn_byte[10:2]=0;
    assign cnn_addr[351:64]=0;
    assign cnn_wdata[351:64]=0;
    nvdla_csb_adapter #(.MMIO_BASE(MMIO_BASE)) control_bridge (
        .clk,.rst_n,.mmio_addr,.mmio_wdata,.mmio_we,.mmio_re,.mmio_rdata,.mmio_ready,
        .csb_valid,.csb_ready,.csb_addr,.csb_wdata,.csb_write,.csb_nposted,
        .csb_rvalid,.csb_rdata,.csb_wr_complete,.config_state,.config_fault
    );
    nvdla_sram_bridge #(.SRAM_BASE(SRAM_BASE),.SRAM_SIZE(SRAM_SIZE)) memory_bridge (
        .clk,.rst_n,.arvalid,.arready,.arid,.arlen,.araddr,.rvalid,.rready,.rid,.rlast,.rdata,
        .awvalid,.awready,.awid,.awlen,.awaddr,.wvalid,.wready,.wdata,.wstrb,.wlast,
        .bvalid,.bready,.bid,.mem_valid(cnn_valid[1:0]),.mem_write(cnn_write[1:0]),
        .mem_byte(cnn_byte[1:0]),.mem_addr(cnn_addr[63:0]),.mem_wdata(cnn_wdata[63:0]),
        .mem_ready(cnn_ready[1:0]),.mem_response(cnn_response[1:0]),.mem_rdata(cnn_rdata[63:0]),
        .mem_fault(cnn_mem_fault),.bridge_fault,.read_state,.write_state,.read_beats,.write_beats
    );
    NV_nvdla engine (
        .dla_core_clk(clk),.dla_csb_clk(clk),.dla_reset_rstn(rst_n),.direct_reset_(rst_n),
        .global_clk_ovr_on(1'b0),.tmc2slcg_disable_clock_gating(1'b0),.test_mode(1'b0),
        .csb2nvdla_valid(csb_valid),.csb2nvdla_ready(csb_ready),.csb2nvdla_addr(csb_addr),
        .csb2nvdla_wdat(csb_wdata),.csb2nvdla_write(csb_write),.csb2nvdla_nposted(csb_nposted),
        .nvdla2csb_valid(csb_rvalid),.nvdla2csb_data(csb_rdata),.nvdla2csb_wr_complete(csb_wr_complete),
        .nvdla_core2dbb_ar_arvalid(arvalid),.nvdla_core2dbb_ar_arready(arready),
        .nvdla_core2dbb_ar_arid(arid),.nvdla_core2dbb_ar_arlen(arlen),.nvdla_core2dbb_ar_araddr(araddr),
        .nvdla_core2dbb_r_rvalid(rvalid),.nvdla_core2dbb_r_rready(rready),
        .nvdla_core2dbb_r_rid(rid),.nvdla_core2dbb_r_rlast(rlast),.nvdla_core2dbb_r_rdata(rdata),
        .nvdla_core2dbb_aw_awvalid(awvalid),.nvdla_core2dbb_aw_awready(awready),
        .nvdla_core2dbb_aw_awid(awid),.nvdla_core2dbb_aw_awlen(awlen),.nvdla_core2dbb_aw_awaddr(awaddr),
        .nvdla_core2dbb_w_wvalid(wvalid),.nvdla_core2dbb_w_wready(wready),
        .nvdla_core2dbb_w_wdata(wdata),.nvdla_core2dbb_w_wstrb(wstrb),.nvdla_core2dbb_w_wlast(wlast),
        .nvdla_core2dbb_b_bvalid(bvalid),.nvdla_core2dbb_b_bready(bready),.nvdla_core2dbb_b_bid(bid),
        .dla_intr(irq),.nvdla_pwrbus_ram_c_pd(32'd0),.nvdla_pwrbus_ram_ma_pd(32'd0),
        .nvdla_pwrbus_ram_mb_pd(32'd0),.nvdla_pwrbus_ram_p_pd(32'd0),
        .nvdla_pwrbus_ram_o_pd(32'd0),.nvdla_pwrbus_ram_a_pd(32'd0)
    );
endmodule
