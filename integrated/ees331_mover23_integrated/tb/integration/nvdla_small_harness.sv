// Real NVDLA + production banked SRAM. Host drives CPU-style MMIO and A port.
// No behavioral replacement for convolution, pooling, DMA or CSB.
module nvdla_small_harness (
    input logic clk,rst_n,
    input logic [31:0] mmio_addr,mmio_wdata,input logic mmio_re,mmio_we,
    output logic [31:0] mmio_rdata,output logic mmio_ready,
    input logic [31:0] host_addr,host_wdata,input logic [3:0] host_strb,
    input logic host_re,host_we,output logic [31:0] host_rdata,
    output logic irq,fault,
    output logic [1:0] config_state,output logic [2:0] read_state,write_state,
    output logic [31:0] read_beats,write_beats,
    output wire [10:0] cnn_valid,cnn_ready,cnn_response,cnn_write
);
    wire [10:0] cnn_byte;
    wire [351:0] cnn_addr,cnn_wdata,cnn_rdata;
    wire cnn_mem_fault,cnn_cancel;
    nvdla_cnn_top cnn (.*);
    datasram_banked memory (
        .clk,.rst_n,.dmem_addr(host_addr),.dmem_wdata(host_wdata),.dmem_wstrb(host_strb),
        .dmem_re(host_re),.dmem_we(host_we),.dmem_rdata(host_rdata),
        .cnn_valid,.cnn_write,.cnn_byte,.cnn_addr,.cnn_wdata,.cnn_ready,.cnn_response,.cnn_rdata,
        .cnn_cancel,.cnn_mem_fault,.io_mem_req(1'b0),.io_mem_we(1'b0),.io_mem_addr(32'd0),
        .io_mem_wdata(32'd0),.io_mem_be(4'd0),.io_mem_gnt(),.io_mem_rvalid(),.io_mem_rdata(),.io_mem_error()
    );
endmodule
