/*
 * CPU + memory boundary. EXTERNAL_CNN_MMIO selects FPGA1's own registers;
 * default zero retains the legacy B1 regression configuration. Both B masters
 * remain external to this module; face_soc_cnn_top connects the real CNN.
 */
module face_soc_cpu_memory_top #(
    parameter bit EXTERNAL_CNN_MMIO = 1'b0,
    parameter bit NATIVE_CNN_MEMORY = 1'b0,
    parameter logic [31:0] RESET_PC = 32'h0000_0000,
    parameter logic [31:0] IMEM_BASE = 32'h0000_0000,
    parameter logic [31:0] IMEM_SIZE = 32'h0001_0000,
    parameter string IMEM_INIT_FILE = "",
    parameter logic [31:0] SRAM_BASE = 32'h0000_0000,
    parameter logic [31:0] SRAM_SIZE = 32'h0004_0000,
    parameter logic [31:0] CNN_MMIO_BASE = 32'h4000_0000,
    parameter logic [31:0] CNN_MMIO_SIZE = 32'h0000_1000
) (
    input  logic        clk,
    input  logic        rst_n,

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
    logic [31:0] instr_d;
    logic [4:0] rs1_d, rs2_d, rd_e, rd_m, rd_w;
    logic regwrite_m, regwrite_w, memread_e;
    logic cmp_eq_e, cmp_lt_e, cmp_ltu_e, mul_busy;
    logic valid_d, valid_e, valid_m, valid_w;
    logic [4:0] rs1_e, rs2_e;
    logic uses_rs1_e, uses_rs2_e;
    logic [2:0] branch_type_e;
    logic [1:0] jump_e;
    logic memread_m;

    logic [1:0] pc_sel;
    logic pc_en, if_id_en, if_id_flush, id_ex_flush;
    logic [3:0] alu_ctrl;
    logic [1:0] alu_src_a_sel, alu_src_b_sel;
    logic [1:0] fwd_a, fwd_b, fwd_store;
    logic regwrite_d, memread_d, memwrite_d;
    logic [2:0] load_type_d;
    logic [1:0] store_type_d, wb_sel_d;
    logic [2:0] branch_type_d;
    logic [1:0] jump_d;
    logic [2:0] imm_type_d;
    logic uses_rs1_d, uses_rs2_d;

    logic [31:0] imem_addr, imem_rdata;
    logic imem_re;
    logic [31:0] dmem_addr, dmem_wdata, dmem_rdata;
    logic [3:0] dmem_wstrb;
    logic dmem_re, dmem_we;
    logic [31:0] mmio_addr, mmio_wdata, mmio_rdata;
    logic mmio_re, mmio_we, mmio_ready;

    cpu_control u_control (.*);

    cpu_datapath #(
        .RESET_PC(RESET_PC), .SRAM_BASE(SRAM_BASE), .SRAM_SIZE(SRAM_SIZE),
        .CNN_MMIO_BASE(CNN_MMIO_BASE), .CNN_MMIO_SIZE(CNN_MMIO_SIZE)
    ) u_cpu_datapath (.*);

    datapath_memory_subsystem #(
        .EXTERNAL_CNN_MMIO(EXTERNAL_CNN_MMIO),
        .NATIVE_CNN_MEMORY(NATIVE_CNN_MEMORY),
        .IMEM_BASE(IMEM_BASE), .IMEM_SIZE(IMEM_SIZE),
        .IMEM_INIT_FILE(IMEM_INIT_FILE),
        .SRAM_BASE(SRAM_BASE), .SRAM_SIZE(SRAM_SIZE),
        .CNN_MMIO_BASE(CNN_MMIO_BASE)
    ) u_memory (.*);
endmodule
