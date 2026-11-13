// Frequency-preserving clock connection and asynchronous-assert/sync-release reset.
// Add a board-specific clock buffer/PLL constraint when mapping to a device.
module clock_unit (
    input logic sys_clk, rst_n_in,
    output wire clk,
    output wire rst_n
);
    (* ASYNC_REG = "TRUE" *) logic [2:0] release_q;
    assign clk = sys_clk;
    assign rst_n = release_q[2];
    always_ff @(posedge sys_clk or negedge rst_n_in) begin
        if (!rst_n_in) release_q <= 3'b0;
        else release_q <= {release_q[1:0], 1'b1};
    end
endmodule
