module mem_wb_reg (
    input logic clk, rst_n,
    input logic valid_m,
    input logic [31:0] read_data_m, alu_result_m, pc4_m,
    input logic [4:0] rd_m,
    input logic regwrite_m,
    input logic [1:0] wb_sel_m,
    output logic valid_w,
    output logic [31:0] read_data_w, alu_result_w, pc4_w,
    output logic [4:0] rd_w,
    output logic regwrite_w,
    output logic [1:0] wb_sel_w
);
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            valid_w<=0; read_data_w<=0; alu_result_w<=0; pc4_w<=0;
            rd_w<=0; regwrite_w<=0; wb_sel_w<=0;
        end else begin
            valid_w<=valid_m; read_data_w<=read_data_m; alu_result_w<=alu_result_m;
            pc4_w<=pc4_m; rd_w<=rd_m; regwrite_w<=regwrite_m; wb_sel_w<=wb_sel_m;
        end
    end
endmodule
