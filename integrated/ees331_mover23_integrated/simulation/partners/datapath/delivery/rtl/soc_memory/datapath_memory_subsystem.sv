module datapath_memory_subsystem #(
    parameter bit EXTERNAL_CNN_MMIO = 1'b0,
    parameter bit NATIVE_CNN_MEMORY = 1'b0,
    parameter logic [31:0] IMEM_BASE = 32'h0000_0000,
    parameter logic [31:0] IMEM_SIZE = 32'h0001_0000,
    parameter string IMEM_INIT_FILE = "",
    parameter logic [31:0] SRAM_BASE = 32'h0000_0000,
    parameter logic [31:0] SRAM_SIZE = 32'h0004_0000,
    parameter logic [31:0] CNN_MMIO_BASE = 32'h4000_0000
) (
    input  logic        clk,
    input  logic        rst_n,

    input  logic [31:0] imem_addr,
    input  logic        imem_re,
    output logic [31:0] imem_rdata,

    input  logic [31:0] dmem_addr,
    input  logic [31:0] dmem_wdata,
    input  logic [3:0]  dmem_wstrb,
    input  logic        dmem_re,
    input  logic        dmem_we,
    output logic [31:0] dmem_rdata,

    input  logic [31:0] mmio_addr,
    input  logic [31:0] mmio_wdata,
    input  logic        mmio_re,
    input  logic        mmio_we,
    output logic [31:0] mmio_rdata,
    output logic        mmio_ready,

    input  logic        io_mem_req,
    input  logic        io_mem_we,
    input  logic [31:0] io_mem_addr,
    input  logic [31:0] io_mem_wdata,
    input  logic [3:0]  io_mem_be,
    output logic        io_mem_gnt,
    output logic        io_mem_rvalid,
    output logic [31:0] io_mem_rdata,
    output logic        io_mem_error,

    input  logic        cnn_mem_req,
    input  logic        cnn_mem_we,
    input  logic [31:0] cnn_mem_addr,
    input  logic [31:0] cnn_mem_wdata,
    input  logic [3:0]  cnn_mem_be,
    output logic        cnn_mem_gnt,
    output logic        cnn_mem_rvalid,
    output logic [31:0] cnn_mem_rdata,
    output logic        cnn_mem_error,

    output logic [31:0] CONTROL,
    input  logic [31:0] STATUS,
    output logic [31:0] INPUT_ADDR,
    output logic [31:0] OUTPUT_ADDR,
    output logic [31:0] WEIGHT_ADDR,
    output logic [31:0] BIAS_ADDR,
    output logic [31:0] IMAGE_SIZE,
    output logic [31:0] CHANNELS,
    output logic [31:0] CNN_PARAM,

    output logic [31:0] cnn_mmio_addr, cnn_mmio_wdata,
    output logic        cnn_mmio_re, cnn_mmio_we,
    input  logic [31:0] cnn_mmio_rdata,
    input  logic        cnn_mmio_ready,

    input  logic [31:0] mem_addr, mem_wdata,
    input  logic        mem_read, mem_write,
    output logic [31:0] mem_rdata,
    output logic        mem_ready, cnn_mem_fault
);
    logic b_req, b_we, b_gnt, b_rvalid, b_error;
    logic [31:0] b_addr, b_wdata, b_rdata;
    logic [3:0] b_be;
    logic arb_cnn_req, arb_cnn_we, arb_cnn_gnt, arb_cnn_rvalid, arb_cnn_error;
    logic [31:0] arb_cnn_addr, arb_cnn_wdata, arb_cnn_rdata;
    logic [3:0] arb_cnn_be;

    generate if (NATIVE_CNN_MEMORY) begin : g_native_cnn
        logic read_pending;
        assign arb_cnn_req = rst_n && !cnn_mem_fault && !read_pending &&
                             (mem_read ^ mem_write);
        assign arb_cnn_we = mem_write;
        assign arb_cnn_addr = mem_addr;
        assign arb_cnn_wdata = mem_wdata;
        assign arb_cnn_be = mem_write ? 4'b1111 : 4'b0000;
        assign mem_rdata = arb_cnn_rdata;
        // Grant commits a write; reads must wait for the SRAM response.
        assign mem_ready = rst_n && !cnn_mem_fault && !arb_cnn_error &&
                           ((arb_cnn_req && mem_write && arb_cnn_gnt) ||
                            (read_pending && arb_cnn_rvalid));
        always_ff @(posedge clk) begin
            if (!rst_n) begin
                read_pending <= 1'b0;
                cnn_mem_fault <= 1'b0;
            end else begin
                if (arb_cnn_req && arb_cnn_gnt && !mem_write)
                    read_pending <= 1'b1;
                if (read_pending && arb_cnn_rvalid) read_pending <= 1'b0;
                // FPGA1 has no memory error input. Stop on a failed transfer
                // until a coordinated system reset; never report success.
                if ((mem_read && mem_write) ||
                    (arb_cnn_error && ((arb_cnn_req && mem_write && arb_cnn_gnt) ||
                                       (read_pending && arb_cnn_rvalid))))
                    cnn_mem_fault <= 1'b1;
            end
        end
        assign cnn_mem_gnt = 1'b0;
        assign cnn_mem_rvalid = 1'b0;
        assign cnn_mem_rdata = 32'b0;
        assign cnn_mem_error = 1'b0;
    end else begin : g_b1_cnn
        assign arb_cnn_req = cnn_mem_req;
        assign arb_cnn_we = cnn_mem_we;
        assign arb_cnn_addr = cnn_mem_addr;
        assign arb_cnn_wdata = cnn_mem_wdata;
        assign arb_cnn_be = cnn_mem_be;
        assign cnn_mem_gnt = arb_cnn_gnt;
        assign cnn_mem_rvalid = arb_cnn_rvalid;
        assign cnn_mem_rdata = arb_cnn_rdata;
        assign cnn_mem_error = arb_cnn_error;
        assign mem_rdata = 32'b0;
        assign mem_ready = 1'b0;
        assign cnn_mem_fault = 1'b0;
    end endgenerate

    imem_rom #(
        .IMEM_BASE(IMEM_BASE), .IMEM_SIZE(IMEM_SIZE),
        .INIT_FILE(IMEM_INIT_FILE)
    ) u_imem (
        .clk(clk), .rst_n(rst_n), .imem_addr(imem_addr),
        .imem_re(imem_re), .imem_rdata(imem_rdata)
    );

    data_sram_tdp #(
        .SRAM_BASE(SRAM_BASE), .SRAM_SIZE(SRAM_SIZE)
    ) u_data_sram (
        .clk(clk), .rst_n(rst_n),
        .a_addr(dmem_addr), .a_wdata(dmem_wdata), .a_wstrb(dmem_wstrb),
        .a_re(dmem_re), .a_we(dmem_we), .a_rdata(dmem_rdata),
        .b_req(b_req), .b_we(b_we), .b_addr(b_addr), .b_wdata(b_wdata),
        .b_be(b_be), .b_gnt(b_gnt), .b_rvalid(b_rvalid),
        .b_rdata(b_rdata), .b_error(b_error)
    );

    sram_b_arbiter u_b_arbiter (
        .clk(clk), .rst_n(rst_n),
        .io_mem_req(io_mem_req), .io_mem_we(io_mem_we),
        .io_mem_addr(io_mem_addr), .io_mem_wdata(io_mem_wdata),
        .io_mem_be(io_mem_be), .io_mem_gnt(io_mem_gnt),
        .io_mem_rvalid(io_mem_rvalid), .io_mem_rdata(io_mem_rdata),
        .io_mem_error(io_mem_error),
        .cnn_mem_req(arb_cnn_req), .cnn_mem_we(arb_cnn_we),
        .cnn_mem_addr(arb_cnn_addr), .cnn_mem_wdata(arb_cnn_wdata),
        .cnn_mem_be(arb_cnn_be), .cnn_mem_gnt(arb_cnn_gnt),
        .cnn_mem_rvalid(arb_cnn_rvalid), .cnn_mem_rdata(arb_cnn_rdata),
        .cnn_mem_error(arb_cnn_error),
        .b_req(b_req), .b_we(b_we), .b_addr(b_addr), .b_wdata(b_wdata),
        .b_be(b_be), .b_gnt(b_gnt), .b_rvalid(b_rvalid),
        .b_rdata(b_rdata), .b_error(b_error)
    );

    assign cnn_mmio_addr = mmio_addr;
    assign cnn_mmio_wdata = mmio_wdata;
    assign cnn_mmio_re = EXTERNAL_CNN_MMIO && rst_n && mmio_re;
    assign cnn_mmio_we = EXTERNAL_CNN_MMIO && rst_n && mmio_we;

    generate if (EXTERNAL_CNN_MMIO) begin : g_external_cnn
        assign mmio_rdata = cnn_mmio_rdata;
        assign mmio_ready = cnn_mmio_ready;
        assign CONTROL = 32'b0;
        assign INPUT_ADDR = 32'b0;
        assign OUTPUT_ADDR = 32'b0;
        assign WEIGHT_ADDR = 32'b0;
        assign BIAS_ADDR = 32'b0;
        assign IMAGE_SIZE = 32'b0;
        assign CHANNELS = 32'b0;
        assign CNN_PARAM = 32'b0;
    end else begin : g_legacy_cnn
    cnn_mmio_regs #(.CNN_MMIO_BASE(CNN_MMIO_BASE)) u_cnn_mmio (
        .clk(clk), .rst_n(rst_n),
        .mmio_addr(mmio_addr), .mmio_wdata(mmio_wdata),
        .mmio_re(mmio_re), .mmio_we(mmio_we),
        .mmio_rdata(mmio_rdata), .mmio_ready(mmio_ready),
        .CONTROL(CONTROL), .STATUS(STATUS),
        .INPUT_ADDR(INPUT_ADDR), .OUTPUT_ADDR(OUTPUT_ADDR),
        .WEIGHT_ADDR(WEIGHT_ADDR), .BIAS_ADDR(BIAS_ADDR),
        .IMAGE_SIZE(IMAGE_SIZE), .CHANNELS(CHANNELS),
        .CNN_PARAM(CNN_PARAM)
    );
    end endgenerate
endmodule
