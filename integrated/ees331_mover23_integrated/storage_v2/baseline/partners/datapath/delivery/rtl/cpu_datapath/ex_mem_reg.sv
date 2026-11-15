module ex_mem_reg (
    input logic clk, rst_n,
    input logic valid_e,
    input logic [31:0] alu_result_e, write_data_e, pc4_e,
    input logic [4:0] rd_e,
    input logic regwrite_e, memread_e, memwrite_e,
    input logic [2:0] load_type_e,
    input logic [1:0] store_type_e, wb_sel_e,
    output logic valid_m,
    output logic [31:0] alu_result_m, write_data_m, pc4_m,
    output logic [4:0] rd_m,
    output logic regwrite_m, memread_m, memwrite_m,
    output logic [2:0] load_type_m,
    output logic [1:0] store_type_m, wb_sel_m
);
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            valid_m<=0; alu_result_m<=0; write_data_m<=0; pc4_m<=0; rd_m<=0;
            regwrite_m<=0; memread_m<=0; memwrite_m<=0; load_type_m<=0;
            store_type_m<=0; wb_sel_m<=0;
        end else begin
            valid_m<=valid_e; alu_result_m<=alu_result_e; write_data_m<=write_data_e;
            pc4_m<=pc4_e; rd_m<=rd_e; regwrite_m<=regwrite_e; memread_m<=memread_e;
            memwrite_m<=memwrite_e; load_type_m<=load_type_e;
            store_type_m<=store_type_e; wb_sel_m<=wb_sel_e;
        end
    end
endmodule
