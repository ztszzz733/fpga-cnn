module tb_base_modules;
    import cpu_control_pkg::*;

    logic clk, rst_n;
    always #5 clk = ~clk;

    logic [31:0] a, b, alu_y;
    logic [3:0] alu_ctrl;
    logic zero;
    logic [31:0] instr, imm;
    logic [2:0] imm_type;
    logic [11:0] imm12;
    logic [12:0] imm13;
    logic [20:0] imm21;
    logic pc_en;
    logic [31:0] next_pc, pc_q;
    logic [4:0] rs1, rs2, waddr;
    logic [31:0] rd1, rd2, wdata;
    logic we;

    logic if_en, if_flush, if_valid_i, if_valid_o;
    logic [31:0] if_instr_i, if_pc_i, if_pc4_i, if_instr_o, if_pc_o, if_pc4_o;

    logic id_flush, id_valid_d, id_valid_e;
    logic [31:0] id_pc_d, id_pc4_d, id_rd1_d, id_rd2_d, id_imm_d;
    logic [31:0] id_pc_e, id_pc4_e, id_rd1_e, id_rd2_e, id_imm_e;
    logic [4:0] id_rs1_d, id_rs2_d, id_rd_d, id_rs1_e, id_rs2_e, id_rd_e;
    logic id_uses_rs1_d, id_uses_rs2_d, id_uses_rs1_e, id_uses_rs2_e;
    logic [3:0] id_alu_ctrl_d, id_alu_ctrl_e;
    logic [1:0] id_alu_a_d, id_alu_b_d, id_alu_a_e, id_alu_b_e;
    logic id_regwrite_d, id_memread_d, id_memwrite_d;
    logic id_regwrite_e, id_memread_e, id_memwrite_e;
    logic [2:0] id_load_d, id_load_e, id_branch_d, id_branch_e;
    logic [1:0] id_store_d, id_store_e, id_wb_d, id_wb_e, id_jump_d, id_jump_e;

    logic ex_valid_e, ex_valid_m;
    logic [31:0] ex_alu_e, ex_write_e, ex_pc4_e, ex_alu_m, ex_write_m, ex_pc4_m;
    logic [4:0] ex_rd_e, ex_rd_m;
    logic ex_regwrite_e, ex_memread_e, ex_memwrite_e;
    logic ex_regwrite_m, ex_memread_m, ex_memwrite_m;
    logic [2:0] ex_load_e, ex_load_m;
    logic [1:0] ex_store_e, ex_store_m, ex_wb_e, ex_wb_m;

    logic mw_valid_m, mw_valid_w;
    logic [31:0] mw_read_m, mw_alu_m, mw_pc4_m, mw_read_w, mw_alu_w, mw_pc4_w;
    logic [4:0] mw_rd_m, mw_rd_w;
    logic mw_regwrite_m, mw_regwrite_w;
    logic [1:0] mw_wb_m, mw_wb_w;

    alu u_alu(.a, .b, .alu_ctrl, .result(alu_y), .zero);
    imm_gen u_imm(.instr, .imm_type, .imm_ext(imm));
    pc u_pc(.clk, .rst_n, .pc_en, .next_pc, .pc_q);
    regfile u_rf(.clk, .rst_n, .rs1, .rs2, .rd1, .rd2, .we, .waddr, .wdata);
    if_id_reg u_ifid(
        .clk, .rst_n, .en(if_en), .flush(if_flush), .valid_i(if_valid_i),
        .instr_i(if_instr_i), .pc_i(if_pc_i), .pc4_i(if_pc4_i),
        .valid_o(if_valid_o), .instr_o(if_instr_o), .pc_o(if_pc_o), .pc4_o(if_pc4_o));
    id_ex_reg u_idex(
        .clk, .rst_n, .flush(id_flush), .valid_d(id_valid_d),
        .pc_d(id_pc_d), .pc4_d(id_pc4_d), .rd1_d(id_rd1_d), .rd2_d(id_rd2_d),
        .imm_d(id_imm_d), .rs1_d(id_rs1_d), .rs2_d(id_rs2_d), .rd_d(id_rd_d),
        .uses_rs1_d(id_uses_rs1_d), .uses_rs2_d(id_uses_rs2_d),
        .alu_ctrl_d(id_alu_ctrl_d), .alu_src_a_sel_d(id_alu_a_d),
        .alu_src_b_sel_d(id_alu_b_d), .regwrite_d(id_regwrite_d),
        .memread_d(id_memread_d), .memwrite_d(id_memwrite_d),
        .load_type_d(id_load_d), .store_type_d(id_store_d), .wb_sel_d(id_wb_d),
        .branch_type_d(id_branch_d), .jump_d(id_jump_d), .valid_e(id_valid_e),
        .pc_e(id_pc_e), .pc4_e(id_pc4_e), .rd1_e(id_rd1_e), .rd2_e(id_rd2_e),
        .imm_e(id_imm_e), .rs1_e(id_rs1_e), .rs2_e(id_rs2_e), .rd_e(id_rd_e),
        .uses_rs1_e(id_uses_rs1_e), .uses_rs2_e(id_uses_rs2_e),
        .alu_ctrl_e(id_alu_ctrl_e), .alu_src_a_sel_e(id_alu_a_e),
        .alu_src_b_sel_e(id_alu_b_e), .regwrite_e(id_regwrite_e),
        .memread_e(id_memread_e), .memwrite_e(id_memwrite_e),
        .load_type_e(id_load_e), .store_type_e(id_store_e), .wb_sel_e(id_wb_e),
        .branch_type_e(id_branch_e), .jump_e(id_jump_e));
    ex_mem_reg u_exmem(
        .clk, .rst_n, .valid_e(ex_valid_e), .alu_result_e(ex_alu_e),
        .write_data_e(ex_write_e), .pc4_e(ex_pc4_e), .rd_e(ex_rd_e),
        .regwrite_e(ex_regwrite_e), .memread_e(ex_memread_e), .memwrite_e(ex_memwrite_e),
        .load_type_e(ex_load_e), .store_type_e(ex_store_e), .wb_sel_e(ex_wb_e),
        .valid_m(ex_valid_m), .alu_result_m(ex_alu_m), .write_data_m(ex_write_m),
        .pc4_m(ex_pc4_m), .rd_m(ex_rd_m), .regwrite_m(ex_regwrite_m),
        .memread_m(ex_memread_m), .memwrite_m(ex_memwrite_m),
        .load_type_m(ex_load_m), .store_type_m(ex_store_m), .wb_sel_m(ex_wb_m));
    mem_wb_reg u_memwb(
        .clk, .rst_n, .valid_m(mw_valid_m), .read_data_m(mw_read_m),
        .alu_result_m(mw_alu_m), .pc4_m(mw_pc4_m), .rd_m(mw_rd_m),
        .regwrite_m(mw_regwrite_m), .wb_sel_m(mw_wb_m), .valid_w(mw_valid_w),
        .read_data_w(mw_read_w), .alu_result_w(mw_alu_w), .pc4_w(mw_pc4_w),
        .rd_w(mw_rd_w), .regwrite_w(mw_regwrite_w), .wb_sel_w(mw_wb_w));

    task automatic check(input logic cond, input string msg);
        if (!cond) begin $error("FAIL: %s", msg); $fatal(1); end
    endtask

    task automatic check_alu(input logic [31:0] lhs, rhs,
                             input logic [3:0] operation,
                             input logic [31:0] expected, input string msg);
        a=lhs; b=rhs; alu_ctrl=operation; #1;
        check(alu_y===expected && zero===(expected==32'b0), msg);
    endtask

    task automatic set_id(input logic p);
        id_valid_d=1; id_pc_d=p?32'h80000000:32'h100; id_pc4_d=p?32'h80000004:32'h104;
        id_rd1_d=p?32'ha5a55a5a:32'h11112222; id_rd2_d=p?32'h5a5aa5a5:32'h33334444;
        id_imm_d=p?32'hffffff80:32'h7c; id_rs1_d=p?31:1; id_rs2_d=p?30:2; id_rd_d=p?29:3;
        id_uses_rs1_d=1; id_uses_rs2_d=p; id_alu_ctrl_d=p?ALU_SRA:ALU_ADD;
        id_alu_a_d=p?ALUA_PC:ALUA_RS1; id_alu_b_d=p?ALUB_IMM:ALUB_RS2;
        id_regwrite_d=1; id_memread_d=p; id_memwrite_d=!p; id_load_d=p?LOAD_LHU:LOAD_LW;
        id_store_d=p?STORE_SH:STORE_SW; id_wb_d=p?WB_LOAD:WB_ALU;
        id_branch_d=p?BR_BGEU:BR_BEQ; id_jump_d=p?JUMP_JALR:JUMP_NONE;
    endtask
    task automatic check_id(input string msg);
        check(id_valid_e===id_valid_d && id_pc_e===id_pc_d && id_pc4_e===id_pc4_d &&
          id_rd1_e===id_rd1_d && id_rd2_e===id_rd2_d && id_imm_e===id_imm_d &&
          id_rs1_e===id_rs1_d && id_rs2_e===id_rs2_d && id_rd_e===id_rd_d &&
          id_uses_rs1_e===id_uses_rs1_d && id_uses_rs2_e===id_uses_rs2_d &&
          id_alu_ctrl_e===id_alu_ctrl_d && id_alu_a_e===id_alu_a_d && id_alu_b_e===id_alu_b_d &&
          id_regwrite_e===id_regwrite_d && id_memread_e===id_memread_d && id_memwrite_e===id_memwrite_d &&
          id_load_e===id_load_d && id_store_e===id_store_d && id_wb_e===id_wb_d &&
          id_branch_e===id_branch_d && id_jump_e===id_jump_d, msg);
    endtask
    task automatic check_id_zero(input string msg);
        check(!id_valid_e && id_pc_e===0 && id_pc4_e===0 && id_rd1_e===0 && id_rd2_e===0 &&
          id_imm_e===0 && id_rs1_e===0 && id_rs2_e===0 && id_rd_e===0 && !id_uses_rs1_e &&
          !id_uses_rs2_e && id_alu_ctrl_e===0 && id_alu_a_e===0 && id_alu_b_e===0 &&
          !id_regwrite_e && !id_memread_e && !id_memwrite_e && id_load_e===0 && id_store_e===0 &&
          id_wb_e===0 && id_branch_e===0 && id_jump_e===0, msg);
    endtask

    task automatic set_ex(input logic p);
        ex_valid_e=1; ex_alu_e=p?32'hffff0001:32'h1000; ex_write_e=p?32'h12345678:32'h89abcdef;
        ex_pc4_e=p?32'h204:32'h104; ex_rd_e=p?17:9; ex_regwrite_e=1;
        ex_memread_e=p; ex_memwrite_e=!p; ex_load_e=p?LOAD_LBU:LOAD_LH;
        ex_store_e=p?STORE_SB:STORE_SH; ex_wb_e=p?WB_PC4:WB_ALU;
    endtask
    task automatic check_ex(input string msg);
        check(ex_valid_m===ex_valid_e && ex_alu_m===ex_alu_e && ex_write_m===ex_write_e &&
          ex_pc4_m===ex_pc4_e && ex_rd_m===ex_rd_e && ex_regwrite_m===ex_regwrite_e &&
          ex_memread_m===ex_memread_e && ex_memwrite_m===ex_memwrite_e && ex_load_m===ex_load_e &&
          ex_store_m===ex_store_e && ex_wb_m===ex_wb_e, msg);
    endtask
    task automatic check_ex_zero(input string msg);
        check(!ex_valid_m && ex_alu_m===0 && ex_write_m===0 && ex_pc4_m===0 && ex_rd_m===0 &&
          !ex_regwrite_m && !ex_memread_m && !ex_memwrite_m && ex_load_m===0 &&
          ex_store_m===0 && ex_wb_m===0, msg);
    endtask

    task automatic set_mw(input logic p);
        mw_valid_m=1; mw_read_m=p?32'h80000000:32'h01020304;
        mw_alu_m=p?32'h7fffffff:32'haabbccdd; mw_pc4_m=p?32'h304:32'h204;
        mw_rd_m=p?23:11; mw_regwrite_m=p; mw_wb_m=p?WB_LOAD:WB_PC4;
    endtask
    task automatic check_mw(input string msg);
        check(mw_valid_w===mw_valid_m && mw_read_w===mw_read_m && mw_alu_w===mw_alu_m &&
          mw_pc4_w===mw_pc4_m && mw_rd_w===mw_rd_m && mw_regwrite_w===mw_regwrite_m &&
          mw_wb_w===mw_wb_m, msg);
    endtask
    task automatic check_mw_zero(input string msg);
        check(!mw_valid_w && mw_read_w===0 && mw_alu_w===0 && mw_pc4_w===0 && mw_rd_w===0 &&
          !mw_regwrite_w && mw_wb_w===0, msg);
    endtask

    initial begin
        clk=0; rst_n=0; a=0; b=0; alu_ctrl=ALU_ADD;
        instr=0; imm_type=IMM_NONE; imm12=0; imm13=0; imm21=0;
        pc_en=0; next_pc=0; rs1=0; rs2=0; we=0; waddr=0; wdata=0;
        if_en=0; if_flush=0; if_valid_i=0; if_instr_i=0; if_pc_i=0; if_pc4_i=0;
        id_flush=0; set_id(0); set_ex(0); set_mw(0);

        repeat(2) @(posedge clk); #1;
        check(pc_q===0, "PC reset");
        check(rd1===0 && rd2===0, "regfile reset and dual read");
        check(!if_valid_o && if_instr_o===0 && if_pc_o===0 && if_pc4_o===0, "IF/ID reset");
        check_id_zero("ID/EX reset"); check_ex_zero("EX/MEM reset"); check_mw_zero("MEM/WB reset");
        rst_n=1;

        check_alu(0,0,ALU_ADD,0,"ALU ADD zero");
        check_alu(32'h7fffffff,1,ALU_ADD,32'h80000000,"ALU ADD maximum positive");
        check_alu(32'hffffffff,1,ALU_ADD,0,"ALU ADD all-ones wrap");
        check_alu(0,1,ALU_SUB,32'hffffffff,"ALU SUB underflow");
        check_alu(32'h80000000,1,ALU_SUB,32'h7fffffff,"ALU SUB minimum negative");
        check_alu(32'ha5a55a5a,32'h0ff0f00f,ALU_AND,32'h05a0500a,"ALU AND");
        check_alu(32'ha5a55a5a,32'h0ff0f00f,ALU_OR,32'haff5fa5f,"ALU OR");
        check_alu(32'ha5a55a5a,32'hffffffff,ALU_XOR,32'h5a5aa5a5,"ALU XOR");
        check_alu(1,31,ALU_SLL,32'h80000000,"ALU SLL");
        check_alu(32'hffffffff,31,ALU_SRL,1,"ALU SRL");
        check_alu(32'h80000000,31,ALU_SRA,32'hffffffff,"ALU SRA negative");
        check_alu(32'h7fffffff,31,ALU_SRA,0,"ALU SRA positive");
        check_alu(32'h80000000,32'h7fffffff,ALU_SLT,1,"ALU SLT boundaries");
        check_alu(32'hffffffff,0,ALU_SLT,1,"ALU SLT all ones");
        check_alu(0,32'hffffffff,ALU_SLTU,1,"ALU SLTU");
        check_alu(32'hffffffff,0,ALU_SLTU,0,"ALU SLTU all ones");

        instr=0; instr[31:20]=12'h7ff; imm_type=IMM_I; #1; check(imm===32'h7ff,"IMM I positive");
        instr[31:20]=12'h800; #1; check(imm===32'hfffff800,"IMM I negative");
        imm12=12'h07c; instr=0; instr[31:25]=imm12[11:5]; instr[11:7]=imm12[4:0];
        imm_type=IMM_S; #1; check(imm===32'h7c,"IMM S positive");
        imm12=12'hf80; instr[31:25]=imm12[11:5]; instr[11:7]=imm12[4:0];
        #1; check(imm===32'hffffff80,"IMM S negative");
        imm13=13'h07e; instr=0; instr[31]=imm13[12]; instr[7]=imm13[11];
        instr[30:25]=imm13[10:5]; instr[11:8]=imm13[4:1]; imm_type=IMM_B;
        #1; check(imm13[0]===1'b0 && imm===32'h7e,"IMM B positive/aligned");
        imm13=13'h1000; instr[31]=imm13[12]; instr[7]=imm13[11];
        instr[30:25]=imm13[10:5]; instr[11:8]=imm13[4:1];
        #1; check(imm===32'hfffff000,"IMM B negative");
        instr=32'h7ffff000; imm_type=IMM_U; #1; check(imm===32'h7ffff000,"IMM U positive");
        instr=32'h80000000; #1; check(imm===32'h80000000,"IMM U high bit");
        imm21=21'h007fe; instr=0; instr[31]=imm21[20]; instr[19:12]=imm21[19:12];
        instr[20]=imm21[11]; instr[30:21]=imm21[10:1]; imm_type=IMM_J;
        #1; check(imm21[0]===1'b0 && imm===32'h7fe,"IMM J positive/aligned");
        imm21=21'h100000; instr[31]=imm21[20]; instr[19:12]=imm21[19:12];
        instr[20]=imm21[11]; instr[30:21]=imm21[10:1];
        #1; check(imm===32'hfff00000,"IMM J negative");
        imm_type=IMM_NONE; #1; check(imm===0,"IMM NONE");

        pc_en=1; next_pc=32'h100; @(posedge clk); #1; check(pc_q===32'h100,"PC enable");
        pc_en=0; next_pc=32'h200; @(posedge clk); #1; check(pc_q===32'h100,"PC hold");
        rst_n=0; pc_en=1; next_pc=32'hdeadbeef; @(posedge clk); #1; check(pc_q===0,"PC reset priority");
        rst_n=1; pc_en=0;

        rs1=5; rs2=6; waddr=5; wdata=32'h11115555; we=1; #1;
        check(rd1===32'h11115555 && rd2===0,"regfile port1 bypass");
        @(posedge clk); #1; waddr=6; wdata=32'h22226666; #1;
        check(rd1===32'h11115555 && rd2===32'h22226666,"regfile port2 bypass");
        @(posedge clk); #1; we=0;
        check(rd1===32'h11115555 && rd2===32'h22226666,"regfile dual read/writeback");
        waddr=5; wdata=32'hffffffff; @(posedge clk); #1;
        check(rd1===32'h11115555,"regfile disabled write hold");
        rs1=0; rs2=0; waddr=0; wdata=32'hdeadbeef; we=1; #1;
        check(rd1===0 && rd2===0,"regfile x0 bypass excluded");
        @(posedge clk); #1; we=0; check(rd1===0 && rd2===0,"regfile x0 remains zero");

        if_en=1; if_flush=0; if_valid_i=1; if_instr_i=32'h13; if_pc_i=32'h20; if_pc4_i=32'h24;
        @(posedge clk); #1;
        check(if_valid_o && if_instr_o===if_instr_i && if_pc_o===if_pc_i && if_pc4_o===if_pc4_i,
              "IF/ID advance");
        if_en=0; if_instr_i=32'hffffffff; if_pc_i=32'h40; if_pc4_i=32'h44; @(posedge clk); #1;
        check(if_valid_o && if_instr_o===32'h13 && if_pc_o===32'h20 && if_pc4_o===32'h24,"IF/ID hold");
        if_flush=1; @(posedge clk); #1;
        check(!if_valid_o && if_instr_o===0 && if_pc_o===0 && if_pc4_o===0,"IF/ID flush");
        if_en=1; if_flush=1; if_valid_i=1; if_instr_i=32'haaaa5555; @(posedge clk); #1;
        check(!if_valid_o && if_instr_o===0,"IF/ID flush over enable");
        rst_n=0; if_en=1; if_flush=1; @(posedge clk); #1;
        check(!if_valid_o && if_instr_o===0 && if_pc_o===0 && if_pc4_o===0,"IF/ID reset priority");
        rst_n=1; if_en=0; if_flush=0;

        id_flush=0; set_id(0); @(posedge clk); #1; check_id("ID/EX advance");
        set_id(1); @(posedge clk); #1; check_id("ID/EX consecutive advance");
        id_flush=1; @(posedge clk); #1; check_id_zero("ID/EX flush");
        rst_n=0; id_flush=1; set_id(1); @(posedge clk); #1; check_id_zero("ID/EX reset priority");
        rst_n=1; id_flush=0;

        set_ex(0); @(posedge clk); #1; check_ex("EX/MEM advance");
        set_ex(1); #1; check(ex_alu_m===32'h1000 && ex_rd_m===9,"EX/MEM waits for edge");
        @(posedge clk); #1; check_ex("EX/MEM edge update");
        set_ex(0); @(posedge clk); #1; check_ex("EX/MEM consecutive advance");
        rst_n=0; @(posedge clk); #1; check_ex_zero("EX/MEM reset"); rst_n=1;

        set_mw(0); @(posedge clk); #1; check_mw("MEM/WB advance");
        set_mw(1); #1; check(mw_read_w===32'h01020304 && mw_rd_w===11,"MEM/WB waits for edge");
        @(posedge clk); #1; check_mw("MEM/WB edge update");
        set_mw(0); @(posedge clk); #1; check_mw("MEM/WB consecutive advance");
        rst_n=0; @(posedge clk); #1; check_mw_zero("MEM/WB reset"); rst_n=1;

        $display("PASS: base datapath modules");
        $finish;
    end
endmodule
