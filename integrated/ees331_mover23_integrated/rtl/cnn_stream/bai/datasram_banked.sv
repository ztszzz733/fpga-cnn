`timescale 1ns/1ps

// Balanced lowest-index request selector.  Carrying the payload through the
// same tree avoids a second wide owner-indexed mux after arbitration.
module datasram_payload_tree #(
    parameter integer REQUESTS = 2,
    parameter integer PAYLOAD_WIDTH = 1
)(
    input  wire [REQUESTS-1:0]               req,
    input  wire [REQUESTS*PAYLOAD_WIDTH-1:0] payload,
    output wire                                valid,
    output wire [PAYLOAD_WIDTH-1:0]            selected_payload
);
    generate
        if (REQUESTS == 1) begin : gen_leaf
            assign valid = req[0];
            assign selected_payload = payload[0 +: PAYLOAD_WIDTH];
        end else begin : gen_branch
            localparam integer LEFT_REQUESTS = REQUESTS / 2;
            localparam integer RIGHT_REQUESTS = REQUESTS - LEFT_REQUESTS;
            wire left_valid, right_valid;
            wire [PAYLOAD_WIDTH-1:0] left_payload, right_payload;

            datasram_payload_tree #(
                .REQUESTS(LEFT_REQUESTS), .PAYLOAD_WIDTH(PAYLOAD_WIDTH)
            ) u_left (
                .req(req[LEFT_REQUESTS-1:0]),
                .payload(payload[0 +: LEFT_REQUESTS*PAYLOAD_WIDTH]),
                .valid(left_valid), .selected_payload(left_payload)
            );
            datasram_payload_tree #(
                .REQUESTS(RIGHT_REQUESTS), .PAYLOAD_WIDTH(PAYLOAD_WIDTH)
            ) u_right (
                .req(req[LEFT_REQUESTS +: RIGHT_REQUESTS]),
                .payload(payload[LEFT_REQUESTS*PAYLOAD_WIDTH +: RIGHT_REQUESTS*PAYLOAD_WIDTH]),
                .valid(right_valid), .selected_payload(right_payload)
            );

            assign valid = left_valid || right_valid;
            assign selected_payload = left_valid ? left_payload : right_payload;
        end
    endgenerate
endmodule

// Inference-friendly true dual-port, byte-write SRAM bank.  Both ports are
// synchronous and read-first.  The parent prevents same-word A/B collisions.
module datasram_tdp_bank #(
    parameter integer DEPTH = 1024,
    parameter integer ADDR_WIDTH = (DEPTH <= 1) ? 1 : $clog2(DEPTH)
)(
    input  wire                  clk,
    input  wire                  a_en,
    input  wire [ADDR_WIDTH-1:0] a_addr,
    input  wire [31:0]           a_wdata,
    input  wire [3:0]            a_be,
    output logic [31:0]          a_rdata,
    input  wire                  b_en,
    input  wire [ADDR_WIDTH-1:0] b_addr,
    input  wire [31:0]           b_wdata,
    input  wire [3:0]            b_be,
    output logic [31:0]          b_rdata
);
    (* ram_style = "block", rw_addr_collision = "yes" *)
    logic [31:0] mem [0:DEPTH-1];

    always @(posedge clk) begin : port_a_storage
        integer lane;
        if (a_en) begin
            a_rdata <= mem[a_addr];
            for (lane = 0; lane < 4; lane = lane + 1)
                if (a_be[lane]) mem[a_addr][lane*8 +: 8] <= a_wdata[lane*8 +: 8];
        end
    end

    always @(posedge clk) begin : port_b_storage
        integer lane;
        if (b_en) begin
            b_rdata <= mem[b_addr];
            for (lane = 0; lane < 4; lane = lane + 1)
                if (b_be[lane]) mem[b_addr][lane*8 +: 8] <= b_wdata[lane*8 +: 8];
        end
    end

`ifndef SYNTHESIS
    always @(posedge clk)
        if (a_en && b_en && a_addr == b_addr)
            $fatal(1, "same-word dual-port SRAM collision");
