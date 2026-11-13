// TEST ONLY: nine-register, zero-wait behavioral stand-in. This is not Z RTL.
module cnn_mmio_stub #(
    parameter logic [31:0] BASE = 32'h4000_0000
) (
    input logic clk,
    input logic rst_n,
    input logic [31:0] addr,
    input logic [31:0] wdata,
    input logic re,
    input logic we,
    output logic [31:0] rdata,
    output logic ready
);
    logic [31:0] regs [0:8];
    integer write_count;
    logic legal;
    logic [3:0] index;

    always_comb begin
        legal = (addr >= BASE) && (addr <= BASE + 32'h20) &&
                (addr[1:0] == 2'b00);
        index = addr[5:2];
        ready = (re || we) && legal;
        rdata = 32'b0;
        if (re && legal) rdata = regs[index];
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            write_count <= 0;
            regs[0] <= 0; regs[1] <= 0; regs[2] <= 0;
            regs[3] <= 0; regs[4] <= 0; regs[5] <= 0;
            regs[6] <= 0; regs[7] <= 0; regs[8] <= 0;
        end else if (we && legal) begin
            regs[index] <= wdata;
            write_count <= write_count + 1;
        end
    end
endmodule
