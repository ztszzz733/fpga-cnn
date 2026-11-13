module cpu_datapath #(
    parameter logic [31:0] RESET_PC      = 32'h0000_0000,
    parameter logic [31:0] SRAM_BASE     = 32'h0000_0000,
    parameter logic [31:0] SRAM_SIZE     = 32'h0004_0000,
    parameter logic [31:0] CNN_MMIO_BASE = 32'h4000_0000,
    parameter logic [31:0] CNN_MMIO_SIZE = 32'h0000_1000
) (
    input  logic clk,
    input  logic rst_n,

    output logic [31:0] instr_d,
    output logic [4:0] rs1_d, rs2_d,
    output logic [4:0] rd_e, rd_m, rd_w,
    output logic regwrite_m, regwrite_w, memread_e,
    output logic cmp_eq_e, cmp_lt_e, cmp_ltu_e, mul_busy,
    output logic valid_d, valid_e, valid_m, valid_w,
    output logic [4:0] rs1_e, rs2_e,
    output logic uses_rs1_e, uses_rs2_e,
    output logic [2:0] branch_type_e,
    output logic [1:0] jump_e,
    output logic memread_m,

    input logic [1:0] pc_sel,
    input logic pc_en, if_id_en, if_id_flush, id_ex_flush,
    input logic [3:0] alu_ctrl,
    input logic [1:0] alu_src_a_sel, alu_src_b_sel,
    input logic [1:0] fwd_a, fwd_b, fwd_store,
    input logic regwrite_d, memread_d, memwrite_d,
    input logic [2:0] load_type_d,
    input logic [1:0] store_type_d, wb_sel_d,
    input logic [2:0] branch_type_d,
    input logic [1:0] jump_d,
    input logic [2:0] imm_type_d,
    input logic uses_rs1_d, uses_rs2_d,

    output logic [31:0] imem_addr,
    output logic imem_re,
    input  logic [31:0] imem_rdata,
    output logic [31:0] dmem_addr, dmem_wdata,
    output logic [3:0] dmem_wstrb,
    output logic dmem_re, dmem_we,
    input  logic [31:0] dmem_rdata,
    output logic [31:0] mmio_addr, mmio_wdata,
    output logic mmio_re, mmio_we,
    input  logic [31:0] mmio_rdata,
    input  logic mmio_ready
);
    import cpu_control_pkg::*;

    logic [31:0] pc_q, next_pc, pc4_seq, branch_target, jalr_target;
    logic fetch_valid;
    logic [31:0] fetch_instr, fetch_pc, fetch_pc4, pc_d, pc4_d;
    logic [4:0] rd_d;
    logic [31:0] rd1_d, rd2_d, imm_d;

    logic [31:0] pc_e, pc4_e, rd1_e, rd2_e, imm_e;
    logic [3:0] alu_ctrl_e;
    logic [1:0] alu_src_a_sel_e, alu_src_b_sel_e;
    logic regwrite_e, memwrite_e;
    logic [2:0] load_type_e;
    logic [1:0] store_type_e, wb_sel_e;
    logic [31:0] src1_fwd_e, src2_fwd_e, store_data_fwd_e;
    logic [31:0] alu_a_e, alu_b_e, alu_result_e;
    /* Full reusable module interfaces expose diagnostic outputs that this
       top-level does not need for architectural decisions. */
    /* verilator lint_off UNUSEDSIGNAL */
    logic alu_zero_e;

    logic [31:0] write_data_m, pc4_m;
    logic memwrite_m;
    logic [2:0] load_type_m;
    logic [1:0] store_type_m, wb_sel_m;
    logic [31:0] alu_result_m, mem_forward_m;
    logic [31:0] read_data_m;

    logic [31:0] read_data_w, alu_result_w, pc4_w, wb_data_w;
    logic [1:0] wb_sel_w;
    logic rf_we;

    logic sram_hit_e, mmio_window_hit_e, mmio_reg_hit_e, unmapped_e;
    logic sram_hit_m, mmio_window_hit_m, mmio_reg_hit_m, unmapped_m;
    logic [31:0] ignored_load_e, store_wdata_e;
    logic load_aligned_e, load_type_valid_e;
    logic store_aligned_e, store_type_valid_e;
    logic [3:0] store_wstrb_e;
    logic [31:0] sram_load_data_m, ignored_store_wdata_m;
    logic load_aligned_m, load_type_valid_m;
    logic ignored_store_aligned_m, ignored_store_type_valid_m;
    logic [3:0] ignored_store_wstrb_m;
    logic legal_sram_load_m, legal_mmio_load_m;
    /* verilator lint_on UNUSEDSIGNAL */

    assign pc4_seq = pc_q + 32'd4;
    assign branch_target = pc_e + imm_e;
    assign jalr_target = (src1_fwd_e + imm_e) & 32'hffff_fffe;
    always_comb begin
        case (pc_sel)
            PC_NEXT:   next_pc = pc4_seq;
            PC_TARGET: next_pc = branch_target;
            PC_JALR:   next_pc = jalr_target;
            default:   next_pc = 32'b0;
        endcase
    end

    pc #(.RESET_PC(RESET_PC)) u_pc (
        .clk(clk), .rst_n(rst_n), .pc_en(pc_en), .next_pc(next_pc), .pc_q(pc_q)
    );
    fetch_adapter u_fetch (
        .clk(clk), .rst_n(rst_n), .request_pc(pc_q), .pc_en(pc_en),
        .if_id_en(if_id_en), .flush(if_id_flush), .imem_addr(imem_addr),
        .imem_re(imem_re), .imem_rdata(imem_rdata), .fetch_valid(fetch_valid),
        .fetch_instr(fetch_instr), .fetch_pc(fetch_pc), .fetch_pc4(fetch_pc4)
    );
    if_id_reg u_if_id (
        .clk(clk), .rst_n(rst_n), .en(if_id_en), .flush(if_id_flush),
        .valid_i(fetch_valid), .instr_i(fetch_instr), .pc_i(fetch_pc),
        .pc4_i(fetch_pc4), .valid_o(valid_d), .instr_o(instr_d),
        .pc_o(pc_d), .pc4_o(pc4_d)
    );

    assign rs1_d = instr_d[19:15];
    assign rs2_d = instr_d[24:20];
    assign rd_d = instr_d[11:7];
    assign rf_we = valid_w && regwrite_w && (rd_w != 5'b0);
    regfile u_regfile (
        .clk(clk), .rst_n(rst_n), .rs1(rs1_d), .rs2(rs2_d),
        .rd1(rd1_d), .rd2(rd2_d), .we(rf_we), .waddr(rd_w), .wdata(wb_data_w)
    );
    imm_gen u_imm_gen (.instr(instr_d), .imm_type(imm_type_d), .imm_ext(imm_d));
    id_ex_reg u_id_ex (
        .clk(clk), .rst_n(rst_n), .flush(id_ex_flush), .valid_d(valid_d),
        .pc_d(pc_d), .pc4_d(pc4_d), .rd1_d(rd1_d), .rd2_d(rd2_d), .imm_d(imm_d),
        .rs1_d(rs1_d), .rs2_d(rs2_d), .rd_d(rd_d), .uses_rs1_d(uses_rs1_d),
        .uses_rs2_d(uses_rs2_d), .alu_ctrl_d(alu_ctrl),
        .alu_src_a_sel_d(alu_src_a_sel), .alu_src_b_sel_d(alu_src_b_sel),
        .regwrite_d(regwrite_d), .memread_d(memread_d), .memwrite_d(memwrite_d),
        .load_type_d(load_type_d), .store_type_d(store_type_d), .wb_sel_d(wb_sel_d),
        .branch_type_d(branch_type_d), .jump_d(jump_d), .valid_e(valid_e),
        .pc_e(pc_e), .pc4_e(pc4_e), .rd1_e(rd1_e), .rd2_e(rd2_e), .imm_e(imm_e),
        .rs1_e(rs1_e), .rs2_e(rs2_e), .rd_e(rd_e), .uses_rs1_e(uses_rs1_e),
        .uses_rs2_e(uses_rs2_e), .alu_ctrl_e(alu_ctrl_e),
        .alu_src_a_sel_e(alu_src_a_sel_e), .alu_src_b_sel_e(alu_src_b_sel_e),
        .regwrite_e(regwrite_e), .memread_e(memread_e), .memwrite_e(memwrite_e),
        .load_type_e(load_type_e), .store_type_e(store_type_e), .wb_sel_e(wb_sel_e),
        .branch_type_e(branch_type_e), .jump_e(jump_e)
    );

    always_comb begin
        case (wb_sel_m)
            WB_ALU:  mem_forward_m = alu_result_m;
            WB_PC4:  mem_forward_m = pc4_m;
            default: mem_forward_m = 32'b0;
        endcase
        case (fwd_a)
            FWD_REG: src1_fwd_e = rd1_e;
            FWD_WB:  src1_fwd_e = wb_data_w;
            FWD_MEM: src1_fwd_e = mem_forward_m;
            default: src1_fwd_e = 32'b0;
        endcase
        case (fwd_b)
            FWD_REG: src2_fwd_e = rd2_e;
            FWD_WB:  src2_fwd_e = wb_data_w;
            FWD_MEM: src2_fwd_e = mem_forward_m;
            default: src2_fwd_e = 32'b0;
        endcase
        case (fwd_store)
            FWD_REG: store_data_fwd_e = rd2_e;
            FWD_WB:  store_data_fwd_e = wb_data_w;
            FWD_MEM: store_data_fwd_e = mem_forward_m;
            default: store_data_fwd_e = 32'b0;
        endcase
        case (alu_src_a_sel_e)
            A_REG:  alu_a_e = src1_fwd_e;
            A_PC:   alu_a_e = pc_e;
            A_ZERO: alu_a_e = 32'b0;
            default: alu_a_e = 32'b0;
        endcase
        case (alu_src_b_sel_e)
            B_REG: alu_b_e = src2_fwd_e;
            B_IMM: alu_b_e = imm_e;
            default: alu_b_e = 32'b0;
        endcase
    end
    alu u_alu (.a(alu_a_e), .b(alu_b_e), .alu_ctrl(alu_ctrl_e),
               .result(alu_result_e), .zero(alu_zero_e));
    assign cmp_eq_e = (src1_fwd_e == src2_fwd_e);
    assign cmp_lt_e = ($signed(src1_fwd_e) < $signed(src2_fwd_e));
    assign cmp_ltu_e = (src1_fwd_e < src2_fwd_e);
    assign mul_busy = 1'b0;

    address_decoder #(.SRAM_BASE(SRAM_BASE), .SRAM_SIZE(SRAM_SIZE),
        .CNN_MMIO_BASE(CNN_MMIO_BASE), .CNN_MMIO_SIZE(CNN_MMIO_SIZE)) u_addr_e (
        .addr(alu_result_e), .sram_hit(sram_hit_e),
        .mmio_window_hit(mmio_window_hit_e), .mmio_reg_hit(mmio_reg_hit_e),
        .unmapped(unmapped_e)
    );
    lsu u_lsu_e (
        .addr(alu_result_e), .store_data(store_data_fwd_e), .read_word(32'b0),
        .load_type(load_type_e), .store_type(store_type_e), .load_data(ignored_load_e),
        .load_aligned(load_aligned_e), .load_type_valid(load_type_valid_e),
        .store_wdata(store_wdata_e), .store_wstrb(store_wstrb_e),
        .store_aligned(store_aligned_e), .store_type_valid(store_type_valid_e)
    );
    assign dmem_addr = alu_result_e;
    assign dmem_wdata = store_wdata_e;
    assign dmem_re = rst_n && valid_e && memread_e && sram_hit_e &&
                     load_type_valid_e && load_aligned_e;
    assign dmem_we = rst_n && valid_e && memwrite_e && sram_hit_e &&
                     store_type_valid_e && store_aligned_e;
    assign dmem_wstrb = dmem_we ? store_wstrb_e : 4'b0;

    ex_mem_reg u_ex_mem (
        .clk(clk), .rst_n(rst_n), .valid_e(valid_e), .alu_result_e(alu_result_e),
        .write_data_e(store_data_fwd_e), .pc4_e(pc4_e), .rd_e(rd_e),
        .regwrite_e(regwrite_e), .memread_e(memread_e), .memwrite_e(memwrite_e),
        .load_type_e(load_type_e), .store_type_e(store_type_e), .wb_sel_e(wb_sel_e),
        .valid_m(valid_m), .alu_result_m(alu_result_m), .write_data_m(write_data_m),
        .pc4_m(pc4_m), .rd_m(rd_m), .regwrite_m(regwrite_m), .memread_m(memread_m),
        .memwrite_m(memwrite_m), .load_type_m(load_type_m),
        .store_type_m(store_type_m), .wb_sel_m(wb_sel_m)
    );

    address_decoder #(.SRAM_BASE(SRAM_BASE), .SRAM_SIZE(SRAM_SIZE),
        .CNN_MMIO_BASE(CNN_MMIO_BASE), .CNN_MMIO_SIZE(CNN_MMIO_SIZE)) u_addr_m (
        .addr(alu_result_m), .sram_hit(sram_hit_m),
        .mmio_window_hit(mmio_window_hit_m), .mmio_reg_hit(mmio_reg_hit_m),
        .unmapped(unmapped_m)
    );
    lsu u_lsu_m (
        .addr(alu_result_m), .store_data(write_data_m), .read_word(dmem_rdata),
        .load_type(load_type_m), .store_type(store_type_m), .load_data(sram_load_data_m),
        .load_aligned(load_aligned_m), .load_type_valid(load_type_valid_m),
        .store_wdata(ignored_store_wdata_m), .store_wstrb(ignored_store_wstrb_m),
        .store_aligned(ignored_store_aligned_m),
        .store_type_valid(ignored_store_type_valid_m)
    );
    assign legal_sram_load_m = valid_m && memread_m && sram_hit_m &&
                               load_type_valid_m && load_aligned_m;
    assign legal_mmio_load_m = valid_m && memread_m && mmio_reg_hit_m &&
                               (load_type_m == LOAD_LW) && (alu_result_m[1:0] == 2'b00);
    always_comb begin
        read_data_m = 32'b0;
        if (legal_sram_load_m) read_data_m = sram_load_data_m;
        else if (legal_mmio_load_m && mmio_ready) read_data_m = mmio_rdata;
    end
    assign mmio_addr = alu_result_m;
    assign mmio_wdata = write_data_m;
    assign mmio_re = rst_n && legal_mmio_load_m;
    assign mmio_we = rst_n && valid_m && memwrite_m && mmio_reg_hit_m &&
                     (store_type_m == STORE_SW) && (alu_result_m[1:0] == 2'b00);

    mem_wb_reg u_mem_wb (
        .clk(clk), .rst_n(rst_n), .valid_m(valid_m), .read_data_m(read_data_m),
        .alu_result_m(alu_result_m), .pc4_m(pc4_m), .rd_m(rd_m),
        .regwrite_m(regwrite_m), .wb_sel_m(wb_sel_m), .valid_w(valid_w),
        .read_data_w(read_data_w), .alu_result_w(alu_result_w), .pc4_w(pc4_w),
        .rd_w(rd_w), .regwrite_w(regwrite_w), .wb_sel_w(wb_sel_w)
    );
    always_comb begin
        case (wb_sel_w)
            WB_ALU:  wb_data_w = alu_result_w;
            WB_LOAD: wb_data_w = read_data_w;
            WB_PC4:  wb_data_w = pc4_w;
            default: wb_data_w = 32'b0;
        endcase
    end

`ifndef SYNTHESIS
    always_ff @(posedge clk) begin
        if (rst_n) begin
            assert (!(dmem_re && dmem_we));
            assert (!(mmio_re && mmio_we));
            assert (!dmem_we || (dmem_wstrb != 4'b0));
            assert (!mmio_re || mmio_ready)
                else $warning("legal MMIO read violated zero-wait ready contract");
            assert (!mmio_we || mmio_ready)
                else $warning("legal MMIO write violated zero-wait ready contract");
        end else begin
            assert (!dmem_we && !mmio_we);
        end
    end
`endif
endmodule