`endif
endmodule

// Interleaved true-dual-port SRAM banks.  CPU uses port A with fixed one-cycle
// reads.  CNN clients and image IO share port B through per-bank round-robin
// arbitration implemented by balanced priority trees.  CPU and port B may use
// the same bank concurrently when their word addresses differ; CPU wins an
// exact-word collision.  Responses remain one cycle after acceptance.
module datasram_banked #(
    parameter logic [31:0] SRAM_BASE = 0,
    parameter logic [31:0] SRAM_SIZE = 32'h40000,
    parameter integer BANKS = 4,
    parameter integer CLIENTS = 11
)(
    input logic clk, rst_n,
    input logic [31:0] dmem_addr, dmem_wdata,
    input logic [3:0] dmem_wstrb,
    input logic dmem_re, dmem_we,
    output logic [31:0] dmem_rdata,
    input wire [CLIENTS-1:0] cnn_valid, cnn_write, cnn_byte,
    input wire [CLIENTS*32-1:0] cnn_addr, cnn_wdata,
    output logic [CLIENTS-1:0] cnn_ready, cnn_response,
    output logic [CLIENTS*32-1:0] cnn_rdata,
    input wire cnn_cancel,
    output logic cnn_mem_fault,
    input logic io_mem_req, io_mem_we,
    input logic [31:0] io_mem_addr, io_mem_wdata,
    input logic [3:0] io_mem_be,
    output logic io_mem_gnt, io_mem_rvalid,
    output logic [31:0] io_mem_rdata,
    output logic io_mem_error
);
    localparam integer WORDS = SRAM_SIZE / 4;
    localparam integer BANK_WORDS = WORDS / BANKS;
    localparam integer BANK_SHIFT = (BANKS <= 1) ? 0 : $clog2(BANKS);
    localparam integer BANK_WIDTH = (BANKS <= 1) ? 1 : $clog2(BANKS);
    localparam integer ROW_WIDTH = (BANK_WORDS <= 1) ? 1 : $clog2(BANK_WORDS);
    localparam integer REQUESTERS = CLIENTS + 1;
    localparam integer OWNER_WIDTH = (REQUESTERS <= 1) ? 1 : $clog2(REQUESTERS);
    localparam integer PAYLOAD_OWNER = 0;
    localparam integer PAYLOAD_ROW = PAYLOAD_OWNER + OWNER_WIDTH;
    localparam integer PAYLOAD_WDATA = PAYLOAD_ROW + ROW_WIDTH;
    localparam integer PAYLOAD_BE = PAYLOAD_WDATA + 32;
    localparam integer PAYLOAD_IS_IO = PAYLOAD_BE + 4;
    localparam integer PAYLOAD_WRITE = PAYLOAD_IS_IO + 1;
    localparam integer PAYLOAD_BYTE = PAYLOAD_WRITE + 1;
    localparam integer PAYLOAD_ERROR = PAYLOAD_BYTE + 1;
    localparam integer PAYLOAD_LANE = PAYLOAD_ERROR + 1;
    localparam integer PAYLOAD_WIDTH = PAYLOAD_LANE + 2;

    function automatic [BANK_WIDTH-1:0] offset_bank(input logic [32:0] offset);
        offset_bank = BANK_WIDTH'((offset >> 2) & (BANKS - 1));
    endfunction
    function automatic [ROW_WIDTH-1:0] offset_row(input logic [32:0] offset);
        offset_row = ROW_WIDTH'(offset >> (2 + BANK_SHIFT));
    endfunction

    wire [32:0] cpu_offset = {1'b0, dmem_addr} - {1'b0, SRAM_BASE};
    wire cpu_valid = cpu_offset < {1'b0, SRAM_SIZE};
    wire cpu_access = (dmem_re || dmem_we) && cpu_valid;
    wire [BANK_WIDTH-1:0] cpu_bank = offset_bank(cpu_offset);
    wire [ROW_WIDTH-1:0] cpu_row = offset_row(cpu_offset);
    wire [30:0] cpu_word = cpu_offset[32:2];

    wire [32:0] io_offset = {1'b0, io_mem_addr} - {1'b0, SRAM_BASE};
    wire io_bad = io_offset >= {1'b0, SRAM_SIZE} || io_mem_addr[1:0] != 0 ||
        (io_mem_we ? io_mem_be == 0 : io_mem_be != 0);
    wire [BANK_WIDTH-1:0] io_bank = offset_bank(io_offset);
    wire [ROW_WIDTH-1:0] io_row = offset_row(io_offset);
    wire [30:0] io_word = io_offset[32:2];

    logic [CLIENTS-1:0] bad;
    logic [REQUESTERS-1:0] request_mask [0:BANKS-1];
    logic [REQUESTERS*PAYLOAD_WIDTH-1:0] request_payloads [0:BANKS-1];
    logic [REQUESTERS-1:0] upper_mask [0:BANKS-1];
    logic [OWNER_WIDTH-1:0] next_owner [0:BANKS-1];
    wire [PAYLOAD_WIDTH-1:0] upper_payload [0:BANKS-1];
    wire [PAYLOAD_WIDTH-1:0] wrap_payload [0:BANKS-1];
    wire [PAYLOAD_WIDTH-1:0] selected_payload [0:BANKS-1];
    wire [OWNER_WIDTH-1:0] selected_owner [0:BANKS-1];
    wire upper_valid [0:BANKS-1], wrap_valid [0:BANKS-1];
    wire selected_valid [0:BANKS-1];
    wire [ROW_WIDTH-1:0] selected_row [0:BANKS-1];
    wire [31:0] selected_wdata [0:BANKS-1];
    wire [3:0] selected_be [0:BANKS-1];
    wire selected_is_io [0:BANKS-1], selected_write [0:BANKS-1];
    wire selected_byte [0:BANKS-1], selected_error [0:BANKS-1];
    wire [1:0] selected_lane [0:BANKS-1];
    wire cnn_requests_enabled = !cnn_mem_fault && !cnn_cancel;

    logic bank_a_en [0:BANKS-1], bank_b_en [0:BANKS-1];
    logic [ROW_WIDTH-1:0] bank_a_addr [0:BANKS-1], bank_b_addr [0:BANKS-1];
    logic [31:0] bank_a_wdata [0:BANKS-1], bank_b_wdata [0:BANKS-1];
    logic [3:0] bank_a_be [0:BANKS-1], bank_b_be [0:BANKS-1];
    wire [31:0] bank_a_rdata [0:BANKS-1], bank_b_rdata [0:BANKS-1];

    logic response_valid [0:BANKS-1], response_is_io [0:BANKS-1];
    logic response_write [0:BANKS-1], response_byte [0:BANKS-1];
    logic response_error [0:BANKS-1];
    logic [1:0] response_lane [0:BANKS-1];
    logic [OWNER_WIDTH-1:0] response_owner [0:BANKS-1];

    logic cpu_read_pending, cpu_read_ok;
    logic [BANK_WIDTH-1:0] cpu_read_bank;
    logic [31:0] dmem_rdata_hold;

    generate
        for (genvar bank = 0; bank < BANKS; bank = bank + 1) begin : gen_banks
            // Select both round-robin candidates together with their payload.
            // This removes the wide owner-indexed mux from the BRAM input path.
            datasram_payload_tree #(
                .REQUESTS(REQUESTERS), .PAYLOAD_WIDTH(PAYLOAD_WIDTH)
            ) u_upper_tree (
                .req(upper_mask[bank]), .payload(request_payloads[bank]),
                .valid(upper_valid[bank]), .selected_payload(upper_payload[bank])
            );
            datasram_payload_tree #(
                .REQUESTS(REQUESTERS), .PAYLOAD_WIDTH(PAYLOAD_WIDTH)
            ) u_wrap_tree (
                .req(request_mask[bank]), .payload(request_payloads[bank]),
                .valid(wrap_valid[bank]), .selected_payload(wrap_payload[bank])
            );
            assign selected_valid[bank] = cnn_requests_enabled ?
                (upper_valid[bank] || wrap_valid[bank]) : request_mask[bank][CLIENTS];
            assign selected_payload[bank] = cnn_requests_enabled ?
                (upper_valid[bank] ? upper_payload[bank] : wrap_payload[bank]) :
                request_payloads[bank][CLIENTS*PAYLOAD_WIDTH +: PAYLOAD_WIDTH];
            assign selected_owner[bank] =
                selected_payload[bank][PAYLOAD_OWNER +: OWNER_WIDTH];
            assign selected_row[bank] = selected_payload[bank][PAYLOAD_ROW +: ROW_WIDTH];
            assign selected_wdata[bank] = selected_payload[bank][PAYLOAD_WDATA +: 32];
            assign selected_be[bank] = selected_payload[bank][PAYLOAD_BE +: 4];
            assign selected_is_io[bank] = selected_payload[bank][PAYLOAD_IS_IO];
            assign selected_write[bank] = selected_payload[bank][PAYLOAD_WRITE];
            assign selected_byte[bank] = selected_payload[bank][PAYLOAD_BYTE];
            assign selected_error[bank] = selected_payload[bank][PAYLOAD_ERROR];
            assign selected_lane[bank] = selected_payload[bank][PAYLOAD_LANE +: 2];

            datasram_tdp_bank #(
                .DEPTH(BANK_WORDS), .ADDR_WIDTH(ROW_WIDTH)
            ) u_bank (
                .clk(clk),
                .a_en(bank_a_en[bank]), .a_addr(bank_a_addr[bank]),
                .a_wdata(bank_a_wdata[bank]), .a_be(bank_a_be[bank]),
                .a_rdata(bank_a_rdata[bank]),
                .b_en(bank_b_en[bank]), .b_addr(bank_b_addr[bank]),
                .b_wdata(bank_b_wdata[bank]), .b_be(bank_b_be[bank]),
                .b_rdata(bank_b_rdata[bank])
            );
        end
    endgenerate

    always_comb begin : request_decode
        logic [32:0] client_offset;
        logic [BANK_WIDTH-1:0] client_bank;
        logic [BANK_WIDTH-1:0] io_target_bank;
        logic [30:0] client_word;
        integer bank, client, requester;

        bad = '0;
        io_target_bank = '0;
        for (bank = 0; bank < BANKS; bank = bank + 1) begin
            request_mask[bank] = '0;
            request_payloads[bank] = '0;
            upper_mask[bank] = '0;
        end

        for (client = 0; client < CLIENTS; client = client + 1) begin
            client_offset = {1'b0, cnn_addr[client*32 +: 32]} - {1'b0, SRAM_BASE};
            bad[client] = client_offset >= {1'b0, SRAM_SIZE} ||
                (!cnn_byte[client] && cnn_addr[client*32 +: 2] != 0);
            client_bank = offset_bank(client_offset);
            client_word = client_offset[32:2];
            if (rst_n && cnn_valid[client] && !bad[client] &&
                !(cpu_access && client_word == cpu_word)) begin
                request_mask[client_bank][client] = 1'b1;
                request_payloads[client_bank][client*PAYLOAD_WIDTH + PAYLOAD_OWNER +: OWNER_WIDTH] =
                    OWNER_WIDTH'(client);
                request_payloads[client_bank][client*PAYLOAD_WIDTH + PAYLOAD_ROW +: ROW_WIDTH] =
                    offset_row(client_offset);
                request_payloads[client_bank][client*PAYLOAD_WIDTH + PAYLOAD_WDATA +: 32] =
                    cnn_byte[client] ? {4{cnn_wdata[client*32 +: 8]}} :
                    cnn_wdata[client*32 +: 32];
                request_payloads[client_bank][client*PAYLOAD_WIDTH + PAYLOAD_BE +: 4] =
                    cnn_write[client] ?
                        (cnn_byte[client] ? (4'b0001 << cnn_addr[client*32 +: 2]) : 4'b1111) :
                        4'b0000;
                request_payloads[client_bank][client*PAYLOAD_WIDTH + PAYLOAD_IS_IO] = 1'b0;
                request_payloads[client_bank][client*PAYLOAD_WIDTH + PAYLOAD_WRITE] = cnn_write[client];
                request_payloads[client_bank][client*PAYLOAD_WIDTH + PAYLOAD_BYTE] = cnn_byte[client];
                request_payloads[client_bank][client*PAYLOAD_WIDTH + PAYLOAD_ERROR] = 1'b0;
                request_payloads[client_bank][client*PAYLOAD_WIDTH + PAYLOAD_LANE +: 2] =
                    cnn_addr[client*32 +: 2];
            end
        end

        if (rst_n && io_mem_req) begin
            io_target_bank = io_bad ? '0 : io_bank;
            if (io_bad || !(cpu_access && io_word == cpu_word)) begin
                request_mask[io_target_bank][CLIENTS] = 1'b1;
                request_payloads[io_target_bank][CLIENTS*PAYLOAD_WIDTH + PAYLOAD_OWNER +: OWNER_WIDTH] =
                    OWNER_WIDTH'(CLIENTS);
                request_payloads[io_target_bank][CLIENTS*PAYLOAD_WIDTH + PAYLOAD_ROW +: ROW_WIDTH] = io_row;
                request_payloads[io_target_bank][CLIENTS*PAYLOAD_WIDTH + PAYLOAD_WDATA +: 32] = io_mem_wdata;
                request_payloads[io_target_bank][CLIENTS*PAYLOAD_WIDTH + PAYLOAD_BE +: 4] =
                    io_mem_we ? io_mem_be : 4'b0000;
                request_payloads[io_target_bank][CLIENTS*PAYLOAD_WIDTH + PAYLOAD_IS_IO] = 1'b1;
                request_payloads[io_target_bank][CLIENTS*PAYLOAD_WIDTH + PAYLOAD_WRITE] = io_mem_we;
                request_payloads[io_target_bank][CLIENTS*PAYLOAD_WIDTH + PAYLOAD_BYTE] = 1'b0;
                request_payloads[io_target_bank][CLIENTS*PAYLOAD_WIDTH + PAYLOAD_ERROR] = io_bad;
                request_payloads[io_target_bank][CLIENTS*PAYLOAD_WIDTH + PAYLOAD_LANE +: 2] = 2'b00;
            end
        end

        for (bank = 0; bank < BANKS; bank = bank + 1)
            for (requester = 0; requester < REQUESTERS; requester = requester + 1)
                upper_mask[bank][requester] = request_mask[bank][requester] &&
                    requester >= next_owner[bank];

    end

    always_comb begin : port_control
        integer bank, owner;

        owner = 0;
        cnn_ready = '0;
        io_mem_gnt = 1'b0;
        for (bank = 0; bank < BANKS; bank = bank + 1) begin
            bank_a_en[bank] = cpu_access && cpu_bank == BANK_WIDTH'(bank);
            bank_a_addr[bank] = cpu_row;
            bank_a_wdata[bank] = dmem_wdata;
            bank_a_be[bank] = (dmem_we && cpu_valid && cpu_bank == BANK_WIDTH'(bank)) ?
                dmem_wstrb : 4'b0;

            bank_b_en[bank] = 1'b0;
            bank_b_addr[bank] = '0;
            bank_b_wdata[bank] = '0;
            bank_b_be[bank] = '0;
            if (selected_valid[bank]) begin
                owner = int'(selected_owner[bank]);
                if (selected_is_io[bank]) begin
                    io_mem_gnt = 1'b1;
                    if (!selected_error[bank]) begin
                        bank_b_en[bank] = 1'b1;
                        bank_b_addr[bank] = selected_row[bank];
                        bank_b_wdata[bank] = selected_wdata[bank];
                        bank_b_be[bank] = selected_be[bank];
                    end
                end else begin
                    cnn_ready[owner] = 1'b1;
                    bank_b_en[bank] = 1'b1;
                    bank_b_addr[bank] = selected_row[bank];
                    bank_b_wdata[bank] = selected_wdata[bank];
                    bank_b_be[bank] = selected_be[bank];
                end
            end
        end
    end

    always_comb begin : response_mux
        logic [7:0] byte_value;
        integer bank, owner;

        byte_value = 8'b0;
        owner = 0;
        dmem_rdata = cpu_read_pending ?
            (cpu_read_ok ? bank_a_rdata[cpu_read_bank] : 32'b0) : dmem_rdata_hold;
        cnn_response = '0;
        cnn_rdata = '0;
        io_mem_rvalid = 1'b0;
        io_mem_rdata = 32'b0;
        io_mem_error = io_mem_gnt && io_mem_we && io_bad;
        for (bank = 0; bank < BANKS; bank = bank + 1) begin
            if (response_valid[bank]) begin
                if (response_is_io[bank]) begin
                    io_mem_rvalid = 1'b1;
                    io_mem_error = response_error[bank];
                    io_mem_rdata = response_error[bank] ? 32'b0 : bank_b_rdata[bank];
                end else if (!cnn_cancel) begin
                    owner = int'(response_owner[bank]);
                    cnn_response[owner] = 1'b1;
                    byte_value = 8'(bank_b_rdata[bank] >> (8 * response_lane[bank]));
                    cnn_rdata[owner*32 +: 32] = response_write[bank] ? 32'b0 :
                        response_byte[bank] ? {{24{byte_value[7]}}, byte_value} : bank_b_rdata[bank];
                end
            end
        end
    end

    always_ff @(posedge clk) begin : control_state
        integer bank;
        if (!rst_n) begin
            cnn_mem_fault <= 1'b0;
            cpu_read_pending <= 1'b0;
            cpu_read_ok <= 1'b0;
            cpu_read_bank <= '0;
            dmem_rdata_hold <= 32'b0;
            for (bank = 0; bank < BANKS; bank = bank + 1) begin
                next_owner[bank] <= '0;
                response_valid[bank] <= 1'b0;
                response_is_io[bank] <= 1'b0;
                response_write[bank] <= 1'b0;
                response_byte[bank] <= 1'b0;
                response_error[bank] <= 1'b0;
                response_lane[bank] <= '0;
                response_owner[bank] <= '0;
            end
        end else begin
            if (cpu_read_pending)
                dmem_rdata_hold <= cpu_read_ok ? bank_a_rdata[cpu_read_bank] : 32'b0;
            cpu_read_pending <= dmem_re;
            cpu_read_ok <= cpu_valid;
            if (dmem_re && cpu_valid) cpu_read_bank <= cpu_bank;

            if (!cnn_cancel && |(cnn_valid & bad)) cnn_mem_fault <= 1'b1;
            for (bank = 0; bank < BANKS; bank = bank + 1) begin
                response_valid[bank] <= 1'b0;
                if (selected_valid[bank]) begin
                    next_owner[bank] <= selected_owner[bank] == OWNER_WIDTH'(REQUESTERS-1) ? '0 :
                        OWNER_WIDTH'(selected_owner[bank] + 1'b1);
                    if (selected_is_io[bank]) begin
                        if (!selected_write[bank]) begin
                            response_valid[bank] <= 1'b1;
                            response_is_io[bank] <= 1'b1;
                            response_error[bank] <= selected_error[bank];
                        end
                    end else begin
                        response_valid[bank] <= !cnn_cancel;
                        response_is_io[bank] <= 1'b0;
                        response_owner[bank] <= selected_owner[bank];
                        response_write[bank] <= selected_write[bank];
                        response_byte[bank] <= selected_byte[bank];
                        response_lane[bank] <= selected_lane[bank];
                        response_error[bank] <= 1'b0;
                    end
                end
            end
        end
    end

`ifndef SYNTHESIS
    // Preserve the existing read-only testbench hierarchy while the synthesized
    // storage remains encapsulated in each dual-port bank.
    wire [31:0] mem [0:BANKS-1][0:BANK_WORDS-1];
    generate
        for (genvar debug_bank = 0; debug_bank < BANKS; debug_bank = debug_bank + 1) begin : gen_debug_bank
            for (genvar debug_row = 0; debug_row < BANK_WORDS; debug_row = debug_row + 1) begin : gen_debug_row
                assign mem[debug_bank][debug_row] = gen_banks[debug_bank].u_bank.mem[debug_row];
            end
        end
    endgenerate

    initial assert (BANKS >= 1 && (BANKS & (BANKS-1)) == 0 && SRAM_BASE[1:0] == 0 &&
        SRAM_SIZE >= BANKS*4 && SRAM_SIZE % (BANKS*4) == 0 &&
        {1'b0, SRAM_BASE} + SRAM_SIZE <= 33'h100000000)
        else $fatal(1, "invalid banked SRAM configuration");
`endif
endmodule
