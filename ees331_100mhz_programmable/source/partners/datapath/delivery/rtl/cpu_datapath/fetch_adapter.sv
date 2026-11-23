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

        fetch_valid = rst_n && !flush && (buffer_valid_q || req_valid_q);
        fetch_instr = buffer_valid_q ? buffer_instr_q : imem_rdata;
        fetch_pc = buffer_valid_q ? buffer_pc_q : req_pc_q;
        fetch_pc4 = buffer_valid_q ? buffer_pc4_q : req_pc4_q;
    end

    always_ff @(posedge clk) begin
        req_valid_q <= imem_re;
        if (!rst_n || flush) begin
            buffer_valid_q <= 1'b0;
        end else if (buffer_valid_q) begin
            if (if_id_en) buffer_valid_q <= 1'b0;
        end else if (req_valid_q && !if_id_en) begin
            buffer_valid_q <= 1'b1;
        end

        // Invalid payload is ignored. Keep flush and the fetch enable off the
        // wide PC/instruction registers and preserve stalls with buffer_valid_q.
        req_pc_q <= imem_addr;
        req_pc4_q <= imem_addr + 32'd4;
        if (!buffer_valid_q) begin
            buffer_instr_q <= imem_rdata;
            buffer_pc_q <= req_pc_q;
            buffer_pc4_q <= req_pc4_q;
        end
    end
endmodule
