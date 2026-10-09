module tb_cpu_datapath;
    import cpu_control_pkg::*;
    logic clk, rst_n;
    int errors, cycles, program_words;
    logic illegal_seen;
    logic completed;

    logic [31:0] instr_d, imem_addr, imem_rdata;
    logic [4:0] rs1_d, rs2_d, rd_e, rd_m, rd_w, rs1_e, rs2_e;
    logic regwrite_m, regwrite_w, memread_e, cmp_eq_e, cmp_lt_e, cmp_ltu_e;
    logic mul_busy, valid_d, valid_e, valid_m, valid_w, uses_rs1_e, uses_rs2_e;
    logic [2:0] branch_type_e;
    logic [1:0] jump_e;
    logic memread_m;
    logic [1:0] pc_sel, alu_src_a_sel, alu_src_b_sel, fwd_a, fwd_b, fwd_store;
    logic pc_en, if_id_en, if_id_flush, id_ex_flush;
    logic [3:0] alu_ctrl;
    logic regwrite_d, memread_d, memwrite_d, uses_rs1_d, uses_rs2_d;
    logic [2:0] load_type_d, branch_type_d, imm_type_d;
    logic [1:0] store_type_d, wb_sel_d, jump_d;
    logic imem_re;
    logic [31:0] dmem_addr, dmem_wdata, dmem_rdata;
    logic [3:0] dmem_wstrb;
    logic dmem_re, dmem_we;
    logic [31:0] mmio_addr, mmio_wdata, mmio_rdata;
    logic mmio_re, mmio_we, mmio_ready;

    cpu_datapath dut (
        .clk(clk), .rst_n(rst_n), .instr_d(instr_d), .rs1_d(rs1_d), .rs2_d(rs2_d),
        .rd_e(rd_e), .rd_m(rd_m), .rd_w(rd_w), .regwrite_m(regwrite_m),
        .regwrite_w(regwrite_w), .memread_e(memread_e), .cmp_eq_e(cmp_eq_e),
        .cmp_lt_e(cmp_lt_e), .cmp_ltu_e(cmp_ltu_e), .mul_busy(mul_busy),
        .valid_d(valid_d), .valid_e(valid_e), .valid_m(valid_m), .valid_w(valid_w),
        .rs1_e(rs1_e), .rs2_e(rs2_e), .uses_rs1_e(uses_rs1_e),
        .uses_rs2_e(uses_rs2_e), .branch_type_e(branch_type_e), .jump_e(jump_e),
        .memread_m(memread_m), .pc_sel(pc_sel), .pc_en(pc_en), .if_id_en(if_id_en),
        .if_id_flush(if_id_flush), .id_ex_flush(id_ex_flush), .alu_ctrl(alu_ctrl),
        .alu_src_a_sel(alu_src_a_sel), .alu_src_b_sel(alu_src_b_sel),
        .fwd_a(fwd_a), .fwd_b(fwd_b), .fwd_store(fwd_store),
        .regwrite_d(regwrite_d), .memread_d(memread_d), .memwrite_d(memwrite_d),
        .load_type_d(load_type_d), .store_type_d(store_type_d), .wb_sel_d(wb_sel_d),
        .branch_type_d(branch_type_d), .jump_d(jump_d), .imm_type_d(imm_type_d),
        .uses_rs1_d(uses_rs1_d), .uses_rs2_d(uses_rs2_d), .imem_addr(imem_addr),
        .imem_re(imem_re), .imem_rdata(imem_rdata), .dmem_addr(dmem_addr),
        .dmem_wdata(dmem_wdata), .dmem_wstrb(dmem_wstrb), .dmem_re(dmem_re),
        .dmem_we(dmem_we), .dmem_rdata(dmem_rdata), .mmio_addr(mmio_addr),
        .mmio_wdata(mmio_wdata), .mmio_re(mmio_re), .mmio_we(mmio_we),
        .mmio_rdata(mmio_rdata), .mmio_ready(mmio_ready)
    );
    control_stub u_control (
        .clk(clk), .rst_n(rst_n), .instr_d(instr_d), .rs1_d(rs1_d), .rs2_d(rs2_d),
        .rd_e(rd_e), .rd_m(rd_m), .rd_w(rd_w), .regwrite_m(regwrite_m),
        .regwrite_w(regwrite_w), .memread_e(memread_e), .cmp_eq_e(cmp_eq_e),
        .cmp_lt_e(cmp_lt_e), .cmp_ltu_e(cmp_ltu_e), .mul_busy(mul_busy),
        .valid_d(valid_d), .valid_e(valid_e), .valid_m(valid_m), .valid_w(valid_w),
        .rs1_e(rs1_e), .rs2_e(rs2_e), .uses_rs1_e(uses_rs1_e),
        .uses_rs2_e(uses_rs2_e), .branch_type_e(branch_type_e), .jump_e(jump_e),
        .memread_m(memread_m), .pc_sel(pc_sel), .pc_en(pc_en), .if_id_en(if_id_en),
        .if_id_flush(if_id_flush), .id_ex_flush(id_ex_flush), .alu_ctrl(alu_ctrl),
        .alu_src_a_sel(alu_src_a_sel), .alu_src_b_sel(alu_src_b_sel),
        .fwd_a(fwd_a), .fwd_b(fwd_b), .fwd_store(fwd_store),
        .regwrite_d(regwrite_d), .memread_d(memread_d), .memwrite_d(memwrite_d),
        .load_type_d(load_type_d), .store_type_d(store_type_d), .wb_sel_d(wb_sel_d),
        .branch_type_d(branch_type_d), .jump_d(jump_d), .imm_type_d(imm_type_d),
        .uses_rs1_d(uses_rs1_d), .uses_rs2_d(uses_rs2_d)
    );
    imem_model u_imem (.clk(clk), .re(imem_re), .addr(imem_addr), .rdata(imem_rdata));
    dmem_model u_dmem (.clk(clk), .re(dmem_re), .we(dmem_we), .wstrb(dmem_wstrb),
        .addr(dmem_addr), .wdata(dmem_wdata), .rdata(dmem_rdata));
    cnn_mmio_stub u_mmio (.clk(clk), .rst_n(rst_n), .addr(mmio_addr),
        .wdata(mmio_wdata), .re(mmio_re), .we(mmio_we), .rdata(mmio_rdata),
        .ready(mmio_ready));

    initial clk=0;
    always #5 clk=~clk;

    function automatic logic [31:0] rtype(
        input logic [6:0] f7, input logic [2:0] f3,
        input logic [4:0] rs2,rs1,rd);
        rtype={f7,rs2,rs1,f3,rd,7'h33};
    endfunction
    function automatic logic [31:0] itype(
        input logic [11:0] imm, input logic [4:0] rs1,
        input logic [2:0] f3, input logic [4:0] rd, input logic [6:0] opc);
        itype={imm,rs1,f3,rd,opc};
    endfunction
    function automatic logic [31:0] stype(
        input logic [11:0] imm, input logic [4:0] rs2,rs1,
        input logic [2:0] f3);
        stype={imm[11:5],rs2,rs1,f3,imm[4:0],7'h23};
    endfunction
    function automatic logic [31:0] btype(
        /* verilator lint_off UNUSEDSIGNAL */ input logic [12:0] imm,
        /* verilator lint_on UNUSEDSIGNAL */ input logic [4:0] rs2,rs1,
        input logic [2:0] f3);
        btype={imm[12],imm[10:5],rs2,rs1,f3,imm[4:1],imm[11],7'h63};
    endfunction
    function automatic logic [31:0] utype(
        input logic [19:0] imm20,input logic [4:0] rd,input logic [6:0] opc);
        utype={imm20,rd,opc};
    endfunction
    function automatic logic [31:0] jtype(
        /* verilator lint_off UNUSEDSIGNAL */ input logic [20:0] imm,
        /* verilator lint_on UNUSEDSIGNAL */ input logic [4:0] rd);
        jtype={imm[20],imm[10:1],imm[11],imm[19:12],rd,7'h6f};
    endfunction
    task automatic put(input int index,input logic [31:0] insn);
        u_imem.mem[index*4+0]=insn[7:0]; u_imem.mem[index*4+1]=insn[15:8];
        u_imem.mem[index*4+2]=insn[23:16]; u_imem.mem[index*4+3]=insn[31:24];
    endtask
    task automatic emit(input logic [31:0] insn);
        put(program_words,insn); program_words++;
    endtask
    task automatic fail(input string name,input string detail);
        errors++; $error("FAIL: %s: %s",name,detail);
    endtask
    task automatic check_reg(input int r,input logic [31:0] exp,input string name);
        if (dut.u_regfile.regs[r]!==exp)
            fail(name,$sformatf("x%0d expected=%08x actual=%08x",r,exp,dut.u_regfile.regs[r]));
    endtask
    function automatic logic [31:0] memword(input int a);
        memword={u_dmem.mem[a+3],u_dmem.mem[a+2],u_dmem.mem[a+1],u_dmem.mem[a]};
    endfunction

    int load_stalls, redirects, dmem_reads, dmem_writes, mmio_reads, mmio_writes;
    logic saw_parallel, saw_invalid_bubble;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            cycles<=0; load_stalls<=0; redirects<=0; dmem_reads<=0; dmem_writes<=0;
            mmio_reads<=0; mmio_writes<=0; saw_parallel<=0; saw_invalid_bubble<=0;
            illegal_seen<=0;
        end else begin
            cycles<=cycles+1;
            if (!pc_en&&!if_id_en&&id_ex_flush) load_stalls<=load_stalls+1;
            if (if_id_flush&&id_ex_flush&&pc_en) redirects<=redirects+1;
            if (dmem_re) dmem_reads<=dmem_reads+1;
            if (dmem_we) dmem_writes<=dmem_writes+1;
            if (mmio_re) mmio_reads<=mmio_reads+1;
            if (mmio_we) mmio_writes<=mmio_writes+1;
            if ((mmio_re||mmio_we)&&(dmem_re||dmem_we)) saw_parallel<=1;
            if (!valid_e && !dmem_re && !dmem_we) saw_invalid_bubble<=1;
            assert(!(dmem_re&&dmem_we)); assert(!(mmio_re&&mmio_we));
            assert(!dmem_we||(dmem_wstrb!=0));
            assert(valid_e||(!dmem_re&&!dmem_we));
            assert(valid_m||(!mmio_re&&!mmio_we));
            assert(!(dmem_re||dmem_we)||!(dut.mmio_window_hit_e));
            assert(!(mmio_re||mmio_we)||mmio_ready);
            assert(!$isunknown({pc_sel,pc_en,if_id_en,if_id_flush,id_ex_flush,
                alu_ctrl,alu_src_a_sel,alu_src_b_sel,fwd_a,fwd_b,fwd_store}));
            assert(dut.u_regfile.regs[0]===32'b0);
            if (valid_d && instr_d==32'hffff_ffff &&
                !regwrite_d&&!memread_d&&!memwrite_d&&branch_type_d==BR_NONE&&jump_d==J_NONE)
                illegal_seen<=1;
        end
    end

    int jalr_setup_index, jalr_target_index, auipc_index;
    initial begin
        errors=0; completed=0; program_words=0; rst_n=0;
        // ALU, immediate, LUI/AUIPC, and forwarding chains.
        emit(itype(256,0,0,1,7'h13)); emit(itype(5,0,0,2,7'h13));
        emit(itype(3,0,0,3,7'h13)); emit(rtype(0,0,3,2,4));
        emit(rtype(32,0,3,2,5)); emit(rtype(0,7,3,2,6));
        emit(rtype(0,6,3,2,7)); emit(rtype(0,4,3,2,8));
        emit(rtype(0,2,3,2,9)); emit(rtype(0,3,3,2,10));
        emit(rtype(0,1,3,2,11)); emit(rtype(0,5,3,11,12));
        emit(itype(-1,0,0,13,7'h13)); emit(rtype(32,5,3,13,14));
        emit(itype(6,2,7,15,7'h13)); emit(itype(2,2,6,16,7'h13));
        emit(itype(3,2,4,17,7'h13)); emit(itype(0,13,2,18,7'h13));
        emit(itype(1,13,3,19,7'h13)); emit(itype(2,2,1,15,7'h13));
        emit(itype(1,11,5,16,7'h13)); emit(itype(12'h401,13,5,17,7'h13));
        emit(utype(20'h12345,22,7'h37)); auipc_index=program_words;
        emit(utype(20'h1,23,7'h17));
        emit(stype(32,23,1,2));
        // Producer reaches W on the same edge its consumer is in D; the
        // resulting signature proves the regfile's WB->ID bypass in-system.
        emit(itype(9,0,0,24,7'h13)); emit(itype(0,0,0,0,7'h13));
        emit(itype(0,0,0,0,7'h13)); emit(itype(1,24,0,25,7'h13));
        emit(stype(48,25,1,2));

        // Loads, exactly one load-use bubble, all lanes and consecutive loads.
        emit(itype(4,1,2,24,7'h03)); emit(itype(1,24,0,25,7'h13));
        emit(itype(0,1,0,26,7'h03)); emit(itype(1,1,0,27,7'h03));
        emit(itype(2,1,0,28,7'h03)); emit(itype(3,1,0,29,7'h03));
        emit(itype(0,1,4,26,7'h03)); emit(itype(1,1,4,27,7'h03));
        emit(itype(2,1,4,28,7'h03)); emit(itype(3,1,4,29,7'h03));
        emit(itype(0,1,1,26,7'h03)); emit(itype(2,1,1,27,7'h03));
        emit(itype(0,1,5,28,7'h03)); emit(itype(2,1,5,29,7'h03));
        emit(itype(0,1,2,26,7'h03)); emit(itype(4,1,2,27,7'h03));

        // Stores: SB lanes, SH lanes, SW, consecutive and store->load.
        emit(stype(16,2,1,0)); emit(stype(17,3,1,0));
        emit(stype(18,4,1,0)); emit(stype(19,5,1,0));
        emit(stype(20,22,1,1)); emit(stype(22,25,1,1));
        emit(stype(24,24,1,2)); emit(stype(28,25,1,2));
        emit(itype(28,1,2,30,7'h03));

        // MMIO valid access followed by E SRAM access (parallel external ports).
        emit(utype(20'h40000,20,7'h37)); emit(stype(8,4,20,2));
        emit(itype(0,1,2,21,7'h03)); emit(itype(8,20,2,22,7'h03));
        // Rejected MMIO and SRAM accesses.
        emit(itype(36,20,2,23,7'h03)); emit(itype(1,20,2,23,7'h03));
        emit(itype(8,20,0,23,7'h03)); emit(stype(8,2,20,0));
        emit(stype(8,2,20,1)); emit(itype(1,1,2,23,7'h03));
        emit(stype(1,2,1,2)); emit(utype(20'h00040,28,7'h37));
        emit(itype(0,28,2,23,7'h03)); emit(stype(0,2,28,2));

        // Each branch is followed by a would-be wrong-path increment.
        emit(btype(8,2,2,0)); emit(itype(1,0,0,31,7'h13));
        emit(btype(8,3,2,0)); emit(itype(1,31,0,31,7'h13));
        emit(btype(8,3,2,1)); emit(itype(2,31,0,31,7'h13));
        emit(btype(8,2,2,1)); emit(itype(4,31,0,31,7'h13));
        emit(btype(8,3,13,4)); emit(stype(40,2,1,2));
        emit(btype(8,13,3,5)); emit(itype(8,31,0,31,7'h13));
        emit(btype(8,13,3,6)); emit(stype(12,2,20,2));
        emit(btype(8,3,13,7)); emit(itype(16,31,0,31,7'h13));

        emit(jtype(8,27)); emit(stype(44,2,1,2));
        jalr_setup_index=program_words; emit(32'h0000_0013);
        emit(itype(1,28,0,29,7'h67)); emit(stype(16,2,20,2));
        jalr_target_index=program_words;
        emit(32'hffff_ffff); emit(itype(9,0,0,0,7'h13));
        emit(jtype(0,0));
        put(jalr_setup_index,itype(12'(jalr_target_index*4),0,0,28,7'h13));

        // Data words 0x80ff7f01 and 0x12345678 at 0x100/0x104.
        u_dmem.mem[256]=8'h01; u_dmem.mem[257]=8'h7f;
        u_dmem.mem[258]=8'hff; u_dmem.mem[259]=8'h80;
        u_dmem.mem[260]=8'h78; u_dmem.mem[261]=8'h56;
        u_dmem.mem[262]=8'h34; u_dmem.mem[263]=8'h12;
        repeat(3) @(posedge clk); #1; rst_n=1;
        repeat(500) begin
            @(posedge clk); #1;
            if (dut.pc_q == (program_words-1)*4 && cycles>20) begin
                repeat(8) @(posedge clk); #1;
                check_reg(0,0,"x0 constant"); check_reg(4,8,"ADD and forwarding");
                check_reg(5,2,"SUB"); check_reg(6,1,"AND"); check_reg(7,7,"OR");
                check_reg(8,6,"XOR"); check_reg(9,0,"SLT"); check_reg(10,0,"SLTU");
                check_reg(11,40,"SLL"); check_reg(12,5,"SRL");
                check_reg(14,32'hffff_ffff,"SRA"); check_reg(18,1,"SLTI");
                check_reg(19,0,"SLTIU"); check_reg(21,32'h80ff_7f01,"MMIO/SRAM parallel load");
                check_reg(22,8,"MMIO readback"); check_reg(23,0,"invalid load returns zero");
                check_reg(25,32'h1234_5679,"one bubble load-use");
                check_reg(30,32'h1234_5679,"store-load same address");
                check_reg(31,5,"taken/not-taken branch paths");
                if (memword(288)!==auipc_index*4+32'h1000)
                    fail("AUIPC","stored PC-relative result mismatch");
                if (memword(304)!==32'd10) fail("WB to ID bypass","signature mismatch");
                if (dut.u_regfile.regs[27]!==((jalr_setup_index-1)*4))
                    fail("JAL link","PC+4 mismatch");
                if (dut.u_regfile.regs[29]!==((jalr_setup_index+2)*4))
                    fail("JALR link","PC+4 mismatch");
                if (dut.jalr_target[0]!==1'b0) fail("JALR","target bit0 not cleared");
                if (memword(272)!==32'h0208_0305) fail("SB lanes","byte stores mismatch");
                if (memword(276)!==32'h5679_5000)
                    fail("SH lanes",$sformatf("expected=56795000 actual=%08x",memword(276)));
                if (memword(284)!==32'h1234_5679) fail("SW/store-load","word mismatch");
                if (memword(296)!==0 || memword(300)!==0)
                    fail("wrong-path SRAM","store committed");
                if (u_mmio.write_count!==1) fail("MMIO writes","illegal/wrong-path write committed");
                if (load_stalls!==1) fail("load-use",$sformatf("expected one stall got %0d",load_stalls));
                if (redirects<7) fail("redirect coverage","too few redirects");
                if (!saw_parallel) fail("parallel ports","M MMIO and E SRAM not observed");
                if (!saw_invalid_bubble) fail("valid bubble","not observed");
                if (dmem_reads<15||dmem_writes<8||mmio_reads!=1||mmio_writes!=1)
                    fail("transaction scoreboard","unexpected transaction totals");
                if (!illegal_seen) fail("illegal instruction","safe NOP not observed");
                if (errors!=0) $fatal(1,"complete datapath failures: %0d",errors);
                completed=1;
                break;
            end
        end
        if (!completed) $fatal(1,"timeout after 500 cycles pc=%08x",dut.pc_q);
        $display("PASS: complete CPU datapath with test stubs");
        $finish;
    end

    initial begin
        #1;
        if (dmem_we||mmio_we) fail("reset side effects","write active during reset");
    end
endmodule
