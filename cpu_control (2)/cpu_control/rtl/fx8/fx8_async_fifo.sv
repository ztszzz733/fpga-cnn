// Dual-clock byte FIFO. Gray pointers cross through two marked synchronizers.
// Async read infers distributed RAM; head and valid stay stable under backpressure.
module fx8_async_fifo #(parameter integer WIDTH=8, ADDR_BITS=5)(
    input wire wr_clk, wr_rst_n, wr_valid,
    input wire [WIDTH-1:0] wr_data,
    output wire wr_ready,
    input wire rd_clk, rd_rst_n, rd_ready,
    output wire rd_valid,
    output wire [WIDTH-1:0] rd_data
);
    localparam integer P=ADDR_BITS+1;
    (* ram_style="distributed" *) logic [WIDTH-1:0] mem[0:(1<<ADDR_BITS)-1];
    logic [P-1:0] wr_bin, wr_gray, rd_bin, rd_gray;
    (* ASYNC_REG="TRUE" *) logic [P-1:0] rd_gray_meta, rd_gray_sync;
    (* ASYNC_REG="TRUE" *) logic [P-1:0] wr_gray_meta, wr_gray_sync;
    logic full, empty;
    wire push=wr_valid&&wr_ready, pop=rd_valid&&rd_ready;
    wire [P-1:0] wb_next=wr_bin+{{(P-1){1'b0}},push};
    wire [P-1:0] rb_next=rd_bin+{{(P-1){1'b0}},pop};
    wire [P-1:0] wg_next=(wb_next>>1)^wb_next;
    wire [P-1:0] rg_next=(rb_next>>1)^rb_next;
    assign wr_ready=wr_rst_n&&!full;
    assign rd_valid=rd_rst_n&&!empty;
    assign rd_data=mem[rd_bin[ADDR_BITS-1:0]];
    always_ff @(posedge wr_clk or negedge wr_rst_n) begin
        if (!wr_rst_n) begin wr_bin<=0;wr_gray<=0;full<=0;rd_gray_meta<=0;rd_gray_sync<=0;end
        else begin
            rd_gray_meta<=rd_gray;rd_gray_sync<=rd_gray_meta;
            wr_bin<=wb_next;wr_gray<=wg_next;
            full<=wg_next=={~rd_gray_sync[P-1:P-2],rd_gray_sync[P-3:0]};
        end
    end
    always_ff @(posedge wr_clk) if (push) mem[wr_bin[ADDR_BITS-1:0]]<=wr_data;
    always_ff @(posedge rd_clk or negedge rd_rst_n) begin
        if (!rd_rst_n) begin rd_bin<=0;rd_gray<=0;empty<=1;wr_gray_meta<=0;wr_gray_sync<=0;end
        else begin
            wr_gray_meta<=wr_gray;wr_gray_sync<=wr_gray_meta;
            rd_bin<=rb_next;rd_gray<=rg_next;empty<=rg_next==wr_gray_sync;
        end
    end
`ifndef SYNTHESIS
    initial assert(ADDR_BITS>=2) else $fatal(1,"FIFO depth must be at least four");
`endif
endmodule
