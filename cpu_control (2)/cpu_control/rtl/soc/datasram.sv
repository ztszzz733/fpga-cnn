// Shared storage with native CNN completion timing and internal B arbitration.
// CPU A retains fixed one-cycle reads. CNN and image bridge share physical B.
module datasram #(
    parameter logic [31:0] SRAM_BASE = 32'h0000_0000,
    parameter logic [31:0] SRAM_SIZE = 32'h0004_0000
) (
    input logic clk, rst_n,
    input logic [31:0] dmem_addr, dmem_wdata,
    input logic [3:0] dmem_wstrb,
    input logic dmem_re, dmem_we,
    output logic [31:0] dmem_rdata,

    input logic [31:0] mem_addr, mem_wdata,
    input logic mem_read, mem_write,
    output logic [31:0] mem_rdata,
    output logic mem_ready,
    output logic cnn_mem_fault,

    input logic io_mem_req, io_mem_we,
    input logic [31:0] io_mem_addr, io_mem_wdata,
    input logic [3:0] io_mem_be,
    output logic io_mem_gnt, io_mem_rvalid,
    output logic [31:0] io_mem_rdata,
    output logic io_mem_error
);
    localparam integer WORDS = SRAM_SIZE / 4;
    localparam integer INDEX_WIDTH = (WORDS > 1) ? $clog2(WORDS) : 1;
    logic [31:0] mem [0:WORDS-1];
    logic read_pending, read_owner_cnn, read_error;
    logic [31:0] read_data;
    logic select_cnn, select_io, request_we, request_error;
    logic [31:0] request_addr, request_wdata;
    logic [3:0] request_be;
    logic [32:0] a_offset, b_offset;
    logic a_in_range, b_in_range, conflict;
    logic [INDEX_WIDTH-1:0] a_index, b_index;
    logic cnn_accept, io_accept;

    assign a_offset = {1'b0, dmem_addr} - {1'b0, SRAM_BASE};
    assign b_offset = {1'b0, request_addr} - {1'b0, SRAM_BASE};
    assign a_in_range = a_offset < {1'b0, SRAM_SIZE};
    assign b_in_range = b_offset < {1'b0, SRAM_SIZE};
    assign a_index = a_offset >> 2;
    assign b_index = b_offset >> 2;
    assign conflict = a_in_range && b_in_range && (a_index == b_index) &&
                      (dmem_we || (dmem_re && request_we));

    // A pending read owns B until the response edge. No second request can
    // replace its owner or reissue the CNN request held until mem_ready.
    always_comb begin
        select_cnn = rst_n && !read_pending && !cnn_mem_fault &&
                     (mem_read ^ mem_write);
        select_io = rst_n && !read_pending && !select_cnn && io_mem_req;
        request_addr = select_cnn ? mem_addr : io_mem_addr;
        request_wdata = select_cnn ? mem_wdata : io_mem_wdata;
        request_we = select_cnn ? mem_write : io_mem_we;
        request_be = select_cnn ? (mem_write ? 4'hf : 4'h0) : io_mem_be;
        request_error = !b_in_range || (request_addr[1:0] != 0) || conflict ||
                        (request_we ? (request_be == 0) : (request_be != 0));
    end
    assign cnn_accept = select_cnn;
    assign io_accept = select_io;
    assign mem_rdata = (read_pending && read_owner_cnn) ? read_data : 32'b0;
    assign mem_ready = rst_n && !cnn_mem_fault &&
                       ((select_cnn && mem_write && !request_error) ||
                        (read_pending && read_owner_cnn && !read_error));
    assign io_mem_gnt = select_io;
    assign io_mem_rvalid = rst_n && read_pending && !read_owner_cnn;
    assign io_mem_rdata = io_mem_rvalid ? read_data : 32'b0;
    assign io_mem_error = (select_io && io_mem_we && request_error) ||
                          (io_mem_rvalid && read_error);

    always_ff @(posedge clk) begin : storage_access
        integer lane;
        if (!rst_n) begin
            dmem_rdata <= 32'b0;
            read_pending <= 1'b0;
            read_owner_cnn <= 1'b0;
            read_error <= 1'b0;
            read_data <= 32'b0;
            cnn_mem_fault <= 1'b0;
        end else begin
            if (dmem_re) begin
                if (a_in_range) dmem_rdata <= mem[a_index];
                else dmem_rdata <= 32'b0;
            end
            if (dmem_we && a_in_range)
                for (lane=0; lane<4; lane=lane+1)
                    if (dmem_wstrb[lane]) mem[a_index][lane*8 +: 8] <= dmem_wdata[lane*8 +: 8];

            if (read_pending) read_pending <= 1'b0;
            if (select_cnn || select_io) begin
                if (request_we) begin
                    if (!request_error)
                        for (lane=0; lane<4; lane=lane+1)
                            if (request_be[lane]) mem[b_index][lane*8 +: 8] <= request_wdata[lane*8 +: 8];
                end else begin
                    read_pending <= 1'b1;
                    read_owner_cnn <= select_cnn;
                    read_error <= request_error;
                    if (request_error) read_data <= 32'b0;
                    else read_data <= mem[b_index];
                end
            end
            // No CNN error input exists. Latch a system fault and never
            // acknowledge failed data; image transactions can still proceed.
            if ((mem_read && mem_write) ||
                (select_cnn && mem_write && request_error) ||
                (read_pending && read_owner_cnn && read_error))
                cnn_mem_fault <= 1'b1;
        end
    end
`ifndef SYNTHESIS
    initial begin
        assert (SRAM_SIZE >= 4 && SRAM_SIZE[1:0] == 0 && SRAM_BASE[1:0] == 0 &&
                ({1'b0, SRAM_BASE} + {1'b0, SRAM_SIZE} <= 33'h100000000))
            else $fatal(1, "invalid SRAM range");
    end
    always @(posedge clk) if (rst_n) begin
        assert (!(dmem_re && dmem_we)) else $error("CPU simultaneous read/write");
        assert (!dmem_we || dmem_wstrb != 0) else $error("CPU zero write strobe");
        assert (!(select_cnn && select_io)) else $error("two B owners");
    end
`endif
endmodule
