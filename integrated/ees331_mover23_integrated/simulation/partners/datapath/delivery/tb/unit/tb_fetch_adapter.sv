module tb_fetch_adapter;
    logic clk, rst_n;
    logic [31:0] request_pc;
    logic pc_en, if_id_en, flush;
    logic [31:0] imem_addr, imem_rdata;
    logic imem_re;
    logic fetch_valid;
    logic [31:0] fetch_instr, fetch_pc, fetch_pc4;

    int errors, accepted_count, delivered_count, flushed_count;
    logic [31:0] expected_pc [0:255];
    int q_head, q_tail, q_count;

    fetch_adapter u_dut (.*);
    always #5 clk=~clk;

    function automatic logic [31:0] instruction_for(input logic [31:0] pc_value);
        instruction_for = 32'ha5a5_0000 ^ pc_value;
    endfunction

    // A true fixed-one-cycle synchronous model: the address is sampled on an
    // edge and the corresponding data is assigned after that edge by NBA.
    always_ff @(posedge clk) begin
        if (imem_re) imem_rdata <= instruction_for(imem_addr);
        else imem_rdata <= 32'hdead_beef;
    end

    task automatic fail(input string name, input string detail);
        errors++;
        $error("FAIL: %s: %s",name,detail);
    endtask

    task automatic check(input logic condition, input string name);
        if (!condition) fail(name,"condition is false");
    endtask

    // Sample the values that a future IF/ID register will observe at the next
    // rising edge, before DUT/IMEM nonblocking assignments update the cycle.
    task automatic scoreboard_sample;
        if (!rst_n) begin
            q_head=0; q_tail=0; q_count=0;
            if (imem_re) fail("reset request","imem_re must be zero");
            if (fetch_valid) fail("reset response","fetch_valid must be zero");
        end else if (flush) begin
            flushed_count += q_count;
            q_head=0; q_tail=0; q_count=0;
            if (imem_re) fail("flush request","imem_re must be zero");
            if (fetch_valid) fail("flush response","fetch_valid must be zero");
        end else begin
            if (fetch_valid) begin
                if (fetch_pc4 !== fetch_pc+32'd4)
                    fail("PC+4 pairing",$sformatf("pc=%08x pc4=%08x",fetch_pc,fetch_pc4));
                if (fetch_instr !== instruction_for(fetch_pc))
                    fail("instruction pairing",$sformatf("pc=%08x instr=%08x expected=%08x",
                         fetch_pc,fetch_instr,instruction_for(fetch_pc)));
            end
            if (if_id_en && fetch_valid) begin
                if (q_count==0) fail("unexplained delivery","scoreboard is empty");
                else begin
                    if (fetch_pc !== expected_pc[q_head])
                        fail("delivery order",$sformatf("expected pc=%08x actual=%08x",
                             expected_pc[q_head],fetch_pc));
                    q_head=(q_head+1)%256; q_count--; delivered_count++;
                end
            end
            if (imem_re) begin
                if (q_count>=255) fail("scoreboard overflow","too many outstanding requests");
                else begin
                    expected_pc[q_tail]=imem_addr;
                    q_tail=(q_tail+1)%256; q_count++; accepted_count++;
                end
            end
            if (u_dut.buffer_valid_q && u_dut.req_valid_q)
                fail("buffer overflow","buffer and direct response valid together");
        end
    endtask

    task automatic step(
        input logic [31:0] pc_value,
        input logic pc_enable, ifid_enable, do_flush
    );
        @(negedge clk);
        request_pc=pc_value; pc_en=pc_enable; if_id_en=ifid_enable; flush=do_flush;
        #1;
        if ((!rst_n || do_flush) && imem_re)
            fail("combinational request gate","request active during reset/flush");
        scoreboard_sample();
        @(posedge clk); #1;
        if ((!rst_n || do_flush) && fetch_valid)
            fail("post-edge valid gate","response active during reset/flush");
    endtask

    task automatic reset_dut;
        @(negedge clk);
        rst_n=0; flush=0; pc_en=1; if_id_en=1; request_pc=32'hffff_1234;
        repeat (2) begin
            scoreboard_sample();
            @(posedge clk); #1;
            check(!imem_re,"reset imem_re");
            check(!fetch_valid,"reset fetch_valid");
            check(!u_dut.req_valid_q && !u_dut.buffer_valid_q,"reset internal valid");
        end
        @(negedge clk); rst_n=1; pc_en=0; if_id_en=1; request_pc=0;
    endtask

    initial begin : test_sequence
        logic [31:0] saved_instr, saved_pc, saved_pc4;
        logic [31:0] stress_pc;
        int before_deliveries;

        clk=0; rst_n=0; request_pc=0; pc_en=0; if_id_en=0; flush=0;
        errors=0; accepted_count=0; delivered_count=0; flushed_count=0;
        q_head=0; q_tail=0; q_count=0;

        // Reset and first fetch. No reset-history request may become a response.
        reset_dut();
        step(32'h0000_0000,1,1,0);
        check(fetch_valid && fetch_pc==0 && fetch_pc4==4 &&
              fetch_instr==instruction_for(0),"first fetch pairing");
        step(32'h0000_0004,0,1,0);
        check(!fetch_valid,"first fetch delivered once");

        // Eight consecutive requests: after initial fill every cycle has a response.
        reset_dut(); before_deliveries=delivered_count;
        for (int i=0;i<8;i++) begin
            step(32'(i*4),1,1,0);
            check(fetch_valid,"continuous response valid");
            check(fetch_pc==32'(i*4),"continuous PC sequence");
        end
        step(32'h0000_0020,0,1,0);
        check(!fetch_valid,"continuous drain");
        check(delivered_count-before_deliveries==8,"continuous one-per-cycle delivery count");

        // One-cycle pause captures the returned response, then consumes it once.
        reset_dut();
        step(32'h0000_0040,1,1,0);
        step(32'h0000_0044,0,0,0);
        check(u_dut.buffer_valid_q && fetch_valid && fetch_pc==32'h40,"single pause buffer");
        step(32'h0000_0044,1,1,0);
        check(!u_dut.buffer_valid_q && fetch_valid && fetch_pc==32'h44,
              "single pause release and next response");
        step(32'h0000_0048,0,1,0); check(!fetch_valid,"single pause no duplicate");

        // Three-cycle pause holds all cached fields and issues no requests.
        reset_dut();
        step(32'h0000_0080,1,1,0);
        step(32'h0000_0084,0,0,0);
        saved_instr=u_dut.buffer_instr_q; saved_pc=u_dut.buffer_pc_q;
        saved_pc4=u_dut.buffer_pc4_q;
        repeat (3) begin
            step(32'h0000_0084,0,0,0);
            check(!imem_re && u_dut.buffer_valid_q,"multi-pause valid/no request");
            check(u_dut.buffer_instr_q==saved_instr && u_dut.buffer_pc_q==saved_pc &&
                  u_dut.buffer_pc4_q==saved_pc4,"multi-pause buffer stable");
        end
        step(32'h0000_0084,1,1,0);
        check(fetch_valid && fetch_pc==32'h84 && !u_dut.buffer_valid_q,"multi-pause release");
        step(32'h0000_0088,0,1,0); check(!fetch_valid,"multi-pause no duplicate");

        // Pause with no outstanding request produces no response.
        reset_dut();
        repeat (3) begin step(32'h0000_00c0,0,0,0); check(!fetch_valid,"empty pause"); end
        step(32'h0000_00c0,1,1,0);
        check(fetch_valid && fetch_pc==32'hc0,"empty pause recovery");
        step(32'h0000_00c4,0,1,0);

        // Flush a direct/in-flight response, then restart from target 0x100.
        reset_dut();
        step(32'h0000_0020,1,1,0);
        step(32'h0000_0100,1,1,1);
        check(!u_dut.req_valid_q && !u_dut.buffer_valid_q,"flush direct state");
        step(32'h0000_0100,1,1,0);
        check(fetch_valid && fetch_pc==32'h100,"flush target first response");
        step(32'h0000_0104,0,1,0);

        // Put an old response in the buffer and flush it while also stalled.
        reset_dut();
        step(32'h0000_0060,1,1,0);
        step(32'h0000_0064,0,0,0);
        check(u_dut.buffer_valid_q,"precondition buffered response");
        step(32'h0000_0140,0,0,1);
        check(!u_dut.req_valid_q && !u_dut.buffer_valid_q,"flush buffered state priority");
        step(32'h0000_0140,1,1,0);
        check(fetch_valid && fetch_pc==32'h140,"buffer flush target response");
        step(32'h0000_0144,0,1,0);

        // Reset dominates simultaneous flush/enables and removes cached history.
        reset_dut();
        step(32'h0000_0180,1,1,0);
        step(32'h0000_0184,0,0,0);
        @(negedge clk); rst_n=0; flush=1; pc_en=1; if_id_en=1; request_pc=32'h200;
        #1; scoreboard_sample();
        @(posedge clk); #1;
        check(!imem_re && !fetch_valid && !u_dut.req_valid_q && !u_dut.buffer_valid_q,
              "reset priority over flush/enable");
        @(negedge clk); rst_n=1; flush=0; pc_en=0; if_id_en=1;

        // PC+4 wraps naturally at the 32-bit boundary.
        reset_dut();
        step(32'hffff_fffc,1,1,0);
        check(fetch_valid && fetch_pc==32'hffff_fffc && fetch_pc4==0,"PC+4 wrap");
        step(0,0,1,0);

        // Deterministic stress: continuous runs, 1-3 cycle stalls and redirects.
        reset_dut(); stress_pc=32'h0000_0200;
        for (int cycle=0;cycle<48;cycle++) begin
            if (cycle==9 || cycle==27 || cycle==39) begin
                stress_pc=stress_pc+32'h100;
                step(stress_pc,0,0,1);
            end else if ((cycle>=4 && cycle<=6) || cycle==16 ||
                         (cycle>=32 && cycle<=33)) begin
                step(stress_pc,0,0,0);
            end else begin
                step(stress_pc,1,1,0);
                stress_pc=stress_pc+4;
            end
        end
        step(stress_pc,0,1,0);
        check(q_count==0,"stress scoreboard drained");
        check(flushed_count>0,"stress exercised flushed requests");

        if (errors!=0) $fatal(1,"fetch adapter failures: %0d",errors);
        $display("PASS: fetch adapter");
        $finish;
    end
endmodule
