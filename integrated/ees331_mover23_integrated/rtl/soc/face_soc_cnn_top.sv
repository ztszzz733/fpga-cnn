// Computational SoC harness. The board top adds image_bridge and clock_unit.
// All ports here are internal SoC signals, not FPGA package pins.
module face_soc_cnn_top #(
    parameter logic [31:0] RESET_PC = 32'h0000_0000,
    parameter logic [31:0] IMEM_BASE = 32'h0000_0000,
    parameter logic [31:0] IMEM_SIZE = 32'h0001_0000,
    parameter string IMEM_INIT_FILE = "",
    parameter logic [31:0] SRAM_BASE = 32'h0000_0000,
    parameter logic [31:0] SRAM_SIZE = 32'h0004_0000,
    parameter logic [31:0] CNN_MMIO_BASE = 32'h4000_0000
) (
    input logic clk, rst_n,
    input logic io_mem_req, io_mem_we,
    input logic [31:0] io_mem_addr, io_mem_wdata,
    input logic [3:0] io_mem_be,
    output logic io_mem_gnt, io_mem_rvalid,
    output logic [31:0] io_mem_rdata,
    output logic io_mem_error,
    output logic cnn_mem_fault
);
    logic [31:0] imem_addr, imem_rdata, dmem_addr, dmem_wdata, dmem_rdata;
    logic imem_re, dmem_re, dmem_we;
    logic [3:0] dmem_wstrb;
    logic [31:0] cnn_mmio_addr, cnn_mmio_wdata, cnn_mmio_rdata;
    logic cnn_mmio_re, cnn_mmio_we, cnn_mmio_ready;
    logic [31:0] mem_addr, mem_wdata, mem_rdata;
    logic mem_read, mem_write, mem_ready;

    cpu_core #(.RESET_PC(RESET_PC), .SRAM_BASE(SRAM_BASE), .SRAM_SIZE(SRAM_SIZE),
        .CNN_MMIO_BASE(CNN_MMIO_BASE)) u_cpu_core (
        .mmio_addr(cnn_mmio_addr), .mmio_wdata(cnn_mmio_wdata),
        .mmio_re(cnn_mmio_re), .mmio_we(cnn_mmio_we),
        .mmio_rdata(cnn_mmio_rdata), .mmio_ready(cnn_mmio_ready), .*
    );
    imem_rom #(.IMEM_BASE(IMEM_BASE), .IMEM_SIZE(IMEM_SIZE),
        .INIT_FILE(IMEM_INIT_FILE)) u_imem (.*);
    datasram #(.SRAM_BASE(SRAM_BASE), .SRAM_SIZE(SRAM_SIZE)) u_datasram (.*);
    mobilefacenet_accelerator_top #(.BASE_ADDR(CNN_MMIO_BASE)) u_cnn (
        .clk(clk), .rst_n(rst_n),
        .mmio_addr(cnn_mmio_addr), .mmio_wdata(cnn_mmio_wdata),
        .mmio_re(cnn_mmio_re), .mmio_we(cnn_mmio_we),
        .mmio_rdata(cnn_mmio_rdata), .mmio_ready(cnn_mmio_ready),
        .mem_addr(mem_addr), .mem_wdata(mem_wdata),
        .mem_read(mem_read), .mem_write(mem_write),
        .mem_rdata(mem_rdata), .mem_ready(mem_ready)
    );
endmodule
