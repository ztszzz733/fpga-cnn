`timescale 1ns/1ps

module tb_b1_memory_subsystem;
    logic clk = 1'b0;
    logic rst_n = 1'b0;
    always #5 clk = ~clk;

    logic [31:0] imem_addr;
    logic imem_re;
    logic [31:0] imem_rdata;
    logic [31:0] dmem_addr, dmem_wdata, dmem_rdata;
    logic [3:0] dmem_wstrb;
    logic dmem_re, dmem_we;
    logic [31:0] mmio_addr, mmio_wdata, mmio_rdata;
    logic mmio_re, mmio_we, mmio_ready;

    logic io_mem_req, io_mem_we, io_mem_gnt, io_mem_rvalid, io_mem_error;
    logic [31:0] io_mem_addr, io_mem_wdata, io_mem_rdata;
    logic [3:0] io_mem_be;
    logic cnn_mem_req, cnn_mem_we, cnn_mem_gnt, cnn_mem_rvalid, cnn_mem_error;
    logic [31:0] cnn_mem_addr, cnn_mem_wdata, cnn_mem_rdata;
    logic [3:0] cnn_mem_be;

    logic [31:0] CONTROL, STATUS, INPUT_ADDR, OUTPUT_ADDR;
    logic [31:0] WEIGHT_ADDR, BIAS_ADDR, IMAGE_SIZE, CHANNELS, CNN_PARAM;
    integer checks = 0;

    datapath_memory_subsystem #(
        .IMEM_SIZE(32'h0000_0100),
        .SRAM_SIZE(32'h0000_0100)
    ) dut (.cnn_mmio_addr(), .cnn_mmio_wdata(), .cnn_mmio_re(), .cnn_mmio_we(),
           .cnn_mmio_rdata(32'b0), .cnn_mmio_ready(1'b0),
           .mem_addr(32'b0), .mem_wdata(32'b0), .mem_read(1'b0), .mem_write(1'b0),
           .mem_rdata(), .mem_ready(), .cnn_mem_fault(), .*);

    task automatic check(input logic condition, input string message);
        begin
            checks = checks + 1;
            if (!condition) $fatal(1, "CHECK FAILED: %s", message);
        end
    endtask

    task automatic a_write(
        input logic [31:0] addr,
        input logic [31:0] data,
        input logic [3:0] strobe
    );
        begin
            @(negedge clk);
            dmem_addr = addr; dmem_wdata = data; dmem_wstrb = strobe;
            dmem_we = 1'b1;
            @(posedge clk); #1;
            dmem_we = 1'b0;
        end
    endtask

    task automatic a_read_check(
        input logic [31:0] addr,
        input logic [31:0] expected,
        input string message
    );
        begin
            @(negedge clk);
            dmem_addr = addr; dmem_re = 1'b1;
            @(posedge clk); #1;
            dmem_re = 1'b0;
            check(dmem_rdata === expected, message);
        end
    endtask

    task automatic io_write_check(
        input logic [31:0] addr,
        input logic [31:0] data,
        input logic expect_error
    );
        begin
            @(negedge clk);
            io_mem_addr = addr; io_mem_wdata = data; io_mem_be = 4'hf;
            io_mem_we = 1'b1; io_mem_req = 1'b1;
            #1;
            check(io_mem_gnt && !cnn_mem_gnt, "IO write grant ownership");
            check(io_mem_error === expect_error, "IO write error value");
            @(posedge clk); #1;
            io_mem_req = 1'b0; io_mem_we = 1'b0; io_mem_be = 4'b0;
        end
    endtask

    task automatic io_read_check(
        input logic [31:0] addr,
        input logic [31:0] expected,
        input logic expect_error
    );
        begin
            @(negedge clk);
            io_mem_addr = addr; io_mem_be = 4'b0;
            io_mem_we = 1'b0; io_mem_req = 1'b1;
            #1;
            check(io_mem_gnt && !cnn_mem_gnt, "IO read grant ownership");
            @(posedge clk); #1;
            io_mem_req = 1'b0;
            check(io_mem_rvalid && !cnn_mem_rvalid, "IO read response ownership");
            check(io_mem_error === expect_error, "IO read error value");
            check(io_mem_rdata === expected, "IO read data");
            @(posedge clk); #1;
            check(!io_mem_rvalid, "IO read valid is a one-cycle pulse");
        end
    endtask

    task automatic mmio_write(input logic [31:0] addr, input logic [31:0] data);
        begin
            @(negedge clk);
            mmio_addr = addr; mmio_wdata = data; mmio_we = 1'b1;
            #1; check(mmio_ready, "MMIO write ready");
            @(posedge clk); #1;
            mmio_we = 1'b0;
        end
    endtask

    task automatic mmio_read_check(
        input logic [31:0] addr,
        input logic [31:0] expected,
        input string message
    );
        begin
            @(negedge clk);
            mmio_addr = addr; mmio_re = 1'b1;
            #1;
            check(mmio_ready, "MMIO read ready");
            check(mmio_rdata === expected, message);
            mmio_re = 1'b0;
        end
    endtask

    initial begin
        imem_addr = 0; imem_re = 0;
        dmem_addr = 0; dmem_wdata = 0; dmem_wstrb = 0; dmem_re = 0; dmem_we = 0;
        mmio_addr = 0; mmio_wdata = 0; mmio_re = 0; mmio_we = 0;
        io_mem_req = 0; io_mem_we = 0; io_mem_addr = 0; io_mem_wdata = 0; io_mem_be = 0;
        cnn_mem_req = 0; cnn_mem_we = 0; cnn_mem_addr = 0; cnn_mem_wdata = 0; cnn_mem_be = 0;
        STATUS = 32'h0000_0005;

        repeat (3) @(posedge clk);
        @(negedge clk); rst_n = 1'b1;

        /* CPU A port: whole-word and byte-enable behavior. */
        a_write(32'h10, 32'h1122_3344, 4'hf);
        a_read_check(32'h10, 32'h1122_3344, "A port word read/write");
        a_write(32'h10, 32'haa00_cc00, 4'b1010);
        a_read_check(32'h10, 32'haa22_cc44, "A port byte strobes");

        /* External image bridge path through the B arbiter. */
        io_write_check(32'h20, 32'hdead_beef, 1'b0);
        io_read_check(32'h20, 32'hdead_beef, 1'b0);

        /* Simultaneous requests: fixed priority belongs to the CNN master. */
        @(negedge clk);
        io_mem_req = 1; io_mem_we = 1; io_mem_addr = 32'h24;
        io_mem_wdata = 32'h1111_1111; io_mem_be = 4'hf;
        cnn_mem_req = 1; cnn_mem_we = 1; cnn_mem_addr = 32'h24;
        cnn_mem_wdata = 32'h2222_2222; cnn_mem_be = 4'hf;
        #1;
        check(cnn_mem_gnt && !io_mem_gnt, "CNN fixed priority over IO");
        @(posedge clk); #1;
        io_mem_req = 0; io_mem_we = 0; io_mem_be = 0;
        cnn_mem_req = 0; cnn_mem_we = 0; cnn_mem_be = 0;
        a_read_check(32'h24, 32'h2222_2222, "CNN priority write reached SRAM");

        /* A wins a same-word collision; the rejected B write reports error. */
        @(negedge clk);
        dmem_addr = 32'h28; dmem_wdata = 32'haaaa_5555; dmem_wstrb = 4'hf; dmem_we = 1;
        io_mem_addr = 32'h28; io_mem_wdata = 32'h5555_aaaa; io_mem_be = 4'hf;
        io_mem_we = 1; io_mem_req = 1;
        #1;
        check(io_mem_gnt && io_mem_error, "B conflict is granted with error");
        @(posedge clk); #1;
        dmem_we = 0; io_mem_req = 0; io_mem_we = 0; io_mem_be = 0;
        a_read_check(32'h28, 32'haaaa_5555, "A port wins same-word conflict");

        /* Misaligned B read completes with rvalid/error and zero data. */
        io_read_check(32'h22, 32'h0000_0000, 1'b1);

        /* CNN MMIO register bank, including read-only STATUS and pulse CONTROL. */
        mmio_write(32'h4000_0008, 32'h0000_0040);
        mmio_read_check(32'h4000_0008, 32'h0000_0040, "INPUT_ADDR register");
        mmio_read_check(32'h4000_0004, 32'h0000_0005, "STATUS read path");
        mmio_write(32'h4000_0004, 32'hffff_ffff);
        mmio_read_check(32'h4000_0004, 32'h0000_0005, "STATUS ignores writes");
        mmio_write(32'h4000_0000, 32'hffff_ffff);
        check(CONTROL === 32'h0000_0003, "CONTROL masks to start/reset pulse bits");
        @(posedge clk); #1;
        check(CONTROL === 32'h0000_0000, "CONTROL automatically clears");

        mmio_addr = 32'h4000_0024; mmio_re = 1;
        #1; check(!mmio_ready, "Unimplemented MMIO offset is not accepted");
        mmio_re = 0;

        $display("B1_MEMORY_RESULT checks=%0d", checks);
        $display("PASS: partner Datapath B1 memory subsystem");
        $finish;
    end
endmodule
