module fetch_adapter (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [31:0] request_pc,
    input  logic        pc_en,
    input  logic        if_id_en,
    input  logic        flush,
    output logic [31:0] imem_addr,
    output logic        imem_re,
    input  logic [31:0] imem_rdata,
    output logic        fetch_valid,
    output logic [31:0] fetch_instr,
    output logic [31:0] fetch_pc,
    output logic [31:0] fetch_pc4
);
    logic        req_valid_q;
    logic [31:0] req_pc_q;
    logic [31:0] req_pc4_q;
    logic        buffer_valid_q;
    logic [31:0] buffer_instr_q;
    logic [31:0] buffer_pc_q;
    logic [31:0] buffer_pc4_q;

    always_comb begin
        imem_addr = request_pc;
        imem_re = rst_n && !flush && pc_en && if_id_en;

        fetch_valid = 1'b0;
        fetch_instr = 32'b0;
        fetch_pc = 32'b0;
        fetch_pc4 = 32'b0;
        if (rst_n && !flush) begin
            if (buffer_valid_q) begin
                fetch_valid = 1'b1;
                fetch_instr = buffer_instr_q;
                fetch_pc = buffer_pc_q;
                fetch_pc4 = buffer_pc4_q;
            end else if (req_valid_q) begin
                fetch_valid = 1'b1;
                fetch_instr = imem_rdata;
                fetch_pc = req_pc_q;
                fetch_pc4 = req_pc4_q;
            end
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            req_valid_q <= 1'b0;
            req_pc_q <= 32'b0;
            req_pc4_q <= 32'b0;
            buffer_valid_q <= 1'b0;
            buffer_instr_q <= 32'b0;
            buffer_pc_q <= 32'b0;
            buffer_pc4_q <= 32'b0;
        end else if (flush) begin
            req_valid_q <= 1'b0;
            req_pc_q <= 32'b0;
            req_pc4_q <= 32'b0;
            buffer_valid_q <= 1'b0;
            buffer_instr_q <= 32'b0;
            buffer_pc_q <= 32'b0;
            buffer_pc4_q <= 32'b0;
        end else begin
            req_valid_q <= imem_re;
            if (imem_re) begin
                req_pc_q <= imem_addr;
                req_pc4_q <= imem_addr + 32'd4;
            end else begin
                req_pc_q <= 32'b0;
                req_pc4_q <= 32'b0;
            end

            if (buffer_valid_q) begin
                if (if_id_en) begin
                    buffer_valid_q <= 1'b0;
                    buffer_instr_q <= 32'b0;
                    buffer_pc_q <= 32'b0;
                    buffer_pc4_q <= 32'b0;
                end
            end else if (req_valid_q && !if_id_en) begin
                buffer_valid_q <= 1'b1;
                buffer_instr_q <= imem_rdata;
                buffer_pc_q <= req_pc_q;
                buffer_pc4_q <= req_pc4_q;
            end
        end
    end
endmodule
