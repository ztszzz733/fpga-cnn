module lsu (
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] addr,
    /* verilator lint_on UNUSEDSIGNAL */
    input  logic [31:0] store_data,
    input  logic [31:0] read_word,
    input  logic [2:0]  load_type,
    input  logic [1:0]  store_type,
    output logic [31:0] load_data,
    output logic        load_aligned,
    output logic        load_type_valid,
    output logic [31:0] store_wdata,
    output logic [3:0]  store_wstrb,
    output logic        store_aligned,
    output logic        store_type_valid
);
    import cpu_control_pkg::*;
    logic [7:0] selected_byte;
    logic [15:0] selected_half;

    always_comb begin
        case (addr[1:0])
            2'b00: selected_byte = read_word[7:0];
            2'b01: selected_byte = read_word[15:8];
            2'b10: selected_byte = read_word[23:16];
            2'b11: selected_byte = read_word[31:24];
            default: selected_byte = 8'b0;
        endcase
        selected_half = addr[1] ? read_word[31:16] : read_word[15:0];

        load_data = 32'b0;
        load_aligned = 1'b0;
        load_type_valid = 1'b1;
        case (load_type)
            LOAD_LB: begin
                load_aligned = 1'b1;
                load_data = {{24{selected_byte[7]}}, selected_byte};
            end
            LOAD_LH: begin
                load_aligned = !addr[0];
                if (!addr[0]) load_data = {{16{selected_half[15]}}, selected_half};
            end
            LOAD_LW: begin
                load_aligned = (addr[1:0] == 2'b00);
                if (addr[1:0] == 2'b00) load_data = read_word;
            end
            LOAD_LBU: begin
                load_aligned = 1'b1;
                load_data = {24'b0, selected_byte};
            end
            LOAD_LHU: begin
                load_aligned = !addr[0];
                if (!addr[0]) load_data = {16'b0, selected_half};
            end
            default: begin
                load_type_valid = 1'b0;
                load_aligned = 1'b0;
                load_data = 32'b0;
            end
        endcase

        store_wdata = 32'b0;
        store_wstrb = 4'b0000;
        store_aligned = 1'b0;
        store_type_valid = 1'b1;
        case (store_type)
            STORE_SB: begin
                store_aligned = 1'b1;
                store_wstrb = 4'b0001 << addr[1:0];
                store_wdata = {24'b0, store_data[7:0]} << (addr[1:0] * 8);
            end
            STORE_SH: begin
                store_aligned = !addr[0];
                if (!addr[0]) begin
                    store_wstrb = addr[1] ? 4'b1100 : 4'b0011;
                    store_wdata = addr[1] ? {store_data[15:0], 16'b0}
                                                : {16'b0, store_data[15:0]};
                end
            end
            STORE_SW: begin
                store_aligned = (addr[1:0] == 2'b00);
                if (addr[1:0] == 2'b00) begin
                    store_wstrb = 4'b1111;
                    store_wdata = store_data;
                end
            end
            default: begin
                store_type_valid = 1'b0;
                store_aligned = 1'b0;
                store_wstrb = 4'b0000;
                store_wdata = 32'b0;
            end
        endcase
    end
endmodule
