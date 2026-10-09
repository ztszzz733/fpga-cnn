// Isolated three-wire autoload CPU wrapper. Original Control/Datapath unchanged.
module cpu_core_autoload #(
    parameter logic [31:0] RESET_PC = 32'h0000_0000,
    parameter logic [31:0] SRAM_BASE = 32'h0000_0000,
    parameter logic [31:0] SRAM_SIZE = 32'h0004_0000,
    parameter logic [31:0] CNN_MMIO_BASE = 32'h4000_0000,
    parameter logic [31:0] CNN_MMIO_SIZE = 32'h0000_1000,
    parameter logic [31:0] LOAD_CTRL_ADDR = 32'h0000_0040
) (
    input logic clk, rst_n,
    output logic load_req,
    input logic load_complete, load_error,
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



    // Two local words overlay a reserved part of the CPU data address space.
    // The unchanged Datapath issues E-stage requests; these registers return
    // data after that edge, exactly like the one-cycle SRAM A port.
    logic [31:0] core_dmem_addr, core_dmem_wdata, core_dmem_rdata;
    logic [3:0] core_dmem_wstrb;
    logic core_dmem_re, core_dmem_we;
    logic local_read_q;
    logic [31:0] local_rdata_q;
    wire local_control = core_dmem_addr[31:2] == LOAD_CTRL_ADDR[31:2];
    wire local_status = core_dmem_addr[31:2] == ((LOAD_CTRL_ADDR + 32'd4) >> 2);
    wire local_hit = local_control || local_status;
    assign dmem_addr = core_dmem_addr;
    assign dmem_wdata = core_dmem_wdata;
    assign dmem_re = core_dmem_re && !local_hit;
    assign dmem_we = core_dmem_we && !local_hit;
    assign dmem_wstrb = dmem_we ? core_dmem_wstrb : 4'b0;
    assign core_dmem_rdata = local_read_q ? local_rdata_q : dmem_rdata;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            load_req <= 0;
            local_read_q <= 0;
            local_rdata_q <= 0;
        end else begin
            if (core_dmem_re) begin
                local_read_q <= local_hit;
                local_rdata_q <= local_control ? {31'b0,load_req} :
                                                {30'b0,load_error,load_complete};
            end
            // Only full-word control stores have effects; status is read-only.
            // Do not allow software to cancel an outstanding transaction.
            if (core_dmem_we && local_control && core_dmem_wstrb == 4'hf) begin
                if (core_dmem_wdata[0]) begin
                    if (!load_req && !load_complete) load_req <= 1;
                end else if (!load_req || load_complete) load_req <= 0;
            end
        end
    end
`ifndef SYNTHESIS
    initial begin
        assert (LOAD_CTRL_ADDR[2:0] == 0 && LOAD_CTRL_ADDR >= SRAM_BASE &&
                ({1'b0,LOAD_CTRL_ADDR}+8 <= {1'b0,SRAM_BASE}+SRAM_SIZE))
            else $fatal(1,"local load registers must be inside SRAM address window");
    end
`endif

    cpu_control u_control (.*);
    cpu_datapath #(
        .RESET_PC(RESET_PC), .SRAM_BASE(SRAM_BASE), .SRAM_SIZE(SRAM_SIZE),
        .CNN_MMIO_BASE(CNN_MMIO_BASE), .CNN_MMIO_SIZE(CNN_MMIO_SIZE)
    ) u_datapath (
        .dmem_addr(core_dmem_addr), .dmem_wdata(core_dmem_wdata),
        .dmem_wstrb(core_dmem_wstrb), .dmem_re(core_dmem_re), .dmem_we(core_dmem_we),
        .dmem_rdata(core_dmem_rdata), .*
    );
endmodule
