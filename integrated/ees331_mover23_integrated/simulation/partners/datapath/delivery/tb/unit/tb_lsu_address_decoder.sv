module tb_lsu_address_decoder;
    import cpu_control_pkg::*;

    int errors;
    logic [31:0] addr;
    logic sram_hit, mmio_window_hit, mmio_reg_hit, unmapped;
    logic high_sram_hit, high_mmio_window_hit, high_mmio_reg_hit, high_unmapped;

    logic [31:0] store_data, read_word, load_data, store_wdata;
    logic [2:0] load_type;
    logic [1:0] store_type;
    logic load_aligned, load_type_valid, store_aligned, store_type_valid;
    logic [3:0] store_wstrb;

    address_decoder u_decoder (
        .addr, .sram_hit, .mmio_window_hit, .mmio_reg_hit, .unmapped
    );
    address_decoder #(
        .SRAM_BASE(32'hffff_f000), .SRAM_SIZE(32'h0000_1000)
    ) u_high_decoder (
        .addr, .sram_hit(high_sram_hit), .mmio_window_hit(high_mmio_window_hit),
        .mmio_reg_hit(high_mmio_reg_hit), .unmapped(high_unmapped)
    );
    lsu u_lsu (
        .addr, .store_data, .read_word, .load_type, .store_type,
        .load_data, .load_aligned, .load_type_valid,
        .store_wdata, .store_wstrb, .store_aligned, .store_type_valid
    );

    task automatic fail(input string name, input string detail);
        errors++;
        $error("FAIL: %s: %s", name, detail);
    endtask

    task automatic check_addr(
        input logic [31:0] test_addr,
        input logic exp_sram, exp_window, exp_reg, exp_unmapped,
        input string name
    );
        addr=test_addr; #1;
        if ({sram_hit,mmio_window_hit,mmio_reg_hit,unmapped} !==
            {exp_sram,exp_window,exp_reg,exp_unmapped})
            fail(name, $sformatf("addr=%08x expected=%b%b%b%b actual=%b%b%b%b",
                 addr, exp_sram, exp_window, exp_reg, exp_unmapped,
                 sram_hit, mmio_window_hit, mmio_reg_hit, unmapped));
        if (sram_hit && mmio_window_hit) fail(name, "SRAM and MMIO overlap");
        if (mmio_reg_hit && !mmio_window_hit) fail(name, "register hit outside window");
        if (unmapped !== !(sram_hit || mmio_window_hit)) fail(name, "unmapped definition");
    endtask

    task automatic check_high(
        input logic [31:0] test_addr, input logic expected, input string name
    );
        addr=test_addr; #1;
        if (high_sram_hit !== expected)
            fail(name, $sformatf("addr=%08x expected hit=%b actual=%b",
                                 addr, expected, high_sram_hit));
        if (high_sram_hit && high_mmio_window_hit) fail(name, "custom ranges overlap");
        if (high_mmio_reg_hit && !high_mmio_window_hit) fail(name, "custom reg invariant");
        if (high_unmapped !== !(high_sram_hit || high_mmio_window_hit))
            fail(name, "custom unmapped definition");
    endtask

    task automatic check_load(
        input logic [1:0] lane, input logic [2:0] kind,
        input logic [31:0] expected_data,
        input logic expected_aligned, expected_valid,
        input string name
    );
        addr={30'b0,lane}; load_type=kind; #1;
        if (load_data!==expected_data || load_aligned!==expected_aligned ||
            load_type_valid!==expected_valid)
            fail(name, $sformatf("expected data=%08x aligned=%b valid=%b; actual=%08x/%b/%b",
                 expected_data, expected_aligned, expected_valid,
                 load_data, load_aligned, load_type_valid));
    endtask

    task automatic check_store(
        input logic [1:0] lane, input logic [1:0] kind,
        input logic [31:0] expected_data, input logic [3:0] expected_strobe,
        input logic expected_aligned, expected_valid,
        input string name
    );
        addr={30'b0,lane}; store_type=kind; #1;
        if (store_wdata!==expected_data || store_wstrb!==expected_strobe ||
            store_aligned!==expected_aligned || store_type_valid!==expected_valid)
            fail(name, $sformatf("expected data=%08x strobe=%b aligned=%b valid=%b; actual=%08x/%b/%b/%b",
                 expected_data, expected_strobe, expected_aligned, expected_valid,
                 store_wdata, store_wstrb, store_aligned, store_type_valid));
    endtask

    initial begin
        errors=0; addr=0; store_data=32'ha1b2_c3d4; read_word=32'h80ff_7f01;
        load_type=LOAD_LB; store_type=STORE_SB;

        check_addr(32'h0000_0000,1,0,0,0,"SRAM first");
        check_addr(32'h0000_0001,1,0,0,0,"SRAM byte");
        check_addr(32'h0003_fffc,1,0,0,0,"SRAM last word");
        check_addr(32'h0003_ffff,1,0,0,0,"SRAM last byte");
        check_addr(32'h0004_0000,0,0,0,1,"SRAM upper exclusive");
        check_addr(32'hffff_ffff,0,0,0,1,"top address unmapped");
        check_addr(32'h3fff_ffff,0,0,0,1,"before MMIO");
        check_addr(32'h4000_0000,0,1,1,0,"MMIO first");
        check_addr(32'h4000_0fff,0,1,0,0,"MMIO last byte");
        check_addr(32'h4000_1000,0,0,0,1,"after MMIO");

        check_addr(32'h4000_0000,0,1,1,0,"CONTROL");
        check_addr(32'h4000_0004,0,1,1,0,"STATUS");
        check_addr(32'h4000_0008,0,1,1,0,"INPUT_ADDR");
        check_addr(32'h4000_000c,0,1,1,0,"OUTPUT_ADDR");
        check_addr(32'h4000_0010,0,1,1,0,"WEIGHT_ADDR");
        check_addr(32'h4000_0014,0,1,1,0,"BIAS_ADDR");
        check_addr(32'h4000_0018,0,1,1,0,"FEATURE_SIZE");
        check_addr(32'h4000_001c,0,1,1,0,"CHANNELS");
        check_addr(32'h4000_0020,0,1,1,0,"LAYER_PARAM");
        check_addr(32'h4000_0001,0,1,0,0,"unaligned MMIO +1");
        check_addr(32'h4000_0002,0,1,0,0,"unaligned MMIO +2");
        check_addr(32'h4000_0003,0,1,0,0,"unaligned MMIO +3");
        check_addr(32'h4000_0024,0,1,0,0,"first unimplemented register");
        check_addr(32'h4000_00fc,0,1,0,0,"unimplemented register 0xfc");
        check_addr(32'h4000_0ffc,0,1,0,0,"unimplemented last word");

        check_high(32'hffff_effc,0,"high range below");
        check_high(32'hffff_f000,1,"high range first");
        check_high(32'hffff_f123,1,"high range inside");
        check_high(32'hffff_ffff,1,"high range last");
        check_high(32'h0000_0000,0,"high range no wrap to zero");
        check_high(32'h0000_0001,0,"high range no wrap to low address");

        check_load(0,LOAD_LB, 32'h0000_0001,1,1,"LB lane 0 positive");
        check_load(1,LOAD_LB, 32'h0000_007f,1,1,"LB lane 1 positive");
        check_load(2,LOAD_LB, 32'hffff_ffff,1,1,"LB lane 2 negative");
        check_load(3,LOAD_LB, 32'hffff_ff80,1,1,"LB lane 3 negative");
        check_load(0,LOAD_LBU,32'h0000_0001,1,1,"LBU lane 0");
        check_load(1,LOAD_LBU,32'h0000_007f,1,1,"LBU lane 1");
        check_load(2,LOAD_LBU,32'h0000_00ff,1,1,"LBU lane 2");
        check_load(3,LOAD_LBU,32'h0000_0080,1,1,"LBU lane 3");
        check_load(0,LOAD_LH, 32'h0000_7f01,1,1,"LH low positive");
        check_load(2,LOAD_LH, 32'hffff_80ff,1,1,"LH high negative");
        check_load(0,LOAD_LHU,32'h0000_7f01,1,1,"LHU low");
        check_load(2,LOAD_LHU,32'h0000_80ff,1,1,"LHU high");
        check_load(0,LOAD_LW, read_word,1,1,"LW aligned");
        check_load(1,LOAD_LH, 0,0,1,"LH misaligned lane 1");
        check_load(3,LOAD_LHU,0,0,1,"LHU misaligned lane 3");
        check_load(1,LOAD_LW, 0,0,1,"LW misaligned lane 1");
        check_load(2,LOAD_LW, 0,0,1,"LW misaligned lane 2");
        check_load(3,LOAD_LW, 0,0,1,"LW misaligned lane 3");
        check_load(0,3'b011,  0,0,0,"invalid load type");

        check_store(0,STORE_SB,32'h0000_00d4,4'b0001,1,1,"SB lane 0");
        check_store(1,STORE_SB,32'h0000_d400,4'b0010,1,1,"SB lane 1");
        check_store(2,STORE_SB,32'h00d4_0000,4'b0100,1,1,"SB lane 2");
        check_store(3,STORE_SB,32'hd400_0000,4'b1000,1,1,"SB lane 3");
        check_store(0,STORE_SH,32'h0000_c3d4,4'b0011,1,1,"SH low");
        check_store(2,STORE_SH,32'hc3d4_0000,4'b1100,1,1,"SH high");
        check_store(0,STORE_SW,32'ha1b2_c3d4,4'b1111,1,1,"SW aligned");
        check_store(1,STORE_SH,0,4'b0000,0,1,"SH misaligned lane 1");
        check_store(3,STORE_SH,0,4'b0000,0,1,"SH misaligned lane 3");
        check_store(1,STORE_SW,0,4'b0000,0,1,"SW misaligned lane 1");
        check_store(2,STORE_SW,0,4'b0000,0,1,"SW misaligned lane 2");
        check_store(3,STORE_SW,0,4'b0000,0,1,"SW misaligned lane 3");
        check_store(0,2'b11,0,4'b0000,0,0,"invalid store type");

        if (errors!=0) $fatal(1,"LSU/address decoder failures: %0d",errors);
        $display("PASS: LSU and address decoder");
        $finish;
    end
endmodule
