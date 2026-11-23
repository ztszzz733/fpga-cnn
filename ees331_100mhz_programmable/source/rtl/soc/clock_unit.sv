// FCLK is forwarded directly; asynchronous reset asserts at once and
// deasserts through synchronizers. Replicate the final fabric driver.
module clock_unit (
    input logic sys_clk, rst_n_in,
    output wire clk,
    output wire rst_n
);
    (* ASYNC_REG = "TRUE" *) logic [2:0] release_q;
    (* MAX_FANOUT = 64 *) logic fabric_release;
    assign clk = sys_clk;
    assign rst_n = fabric_release;

    always_ff @(posedge sys_clk or negedge rst_n_in) begin
        if (!rst_n_in)
            release_q <= 3'b0;
        else
            release_q <= {release_q[1:0], 1'b1};
    end
    always_ff @(posedge sys_clk or negedge rst_n_in) begin
        if (!rst_n_in)
            fabric_release <= 0;
        else
            fabric_release <= release_q[2];
    end
endmodule
