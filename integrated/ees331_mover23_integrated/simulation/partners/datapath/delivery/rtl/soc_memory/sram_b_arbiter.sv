module sram_b_arbiter (
    input  logic        clk,
    input  logic        rst_n,

    input  logic        io_mem_req,
    input  logic        io_mem_we,
    input  logic [31:0] io_mem_addr,
    input  logic [31:0] io_mem_wdata,
    input  logic [3:0]  io_mem_be,
    output logic        io_mem_gnt,
    output logic        io_mem_rvalid,
    output logic [31:0] io_mem_rdata,
    output logic        io_mem_error,

    input  logic        cnn_mem_req,
    input  logic        cnn_mem_we,
    input  logic [31:0] cnn_mem_addr,
    input  logic [31:0] cnn_mem_wdata,
    input  logic [3:0]  cnn_mem_be,
    output logic        cnn_mem_gnt,
    output logic        cnn_mem_rvalid,
    output logic [31:0] cnn_mem_rdata,
    output logic        cnn_mem_error,

    output logic        b_req,
    output logic        b_we,
    output logic [31:0] b_addr,
    output logic [31:0] b_wdata,
    output logic [3:0]  b_be,
    input  logic        b_gnt,
    input  logic        b_rvalid,
    input  logic [31:0] b_rdata,
    input  logic        b_error
);
    localparam logic OWNER_IO = 1'b0;
    localparam logic OWNER_CNN = 1'b1;

    logic read_pending_q, read_owner_q;
    logic select_io, select_cnn;

    always_comb begin
        select_io = 1'b0;
        select_cnn = 1'b0;
        if (rst_n && !read_pending_q) begin
            if (cnn_mem_req) select_cnn = 1'b1;
            else if (io_mem_req) select_io = 1'b1;
        end

        b_req = 1'b0;
        b_we = 1'b0;
        b_addr = 32'b0;
        b_wdata = 32'b0;
        b_be = 4'b0;
        if (select_cnn) begin
            b_req = cnn_mem_req;
            b_we = cnn_mem_we;
            b_addr = cnn_mem_addr;
            b_wdata = cnn_mem_wdata;
            b_be = cnn_mem_be;
        end else if (select_io) begin
            b_req = io_mem_req;
            b_we = io_mem_we;
            b_addr = io_mem_addr;
            b_wdata = io_mem_wdata;
            b_be = io_mem_be;
        end

        io_mem_gnt = 1'b0;
        io_mem_rvalid = 1'b0;
        io_mem_rdata = 32'b0;
        io_mem_error = 1'b0;
        cnn_mem_gnt = 1'b0;
        cnn_mem_rvalid = 1'b0;
        cnn_mem_rdata = 32'b0;
        cnn_mem_error = 1'b0;

        if (select_cnn) begin
            cnn_mem_gnt = b_gnt;
            if (b_gnt && b_we) cnn_mem_error = b_error;
        end else if (select_io) begin
            io_mem_gnt = b_gnt;
            if (b_gnt && b_we) io_mem_error = b_error;
        end

        if (read_pending_q && b_rvalid) begin
            if (read_owner_q == OWNER_CNN) begin
                cnn_mem_rvalid = 1'b1;
                cnn_mem_rdata = b_rdata;
                cnn_mem_error = b_error;
            end else begin
                io_mem_rvalid = 1'b1;
                io_mem_rdata = b_rdata;
                io_mem_error = b_error;
            end
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            read_pending_q <= 1'b0;
            read_owner_q <= OWNER_IO;
        end else begin
            if (read_pending_q && b_rvalid) read_pending_q <= 1'b0;
            else if (b_req && b_gnt && !b_we) begin
                read_pending_q <= 1'b1;
                read_owner_q <= select_cnn ? OWNER_CNN : OWNER_IO;
            end
        end
    end

`ifndef SYNTHESIS
    always_ff @(posedge clk) begin
        if (rst_n) begin
            assert (!(io_mem_gnt && cnn_mem_gnt));
            assert (!(io_mem_rvalid && cnn_mem_rvalid));
            assert (!b_rvalid || read_pending_q)
                else $error("B port returned data without a pending owner");
        end
    end
`endif
endmodule
