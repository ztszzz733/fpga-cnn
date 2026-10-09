// Active UART storage reader with a fixed batch and three-wire CPU handshake.
// Peer protocol: IMIO read requests, IMOR read replies (see docs/autoload_uart_protocol.md).
module image_bridge_autoload #(
    parameter integer CLOCK_HZ = 50_000_000,
    parameter integer BAUD = 115200,
    parameter integer TIMEOUT_CYCLES = CLOCK_HZ,
    parameter integer CHUNK_BYTES = 64,
    parameter logic [31:0] SRAM_BASE = 0,
    parameter logic [31:0] SRAM_SIZE = 32'h0004_0000,
    parameter logic [31:0] LOAD_CTRL_ADDR = 32'h40,
    parameter logic [31:0] SOURCE_BASE = 0,
    parameter logic [31:0] LOAD_BASE = 32'h100,
    parameter integer LOAD_BYTES = 256,
    parameter logic [31:0] EXPECTED_CRC32 = 32'hfe679cc9
) (
    input logic clk, rst_n, uart_rx,
    output wire uart_tx,
    input logic load_req,
    output wire load_complete, load_error,
    output wire io_mem_req, io_mem_we,
    output wire [31:0] io_mem_addr, io_mem_wdata,
    output wire [3:0] io_mem_be,
    input logic io_mem_gnt, io_mem_rvalid,
    input logic [31:0] io_mem_rdata,
    input logic io_mem_error,
    output wire bridge_ready, bridge_busy,
    output logic bridge_error
);
    typedef enum logic [3:0] {IDLE, BUILD, REQUEST_CRC, SEND, DRAIN,
        RECEIVE, VERIFY, STORE, COMPLETE, HALTED} state_t;
    state_t state;
    logic [7:0] request_bytes[0:15];
    logic [7:0] response_bytes[0:CHUNK_BYTES+15];
    logic [7:0] rx_data, tag, error_code;
    logic rx_valid, rx_error, tx_ready, failed;
    integer chunk_length, index, timer;
    logic [31:0] offset, packet_crc, batch_crc;
    wire [31:0] source_address = SOURCE_BASE + offset;
    wire [31:0] destination = LOAD_BASE + offset + index;
    wire [32:0] load_end = {1'b0,LOAD_BASE} + LOAD_BYTES;
    wire [32:0] sram_end = {1'b0,SRAM_BASE} + SRAM_SIZE;
    wire config_valid = LOAD_BYTES > 0 && LOAD_BASE >= SRAM_BASE &&
        load_end <= sram_end && load_end <= 33'h100000000 &&
        ({1'b0,SOURCE_BASE}+LOAD_BYTES <= 33'h100000000) &&
        (load_end <= {1'b0,LOAD_CTRL_ADDR} ||
         {1'b0,LOAD_BASE} >= {1'b0,LOAD_CTRL_ADDR}+8);

    function automatic [31:0] crc_byte(input [31:0] old, input [7:0] value);
        reg [31:0] c;
        integer k;
        begin
            c = old ^ value;
            for (k=0;k<8;k=k+1) c=c[0] ? (c>>1)^32'hedb88320 : c>>1;
            crc_byte = c;
        end
    endfunction

    autoload_uart_rx #(.DIVISOR(CLOCK_HZ/BAUD)) u_rx
        (.clk(clk),.rst_n(rst_n),.rx(uart_rx),.data(rx_data),.valid(rx_valid),.error(rx_error));
    autoload_uart_tx #(.DIVISOR(CLOCK_HZ/BAUD)) u_tx
        (.clk(clk),.rst_n(rst_n),.valid(state==SEND),.data(state==SEND ? request_bytes[index] : 8'b0),
         .ready(tx_ready),.tx(uart_tx));

    assign load_complete = rst_n && state==COMPLETE;
    assign load_error = load_complete && failed;
    assign bridge_ready = rst_n && state==IDLE && !bridge_error;
    assign bridge_busy = rst_n && state!=IDLE && state!=COMPLETE && state!=HALTED;
    assign io_mem_req = rst_n && state==STORE;
    assign io_mem_we = 1'b1;
    assign io_mem_addr = {destination[31:2],2'b00};
    assign io_mem_be = io_mem_req ? (4'b0001 << destination[1:0]) : 4'b0;
    assign io_mem_wdata = io_mem_req ?
        ({24'b0,response_bytes[12+index]} << (8*destination[1:0])) : 32'b0;

    // All errors latch and require system reset after CPU acknowledgement.
    // This prevents a late external reply from becoming a fresh transaction.
    task automatic fail(input [7:0] code);
        begin
            failed <= 1;
            bridge_error <= 1;
            error_code <= code;
            state <= COMPLETE;
        end
    endtask

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state<=IDLE; chunk_length<=0; index<=0; timer<=0; offset<=0;
            tag<=0; failed<=0; bridge_error<=0; error_code<=0;
            packet_crc<=32'hffffffff; batch_crc<=32'hffffffff;
        end else begin
            case (state)
                IDLE: if (load_req) begin
                    offset<=0; index<=0; timer<=0; failed<=0; error_code<=0;
                    batch_crc<=32'hffffffff;
                    chunk_length <= LOAD_BYTES < CHUNK_BYTES ? LOAD_BYTES : CHUNK_BYTES;
                    if (!config_valid) fail(8'd1);
                    else state<=BUILD;
                end
                BUILD: begin
                    request_bytes[0]<=8'h49; request_bytes[1]<=8'h4d;
                    request_bytes[2]<=8'h49; request_bytes[3]<=8'h4f;
                    request_bytes[4]<=2; request_bytes[5]<=tag;
                    request_bytes[6]<=chunk_length; request_bytes[7]<=chunk_length>>8;
                    for (integer b=0;b<4;b=b+1)
                        request_bytes[8+b]<=source_address>>(8*b);
                    packet_crc<=32'hffffffff; index<=0; state<=REQUEST_CRC;
                end
                REQUEST_CRC: begin
                    packet_crc<=crc_byte(packet_crc,request_bytes[index]);
                    if (index==11) begin
                        for (integer b=0;b<4;b=b+1)
                            request_bytes[12+b]<=(~crc_byte(packet_crc,request_bytes[index]))>>(8*b);
                        index<=0; state<=SEND;
                    end else index<=index+1;
                end
                SEND: if (tx_ready) begin
                    if (index==15) state<=DRAIN;
                    else index<=index+1;
                end
                DRAIN: if (tx_ready) begin
                    state<=RECEIVE; index<=0; timer<=0; packet_crc<=32'hffffffff;
                end
                RECEIVE: begin
                    if (rx_error) fail(8'd2);
                    else if (rx_valid) begin
                        timer<=0;
                        response_bytes[index]<=rx_data;
                        if (index<12+chunk_length) packet_crc<=crc_byte(packet_crc,rx_data);
                        if (index==15+chunk_length) state<=VERIFY;
                        else index<=index+1;
                    end else if (timer>=TIMEOUT_CYCLES-1) fail(8'd3);
                    else timer<=timer+1;
                end
                VERIFY: begin
                    if ({response_bytes[0],response_bytes[1],response_bytes[2],response_bytes[3]}!=32'h494d4f52 ||
                        response_bytes[4]!=0 || response_bytes[5]!=tag ||
                        {response_bytes[7],response_bytes[6]}!=chunk_length ||
                        {response_bytes[11],response_bytes[10],response_bytes[9],response_bytes[8]}!=source_address)
                        fail(8'd4);
                    else if ({response_bytes[15+chunk_length],response_bytes[14+chunk_length],
                              response_bytes[13+chunk_length],response_bytes[12+chunk_length]} != ~packet_crc)
                        fail(8'd5);
                    else begin index<=0; timer<=0; state<=STORE; end
                end
                STORE: begin
                    if (io_mem_gnt) begin
                        timer<=0;
                        if (io_mem_error) fail(8'd6);
                        else begin
                            batch_crc<=crc_byte(batch_crc,response_bytes[12+index]);
                            if (index==chunk_length-1) begin
                                if (offset+chunk_length==LOAD_BYTES) begin
                                    if (~crc_byte(batch_crc,response_bytes[12+index])!=EXPECTED_CRC32)
                                        fail(8'd8);
                                    else begin state<=COMPLETE; failed<=0; tag<=tag+1'b1; end
                                end else begin
                                    offset<=offset+chunk_length;
                                    chunk_length <= LOAD_BYTES-offset-chunk_length < CHUNK_BYTES ?
                                                    LOAD_BYTES-offset-chunk_length : CHUNK_BYTES;
                                    tag<=tag+1'b1; index<=0; state<=BUILD;
                                end
                            end else index<=index+1;
                        end
                    end else if (timer>=TIMEOUT_CYCLES-1) fail(8'd7);
                    else timer<=timer+1;
                end
                COMPLETE: if (!load_req) begin
                    state<=failed ? HALTED : IDLE;
                    failed<=0;
                end
                HALTED: state<=HALTED;
                default: fail(8'd9);
            endcase
        end
    end
`ifndef SYNTHESIS
    initial begin
        assert (CLOCK_HZ/BAUD>=4 && CHUNK_BYTES>=1 && CHUNK_BYTES<=256 && TIMEOUT_CYCLES>0)
            else $fatal(1,"invalid autoload UART parameters");
    end
`endif
endmodule
