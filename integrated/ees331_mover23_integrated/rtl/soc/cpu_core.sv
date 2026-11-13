// CPU execution core only. Memories and CNN are peer modules in the SoC.
module cpu_core #(
    parameter logic [31:0] RESET_PC = 32'h0000_0000,
    parameter logic [31:0] SRAM_BASE = 32'h0000_0000,
    parameter logic [31:0] SRAM_SIZE = 32'h0004_0000,
    parameter logic [31:0] CNN_MMIO_BASE = 32'h4000_0000,
    parameter logic [31:0] CNN_MMIO_SIZE = 32'h0000_1000
) (
    input logic clk, rst_n,
    output logic [31:0] imem_addr,
    output logic imem_re,
    input logic [31:0] imem_rdata,
    output logic [31:0] dmem_addr, dmem_wdata,
    output logic [3:0] dmem_wstrb,
    output logic dmem_re, dmem_we,
    input logic [31:0] dmem_rdata,
    output logic [31:0] mmio_addr, mmio_wdata,
    output logic mmio_re, mmio_we,
    input logic [31:0] mmio_rdata,
    input logic mmio_ready
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


    cpu_control u_control (.*);
    cpu_datapath #(
        .RESET_PC(RESET_PC), .SRAM_BASE(SRAM_BASE), .SRAM_SIZE(SRAM_SIZE),
        .CNN_MMIO_BASE(CNN_MMIO_BASE), .CNN_MMIO_SIZE(CNN_MMIO_SIZE)
    ) u_datapath (.*);
endmodule
