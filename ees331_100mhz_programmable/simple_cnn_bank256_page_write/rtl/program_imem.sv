// Independent write port for the PS loader. CPU fetch remains synchronous.
module program_imem(
    input  logic clk, rst_n,
    input  logic [31:0] imem_addr,
    input  logic imem_re,
    output wire [31:0] imem_rdata,
    input  logic load_we,
    input  logic [10:0] load_word,
    input  logic [31:0] load_data
);
    (* ram_style = "block" *) logic [31:0] mem [0:2047];
    logic [31:0] read_data;
    logic fetch_valid;

    always_ff @(posedge clk) begin
        if (load_we) mem[load_word] <= load_data;
        if (imem_re) read_data <= mem[imem_addr[12:2]];
        if (!rst_n) fetch_valid <= 0;
        else if (imem_re)
            fetch_valid <= imem_addr[31:13] == 0 && imem_addr[1:0] == 0;
    end
    assign imem_rdata = fetch_valid ? read_data : 32'h00000013;
endmodule
