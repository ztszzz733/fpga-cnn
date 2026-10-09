`timescale 1ns/1ps

/*
 * Pure Verilog testbench for Vivado/XSim.
 * The production design remains SystemVerilog because it uses package,
 * logic, always_comb and always_ff constructs supported by Vivado.
 */
module tb_add_vivado;
    reg clk;
    reg rst_n;

    reg         io_mem_req;
    reg         io_mem_we;
    reg  [31:0] io_mem_addr;
    reg  [31:0] io_mem_wdata;
    reg  [3:0]  io_mem_be;
    wire        io_mem_gnt;
    wire        io_mem_rvalid;
    wire [31:0] io_mem_rdata;
    wire        io_mem_error;

    reg         cnn_mem_req;
    reg         cnn_mem_we;
    reg  [31:0] cnn_mem_addr;
    reg  [31:0] cnn_mem_wdata;
    reg  [3:0]  cnn_mem_be;
    wire        cnn_mem_gnt;
    wire        cnn_mem_rvalid;
    wire [31:0] cnn_mem_rdata;
    wire        cnn_mem_error;

    wire [31:0] CONTROL;
    reg  [31:0] STATUS;
    wire [31:0] INPUT_ADDR;
    wire [31:0] OUTPUT_ADDR;
    wire [31:0] WEIGHT_ADDR;
    wire [31:0] BIAS_ADDR;
    wire [31:0] IMAGE_SIZE;
    wire [31:0] CHANNELS;
    wire [31:0] CNN_PARAM;

    /* These four testbench-only observation signals appear in the waveform. */
    wire [31:0] x1_value;
    wire [31:0] x2_value;
    wire [31:0] x6_value;
    integer rf_writes;
    integer dmem_reads;
    integer dmem_writes;
    integer mmio_reads;
    integer mmio_writes;
    integer i;

    face_soc_cpu_memory_top #(
        .IMEM_SIZE(32'h0000_0100),
        .SRAM_SIZE(32'h0000_0100)
    ) dut (
        .clk(clk),
        .rst_n(rst_n),
        .io_mem_req(io_mem_req),
        .io_mem_we(io_mem_we),
        .io_mem_addr(io_mem_addr),
        .io_mem_wdata(io_mem_wdata),
        .io_mem_be(io_mem_be),
        .io_mem_gnt(io_mem_gnt),
        .io_mem_rvalid(io_mem_rvalid),
        .io_mem_rdata(io_mem_rdata),
        .io_mem_error(io_mem_error),
        .cnn_mem_req(cnn_mem_req),
        .cnn_mem_we(cnn_mem_we),
        .cnn_mem_addr(cnn_mem_addr),
        .cnn_mem_wdata(cnn_mem_wdata),
        .cnn_mem_be(cnn_mem_be),
        .cnn_mem_gnt(cnn_mem_gnt),
        .cnn_mem_rvalid(cnn_mem_rvalid),
        .cnn_mem_rdata(cnn_mem_rdata),
        .cnn_mem_error(cnn_mem_error),
        .CONTROL(CONTROL),
        .STATUS(STATUS),
        .INPUT_ADDR(INPUT_ADDR),
        .OUTPUT_ADDR(OUTPUT_ADDR),
        .WEIGHT_ADDR(WEIGHT_ADDR),
        .BIAS_ADDR(BIAS_ADDR),
        .IMAGE_SIZE(IMAGE_SIZE),
        .CHANNELS(CHANNELS),
        .CNN_PARAM(CNN_PARAM)
    );

    assign x1_value = dut.u_cpu_datapath.u_regfile.regs[1];
    assign x2_value = dut.u_cpu_datapath.u_regfile.regs[2];
    assign x6_value = dut.u_cpu_datapath.u_regfile.regs[6];

    initial begin
        clk = 1'b0;
        rst_n = 1'b0;
        io_mem_req = 1'b0;
        io_mem_we = 1'b0;
        io_mem_addr = 32'b0;
        io_mem_wdata = 32'b0;
        io_mem_be = 4'b0;
        cnn_mem_req = 1'b0;
        cnn_mem_we = 1'b0;
        cnn_mem_addr = 32'b0;
        cnn_mem_wdata = 32'b0;
        cnn_mem_be = 4'b0;
        STATUS = 32'b0;
        rf_writes = 0;
        dmem_reads = 0;
        dmem_writes = 0;
        mmio_reads = 0;
        mmio_writes = 0;

        /* Program is stored inside the simulated instruction ROM. */
        for (i = 0; i < 64; i = i + 1)
            dut.u_memory.u_imem.mem[i] = 32'h0000_0013; /* NOP: addi x0,x0,0 */
        dut.u_memory.u_imem.mem[0] = 32'h0020_8333;     /* add x6,x1,x2 */

        /* Hold reset for three cycles, then prepare the two ADD source values. */
        repeat (3) @(negedge clk);
        dut.u_cpu_datapath.u_regfile.regs[1] = 32'd1;
        dut.u_cpu_datapath.u_regfile.regs[2] = 32'd2;
        rst_n = 1'b1;

        repeat (10) @(negedge clk);
        #1;
        if (x1_value !== 32'd1) begin
            $display("FAIL: x1 expected 1, got %0d", x1_value);
            $finish;
        end
        if (x2_value !== 32'd2) begin
            $display("FAIL: x2 expected 2, got %0d", x2_value);
            $finish;
        end
        if (x6_value !== 32'd3) begin
            $display("FAIL: x6 expected 3, got %0d", x6_value);
            $finish;
        end
        if (rf_writes !== 1) begin
            $display("FAIL: expected one architectural register write, got %0d", rf_writes);
            $finish;
        end
        if ((dmem_reads !== 0) || (dmem_writes !== 0) ||
            (mmio_reads !== 0) || (mmio_writes !== 0)) begin
            $display("FAIL: ADD produced a memory or MMIO side effect");
            $finish;
        end

        $display("VIVADO_ADD_RESULT x1=%0d x2=%0d x6=%0d rf_writes=%0d dmem_reads=%0d dmem_writes=%0d mmio_reads=%0d mmio_writes=%0d",
                 x1_value, x2_value, x6_value, rf_writes,
                 dmem_reads, dmem_writes, mmio_reads, mmio_writes);
        $display("PASS: Vivado Verilog testbench + real Control + production Datapath ADD");
        $finish;
    end

    always #5 clk = ~clk;

    always @(posedge clk) begin
        if (rst_n) begin
            if (dut.u_cpu_datapath.rf_we)
                rf_writes = rf_writes + 1;
            if (dut.u_cpu_datapath.dmem_re)
                dmem_reads = dmem_reads + 1;
            if (dut.u_cpu_datapath.dmem_we)
                dmem_writes = dmem_writes + 1;
            if (dut.u_cpu_datapath.mmio_re)
                mmio_reads = mmio_reads + 1;
            if (dut.u_cpu_datapath.mmio_we)
                mmio_writes = mmio_writes + 1;
        end
    end
endmodule
