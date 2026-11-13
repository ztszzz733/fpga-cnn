// Stop-and-wait UART SRAM transport. See docs/uart_image_bridge_protocol.md.
module image_bridge #(
    parameter integer CLOCK_HZ = 50_000_000,
    parameter integer BAUD = 115200,
    parameter integer MAX_PAYLOAD = 256,
    parameter integer TIMEOUT_CYCLES = CLOCK_HZ,
    parameter logic [31:0] SRAM_BASE = 0,
    parameter logic [31:0] SRAM_SIZE = 32'h0004_0000
) (
    input logic clk, rst_n, uart_rx,
    output wire uart_tx,
    output wire io_mem_req, io_mem_we,
    output wire [31:0] io_mem_addr, io_mem_wdata,
    output wire [3:0] io_mem_be,
    input logic io_mem_gnt, io_mem_rvalid,
    input logic [31:0] io_mem_rdata,
    input logic io_mem_error,
    output wire bridge_ready, bridge_busy,
    output logic bridge_error
);
    typedef enum logic [3:0] {RECEIVE, CHECK_CRC, REQUEST, READ_WAIT,
        PREPARE, CHECKSUM, SEND, DRAIN, HALTED} state_t;
    state_t state;
    logic [7:0] packet [0:MAX_PAYLOAD+15];
    logic [7:0] reply [0:MAX_PAYLOAD+15];
    logic [7:0] rx_data, status;
    logic rx_valid, rx_error, tx_ready;
    integer count, expected, length, index, reply_length, tx_count, timer;
    logic [31:0] crc, address;
    logic write_command, halt_after_reply;
    wire [31:0] byte_address = address + index;
    wire [31:0] header_address = {packet[11],packet[10],packet[9],packet[8]};
    wire [15:0] header_length = {packet[7],packet[6]};
    wire [32:0] offset = {1'b0,header_address} - {1'b0,SRAM_BASE};

    function automatic [31:0] crc_byte(input [31:0] previous, input [7:0] value);
        reg [31:0] c;
        integer n;
        begin
            c = previous ^ value;
            for (n=0;n<8;n=n+1) c = c[0] ? ((c >> 1) ^ 32'hedb88320) : (c >> 1);
            crc_byte = c;
        end
    endfunction

    bridge_uart_rx #(.DIVISOR(CLOCK_HZ/BAUD)) u_rx
        (.clk(clk),.rst_n(rst_n),.rx(uart_rx),.data(rx_data),.valid(rx_valid),.error(rx_error));
    bridge_uart_tx #(.DIVISOR(CLOCK_HZ/BAUD)) u_tx
        (.clk(clk),.rst_n(rst_n),.data(reply[tx_count]),.valid(state==SEND),
         .ready(tx_ready),.tx(uart_tx));

    assign bridge_ready = rst_n && state==RECEIVE && count==0;
    assign bridge_busy = rst_n && state!=HALTED && !bridge_ready;
    assign io_mem_req = rst_n && state==REQUEST;
    assign io_mem_we = write_command;
    assign io_mem_addr = {byte_address[31:2],2'b00};
    assign io_mem_be = write_command ? (4'b0001 << byte_address[1:0]) : 4'b0;
    assign io_mem_wdata = {24'b0,packet[12+index]} << (8*byte_address[1:0]);

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state<=RECEIVE; count<=0; expected<=16; length<=0; index<=0;
            reply_length<=0; tx_count<=0; timer<=0; crc<=32'hffffffff;
            address<=0; write_command<=0; status<=0;
            halt_after_reply<=0; bridge_error<=0;
        end else begin
            case (state)
                RECEIVE: begin
                    if (rx_error || (count!=0 && timer>=TIMEOUT_CYCLES-1)) begin
                        count<=0; timer<=0; crc<=32'hffffffff; bridge_error<=1;
                    end else if (rx_valid) begin
                        timer<=0;
                        // Seek IMIO, including an overlapping first magic byte.
                        if (count<4 && rx_data != ((count==0 || count==2) ? 8'h49 :
                            ((count==1) ? 8'h4d : 8'h4f))) begin
                            count <= rx_data==8'h49 ? 1 : 0;
                            crc <= rx_data==8'h49 ? crc_byte(32'hffffffff,8'h49) : 32'hffffffff;
                            if (rx_data==8'h49) packet[0]<=rx_data;
                        end else begin
                            packet[count]<=rx_data;
                            count<=count+1;
                            if (count<12 || count<expected-4) crc<=crc_byte(crc,rx_data);
                            if (count==11) begin
                                if ((packet[4]!=1 && packet[4]!=2) ||
                                    header_length==0 || header_length>MAX_PAYLOAD) begin
                                    status<=2; reply_length<=0; state<=PREPARE; bridge_error<=1;
                                end else expected<=16 + ((packet[4]==1) ? header_length : 0);
                            end else if (count>=12 && count==expected-1) state<=CHECK_CRC;
                        end
                    end else if (count!=0) timer<=timer+1;
                end
                CHECK_CRC: begin
                    timer<=0; index<=0; address<=header_address;
                    length<=header_length; write_command<=packet[4]==1;
                    reply_length<=0;
                    if ({packet[expected-1],packet[expected-2],packet[expected-3],packet[expected-4]} != ~crc) begin
                        status<=1; state<=PREPARE; bridge_error<=1;
                    end else if (offset>={1'b0,SRAM_SIZE} ||
                                 offset+header_length>{1'b0,SRAM_SIZE}) begin
                        status<=3; state<=PREPARE; bridge_error<=1;
                    end else begin status<=0; state<=REQUEST; end
                end
                REQUEST: begin
                    if (io_mem_gnt) begin
                        timer<=0;
                        if (!write_command) state<=READ_WAIT;
                        else if (io_mem_error) begin
                            status<=4; state<=PREPARE; bridge_error<=1;
                        end else if (index==length-1) state<=PREPARE;
                        else index<=index+1;
                    end else if (timer>=TIMEOUT_CYCLES-1) begin
                        status<=5; state<=PREPARE; bridge_error<=1; halt_after_reply<=1;
                    end else timer<=timer+1;
                end
                READ_WAIT: begin
                    if (io_mem_rvalid) begin
                        timer<=0;
                        if (io_mem_error) begin
                            status<=4; state<=PREPARE; bridge_error<=1;
                        end else begin
                            reply[12+index]<=io_mem_rdata >> (8*byte_address[1:0]);
                            if (index==length-1) begin reply_length<=length; state<=PREPARE; end
                            else begin index<=index+1; state<=REQUEST; end
                        end
                    end else if (timer>=TIMEOUT_CYCLES-1) begin
                        status<=5; state<=PREPARE; bridge_error<=1; halt_after_reply<=1;
                    end else timer<=timer+1;
                end
                PREPARE: begin
                    reply[0]<=8'h49; reply[1]<=8'h4d; reply[2]<=8'h4f; reply[3]<=8'h52;
                    reply[4]<=status; reply[5]<=packet[5];
                    reply[6]<=reply_length[7:0]; reply[7]<=reply_length[15:8];
                    reply[8]<=packet[8]; reply[9]<=packet[9]; reply[10]<=packet[10]; reply[11]<=packet[11];
                    count<=0; crc<=32'hffffffff; state<=CHECKSUM;
                end
                CHECKSUM: begin
                    if (count<12+reply_length) begin
                        crc<=crc_byte(crc,reply[count]); count<=count+1;
                    end else begin
                        reply[count]<=~crc[7:0]; reply[count+1]<=~crc[15:8];
                        reply[count+2]<=~crc[23:16]; reply[count+3]<=~crc[31:24];
                        tx_count<=0; state<=SEND;
                    end
                end
                SEND: if (tx_ready) begin
                    if (tx_count==15+reply_length) state<=DRAIN;
                    else tx_count<=tx_count+1;
                end
                DRAIN: if (tx_ready) begin
                    state<=halt_after_reply ? HALTED : RECEIVE;
                    count<=0; timer<=0; crc<=32'hffffffff;
                end
                HALTED: state<=HALTED;
                default: state<=HALTED;
            endcase
        end
    end
`ifndef SYNTHESIS
    initial begin
        assert (CLOCK_HZ/BAUD>=4 && MAX_PAYLOAD>=1 && MAX_PAYLOAD<=65535 && TIMEOUT_CYCLES>0)
            else $fatal(1,"invalid UART bridge parameters");
        assert (SRAM_BASE[1:0]==0 && SRAM_SIZE>=4 && SRAM_SIZE[1:0]==0 &&
                {1'b0,SRAM_BASE}+{1'b0,SRAM_SIZE}<=33'h100000000)
            else $fatal(1,"invalid UART SRAM range");
    end
`endif
endmodule

module bridge_uart_rx #(parameter integer DIVISOR=434)(
    input logic clk,rst_n,rx, output logic [7:0] data,
    output logic valid,error
);
    (* ASYNC_REG="TRUE" *) logic [1:0] sync_rx;
    logic [7:0] shift;
    integer phase,ticks,bit_index;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            sync_rx<=2'b11; phase<=0; ticks<=0; bit_index<=0;
            shift<=0; data<=0; valid<=0; error<=0;
        end else begin
            sync_rx<={sync_rx[0],rx}; valid<=0; error<=0;
            case (phase)
                0: if (!sync_rx[1]) begin ticks<=DIVISOR/2-1; phase<=1; end
                1: if (ticks!=0) ticks<=ticks-1;
                   else if (!sync_rx[1]) begin ticks<=DIVISOR-1; bit_index<=0; phase<=2; end
                   else phase<=0;
                2: if (ticks!=0) ticks<=ticks-1;
                   else begin
                       shift[bit_index]<=sync_rx[1]; ticks<=DIVISOR-1;
                       if (bit_index==7) phase<=3; else bit_index<=bit_index+1;
                   end
                3: if (ticks!=0) ticks<=ticks-1;
                   else if (sync_rx[1]) begin data<=shift; valid<=1; phase<=0; end
                   else begin error<=1; phase<=4; end
                4: if (sync_rx[1]) phase<=0;
                default: phase<=0;
            endcase
        end
    end
endmodule

module bridge_uart_tx #(parameter integer DIVISOR=434)(
    input logic clk,rst_n,valid, input logic [7:0] data,
    output wire ready,tx
);
    logic busy;
    logic [9:0] shift;
    integer ticks,bit_index;
    assign ready=!busy;
    assign tx=busy ? shift[0] : 1'b1;
    always_ff @(posedge clk) begin
        if (!rst_n) begin busy<=0; shift<=10'h3ff; ticks<=0; bit_index<=0; end
        else if (!busy) begin
            if (valid) begin
                busy<=1; shift<={1'b1,data,1'b0}; ticks<=DIVISOR-1; bit_index<=0;
            end
        end else if (ticks!=0) ticks<=ticks-1;
        else if (bit_index==9) busy<=0;
        else begin shift<={1'b1,shift[9:1]}; ticks<=DIVISOR-1; bit_index<=bit_index+1; end
    end
endmodule
