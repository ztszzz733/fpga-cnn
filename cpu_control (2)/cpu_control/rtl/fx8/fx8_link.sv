// EES-331 supplies a continuous forwarded clock, sys_clk/4 (25 MHz at 100 MHz).
// Peer and FPGA transfer bytes on rising link-clock edges when valid && ready.
// Both FIFO domains are flushed on a sticky loader fault; reset is required.
module fx8_link (
    input wire clk,rst_n,fault,
    output wire fx8_clk,fx8_reset_n,
    input wire [7:0] fx8_rx_data,
    input wire fx8_rx_valid,fx8_tx_ready,
    output wire fx8_rx_ready,fx8_tx_valid,
    output wire [7:0] fx8_tx_data,
    output wire [7:0] rx_data,
    output wire rx_valid,
    input wire rx_ready,
    input wire [7:0] tx_data,
    input wire tx_valid,
    output wire tx_ready
);
    logic [1:0] divider;
    wire link_clk;
    always_ff @(posedge clk or negedge rst_n)
        if (!rst_n) divider<=0; else divider<=divider+1'b1;
`ifdef SYNTHESIS
    BUFG u_link_bufg(.I(divider[1]),.O(link_clk));
    ODDR #(.DDR_CLK_EDGE("SAME_EDGE"),.INIT(1'b0),.SRTYPE("ASYNC")) u_forward_clock
        (.C(link_clk),.CE(1'b1),.D1(1'b1),.D2(1'b0),.R(!rst_n),.S(1'b0),.Q(fx8_clk));
`else
    assign link_clk=divider[1];
    assign fx8_clk=link_clk;
`endif
    wire transport_reset_n=rst_n&&!fault;
    (* ASYNC_REG="TRUE" *) logic [2:0] sys_reset_pipe,link_reset_pipe;
    assign fx8_reset_n=link_reset_pipe[2];
    always_ff @(posedge clk or negedge transport_reset_n)
        if (!transport_reset_n) sys_reset_pipe<=0;
        else sys_reset_pipe<={sys_reset_pipe[1:0],1'b1};
    always_ff @(posedge link_clk or negedge transport_reset_n)
        if (!transport_reset_n) link_reset_pipe<=0;
        else link_reset_pipe<={link_reset_pipe[1:0],1'b1};
    fx8_async_fifo #(.ADDR_BITS(9)) u_rx_fifo (
        .wr_clk(link_clk),.wr_rst_n(link_reset_pipe[2]),.wr_valid(fx8_rx_valid),.wr_data(fx8_rx_data),.wr_ready(fx8_rx_ready),
        .rd_clk(clk),.rd_rst_n(sys_reset_pipe[2]),.rd_valid(rx_valid),.rd_data(rx_data),.rd_ready(rx_ready));
    fx8_async_fifo #(.ADDR_BITS(5)) u_tx_fifo (
        .wr_clk(clk),.wr_rst_n(sys_reset_pipe[2]),.wr_valid(tx_valid),.wr_data(tx_data),.wr_ready(tx_ready),
        .rd_clk(link_clk),.rd_rst_n(link_reset_pipe[2]),.rd_valid(fx8_tx_valid),.rd_data(fx8_tx_data),.rd_ready(fx8_tx_ready));
endmodule
