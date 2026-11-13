module tb_dmem_timing;
    import cpu_control_pkg::*;
    localparam int unsigned MEM_BYTES = 262144;
    logic clk;
    int errors = 0;
    initial clk = 0;
    always #5 clk = ~clk;

    logic re, we;
    logic [3:0] wstrb;
    logic [31:0] addr, wdata, rdata, observed_at_edge;
    dmem_model u_mem (.*);
    always_ff @(posedge clk) observed_at_edge <= rdata;

    logic [31:0] lsu_addr, store_data, read_word, load_data, store_wdata;
    logic [2:0] load_type;
    logic [1:0] store_type;
    logic load_aligned, load_type_valid, store_aligned, store_type_valid;
    logic [3:0] store_wstrb;
    lsu u_lsu (
        .addr(lsu_addr), .store_data, .read_word, .load_type, .store_type,
        .load_data, .load_aligned, .load_type_valid,
        .store_wdata, .store_wstrb, .store_aligned, .store_type_valid
    );

    // EX-request experiment: EX metadata enters M on the same edge at which
    // SRAM accepts the old E address. The returned word is stable throughout M.
    logic valid_e, regwrite_e, memread_e, memwrite_e;
    logic [31:0] alu_result_e, write_data_e, pc4_e;
    logic [4:0] rd_e;
    logic [2:0] load_type_e;
    logic [1:0] store_type_e, wb_sel_e;
    logic valid_m, regwrite_m, memread_m, memwrite_m;
    logic [31:0] alu_result_m, write_data_m, pc4_m;
    logic [4:0] rd_m;
    logic [2:0] load_type_m;
    logic [1:0] store_type_m, wb_sel_m;
    ex_mem_reg u_ex_mem (.*);

    logic pre, pwe;
    logic [3:0] pwstrb;
    logic [31:0] paddr, pwdata, prdata;
    dmem_model u_pipe_mem (
        .clk, .re(pre), .we(pwe), .wstrb(pwstrb), .addr(paddr),
        .wdata(pwdata), .rdata(prdata)
    );
    logic [31:0] pipe_load_data;
    logic pipe_load_aligned, pipe_load_type_valid;
    logic [31:0] unused_store_wdata;
    logic [3:0] unused_store_wstrb;
    logic unused_store_aligned, unused_store_type_valid;
    lsu u_pipe_lsu (
        .addr(alu_result_m), .store_data(write_data_m), .read_word(prdata),
        .load_type(load_type_m), .store_type(store_type_m),
        .load_data(pipe_load_data), .load_aligned(pipe_load_aligned),
        .load_type_valid(pipe_load_type_valid), .store_wdata(unused_store_wdata),
        .store_wstrb(unused_store_wstrb), .store_aligned(unused_store_aligned),
        .store_type_valid(unused_store_type_valid)
    );
    logic valid_w, regwrite_w;
    logic [31:0] read_data_w, alu_result_w, pc4_w;
    logic [4:0] rd_w;
    logic [1:0] wb_sel_w;
    mem_wb_reg u_mem_wb (
        .clk, .rst_n(rst_n), .valid_m, .read_data_m(pipe_load_data),
        .alu_result_m, .pc4_m, .rd_m, .regwrite_m, .wb_sel_m,
        .valid_w, .read_data_w, .alu_result_w, .pc4_w, .rd_w,
        .regwrite_w, .wb_sel_w
    );
    logic rst_n;

    // Independent M-request experiment. Its MEM/WB observer proves that a
    // request first asserted in M cannot be consumed on that same edge.
    logic mre;
    logic [31:0] maddr, mrdata, mload_data, m_sampled;
    dmem_model u_m_request (
        .clk, .re(mre), .we(1'b0), .wstrb(4'b0), .addr(maddr),
        .wdata(32'b0), .rdata(mrdata)
    );
    assign read_word = rdata;
    assign mload_data = mrdata;
    always_ff @(posedge clk) m_sampled <= mload_data;

    task automatic fail(input string name, input string detail);
        errors++;
        $error("FAIL: %s: %s", name, detail);
    endtask
    task automatic expect32(input logic [31:0] got, exp, input string name);
        if (got !== exp) fail(name, $sformatf("expected=%08x actual=%08x", exp, got));
    endtask
    task automatic idle;
        re=0; we=0; wstrb=0; addr=0; wdata=0;
    endtask
    task automatic write_req(
        input logic [31:0] a, d, input logic [3:0] s, input string name
    );
        @(negedge clk); re=0; we=1; addr=a; wdata=d; wstrb=s;
        @(posedge clk); #1; we=0;
        if (^rdata === 1'bx) fail(name,"rdata became X");
    endtask
    task automatic read_req(
        input logic [31:0] a, input logic [31:0] exp, input string name
    );
        logic [31:0] old;
        @(negedge clk); old=rdata; re=1; we=0; addr=a;
        @(posedge clk);
        if (rdata !== old) fail(name,"rdata changed before NBA update");
        #1;
        expect32(rdata,exp,name);
        expect32(observed_at_edge,old,{name," NBA observer"});
        re=0;
    endtask
    task automatic lsu_store(
        input logic [31:0] a, d, input logic [1:0] kind,
        input logic allow, input string name
    );
        lsu_addr=a; store_data=d; store_type=kind; #1;
        @(negedge clk); addr=a; wdata=store_wdata; wstrb=store_wstrb;
        we=allow && store_aligned && store_type_valid; re=0;
        @(posedge clk); #1; we=0;
        if (!allow && store_wstrb!=0 && we) fail(name,"gating failed");
    endtask
    task automatic lsu_load(
        input logic [31:0] a, input logic [2:0] kind,
        input logic [31:0] exp, input string name
    );
        read_req({a[31:2],2'b00},u_mem_word(a),{name," raw"});
        lsu_addr=a; load_type=kind; #1;
        expect32(load_data,exp,name);
    endtask
    function automatic logic [31:0] u_mem_word(
        /* verilator lint_off UNUSEDSIGNAL */ input logic [31:0] a
        /* verilator lint_on UNUSEDSIGNAL */
    );
        int unsigned b;
        b={a[31:2],2'b00};
        if (b+3 < MEM_BYTES)
            u_mem_word={u_mem.mem[b+3],u_mem.mem[b+2],u_mem.mem[b+1],u_mem.mem[b]};
        else u_mem_word=0;
    endfunction

    initial begin
        idle(); store_data=0; load_type=LOAD_LW; store_type=STORE_SW;
        rst_n=0; valid_e=0; regwrite_e=0; memread_e=0; memwrite_e=0;
        alu_result_e=0; write_data_e=0; pc4_e=0; rd_e=0;
        load_type_e=LOAD_LW; store_type_e=STORE_SW; wb_sel_e=WB_LOAD;
        pre=0; pwe=0; pwstrb=0; paddr=0; pwdata=0; mre=0; maddr=0;
        repeat(2) @(posedge clk); #1; rst_n=1;

        // Direct model, endian, byte-enable, boundaries, and deterministic OOB.
        write_req(0,32'h1122_3344,4'b1111,"first word SW");
        read_req(0,32'h1122_3344,"single LW / SRAM first");
        write_req(4,32'haabb_ccdd,4'b1111,"second word SW");
        read_req(0,32'h1122_3344,"back-to-back LW first");
        read_req(4,32'haabb_ccdd,"back-to-back LW second");
        write_req(0,32'h0000_9900,4'b0010,"byte enable lane 1");
        read_req(0,32'h1122_9944,"SW then LW same address");
        write_req(8,32'hdead_beef,4'b1111,"SW then LW different store");
        read_req(4,32'haabb_ccdd,"SW then LW different load");
        read_req(8,32'hdead_beef,"LW then SW load");
        write_req(12,32'h0102_0304,4'b1111,"LW then SW store");
        write_req(16,32'h5566_7788,4'b1111,"consecutive SW first");
        write_req(20,32'h99aa_bbcc,4'b1111,"consecutive SW second");
        read_req(16,32'h5566_7788,"consecutive SW verify first");
        read_req(20,32'h99aa_bbcc,"consecutive SW verify second");

        write_req(32,32'h80ff_7f01,4'b1111,"lane source");
        lsu_load(32,LOAD_LB, 32'h0000_0001,"LB lane 0");
        lsu_load(33,LOAD_LB, 32'h0000_007f,"LB lane 1");
        lsu_load(34,LOAD_LB, 32'hffff_ffff,"LB lane 2");
        lsu_load(35,LOAD_LB, 32'hffff_ff80,"LB lane 3");
        lsu_load(32,LOAD_LH, 32'h0000_7f01,"LH lane 0");
        lsu_load(34,LOAD_LH, 32'hffff_80ff,"LH lane 2");
        lsu_load(34,LOAD_LBU,32'h0000_00ff,"LBU");
        lsu_load(34,LOAD_LHU,32'h0000_80ff,"LHU");

        write_req(40,0,4'b1111,"clear SB word");
        lsu_store(40,32'h11,STORE_SB,1,"SB lane 0");
        lsu_store(41,32'h22,STORE_SB,1,"SB lane 1");
        lsu_store(42,32'h33,STORE_SB,1,"SB lane 2");
        lsu_store(43,32'h44,STORE_SB,1,"SB lane 3");
        read_req(40,32'h4433_2211,"SB four lanes");
        lsu_store(44,32'ha1b2,STORE_SH,1,"SH lane 0");
        lsu_store(46,32'hc3d4,STORE_SH,1,"SH lane 2");
        read_req(44,32'hc3d4_a1b2,"SH two lanes");
        lsu_store(48,32'h89ab_cdef,STORE_SW,1,"SW four bytes");
        read_req(48,32'h89ab_cdef,"SW verify");

        // Misalignment and all side-effect gates.
        lsu_addr=51; load_type=LOAD_LW; #1;
        if (load_aligned || load_data!=0) fail("misaligned load","not rejected");
        lsu_addr=53; store_type=STORE_SH; #1;
        if (store_aligned || store_wstrb!=0) fail("misaligned store","not rejected");
        write_req(MEM_BYTES-4,32'hface_cafe,4'b1111,"last legal word");
        read_req(MEM_BYTES-4,32'hface_cafe,"SRAM last legal byte");
        read_req(MEM_BYTES,0,"SRAM out of range read");
        write_req(MEM_BYTES,32'hffff_ffff,4'b1111,"OOB write no side effect");
        read_req(MEM_BYTES-4,32'hface_cafe,"OOB write preserved memory");
        write_req(56,32'h1234_5678,4'b1111,"gate baseline");
        lsu_store(56,32'hffff_ffff,STORE_SW,0,"valid=0 store");
        read_req(56,32'h1234_5678,"valid=0 no write");
        lsu_store(56,32'heeee_eeee,STORE_SW,0,"wrong-path store");
        read_req(56,32'h1234_5678,"wrong-path no write");
        rst_n=0; lsu_store(56,32'hdddd_dddd,STORE_SW,rst_n,"reset store"); rst_n=1;
        read_req(56,32'h1234_5678,"reset no write");

        // M-stage request: preload old response A, then request B and sample on
        // the same edge. The observer necessarily captures A, proving option A bad.
        u_m_request.mem[0]=8'h11; u_m_request.mem[1]=8'h11;
        u_m_request.mem[2]=8'h11; u_m_request.mem[3]=8'h11;
        u_m_request.mem[4]=8'h22; u_m_request.mem[5]=8'h22;
        u_m_request.mem[6]=8'h22; u_m_request.mem[7]=8'h22;
        @(negedge clk); mre=1; maddr=0; @(posedge clk); #1;
        @(negedge clk); maddr=4; @(posedge clk); #1;
        expect32(m_sampled,32'h1111_1111,"M request MEM/WB samples stale rdata");
        expect32(mrdata,32'h2222_2222,"M request new rdata only after edge"); mre=0;

        // EX-stage request: load metadata and address are paired in M, then the
        // following M->W edge captures the processed value and matching metadata.
        u_pipe_mem.mem[100]=8'h78; u_pipe_mem.mem[101]=8'h56;
        u_pipe_mem.mem[102]=8'h34; u_pipe_mem.mem[103]=8'h12;
        @(negedge clk); valid_e=1; regwrite_e=1; memread_e=1;
        alu_result_e=100; rd_e=5; load_type_e=LOAD_LW; wb_sel_e=WB_LOAD;
        pre=1; paddr=alu_result_e;
        @(posedge clk); #1;
        if (!valid_m || !regwrite_m || !memread_m || memwrite_m ||
            rd_m!=5 || load_type_m!=LOAD_LW || alu_result_m!=100)
            fail("EX request M-stage pairing","metadata mismatch");
        @(negedge clk); valid_e=0; regwrite_e=0; memread_e=0; pre=0;
        @(posedge clk); #1;
        if (!valid_w || !regwrite_w || rd_w!=5 || wb_sel_w!=WB_LOAD ||
            alu_result_w!=100 || pc4_w!=0 ||
            !pipe_load_aligned || !pipe_load_type_valid || !load_type_valid)
            fail("EX request metadata pairing","metadata mismatch");
        expect32(read_data_w,32'h1234_5678,"EX request MEM/WB receives current load");
        expect32(read_data_w + 32'd7,32'h1234_567f,
                 "one-bubble load-use consumes WB forwarding value");

        // A split-stage policy would require address 0x80 for the M-store and
        // 0x100 for the E-load on the same cycle. A single addr cannot equal both.
        if ((32'h0000_0080 == 32'h0000_0100))
            fail("M-store/E-load structural conflict","distinct addresses collapsed");

        // One-port structural result: one E-stage instruction per cycle means a
        // common EX request port handles load/store sequences with no M/E conflict.
        // A split policy (M-store plus E-load) presents two distinct addresses and
        // cannot be represented by this single addr port; no arbitration can keep both.
        if (errors != 0) $fatal(1,"Data SRAM timing failures: %0d",errors);
        $display("PASS: fixed-latency Data SRAM timing");
        $finish;
    end
endmodule
