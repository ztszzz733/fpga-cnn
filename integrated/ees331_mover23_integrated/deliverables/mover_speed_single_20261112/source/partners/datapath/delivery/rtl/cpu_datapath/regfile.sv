module regfile (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [4:0]  rs1,
    input  logic [4:0]  rs2,
    output logic [31:0] rd1,
    output logic [31:0] rd2,
    input  logic        we,
    input  logic [4:0]  waddr,
    input  logic [31:0] wdata
);
    logic [31:0] regs [0:31];
    integer i;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            for (i = 0; i < 32; i = i + 1) regs[i] <= 32'b0;
        end else if (we && (waddr != 5'd0)) begin
            regs[waddr] <= wdata;
        end
    end

    always_comb begin
        if (rs1 == 5'd0) rd1 = 32'b0;
        else if (we && (waddr == rs1) && (waddr != 5'd0)) rd1 = wdata;
        else rd1 = regs[rs1];

        if (rs2 == 5'd0) rd2 = 32'b0;
        else if (we && (waddr == rs2) && (waddr != 5'd0)) rd2 = wdata;
        else rd2 = regs[rs2];
    end
endmodule
