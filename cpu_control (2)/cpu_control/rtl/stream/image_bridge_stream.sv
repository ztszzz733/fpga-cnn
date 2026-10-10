// Two packet slots decouple UART reception from pixel consumption.
// IMIO requests / IMOR replies; CRC-checked image payload only, no weights/tasks.
module image_bridge_stream #(
    parameter integer CLOCK_HZ=100000000, BAUD=25000000,
    WIDTH=524, HEIGHT=524, FRAMES=6, CHUNK=1024, TIMEOUT=10000
)(
    input wire clk,rst_n,uart_rx,load_req,
    output wire uart_tx,load_complete,load_error,bridge_ready,bridge_busy,
    output logic bridge_error,
    output wire pixel_valid,input wire pixel_ready,output wire [7:0] pixel_data,
    output wire pixel_sof,pixel_eof,output wire [31:0] pixel_frame,
    output wire rx_receiving, output logic [31:0] packets_checked
);
    localparam integer PIXELS=WIDTH*HEIGHT;
    typedef enum logic [3:0] {IDLE,FREE,BUILD,CRC,SEND,DRAIN,RECEIVE,VERIFY,FINISH,COMPLETE,HALTED} state_t;
    state_t state;
    logic [7:0] request_bytes[0:15],slots[0:1][0:CHUNK+15];
    logic [1:0] occupied;
    logic wr_slot,rd_slot;
    integer lengths[0:1];
    integer slot_frames[0:1],slot_offsets[0:1];
    integer frame,offset,length,index,timer,read_index;
    logic [7:0] tag,rx_data;
    logic rx_valid,rx_error,tx_ready;
    logic [31:0] crc;
    wire [31:0] address=frame*PIXELS+offset;
    function automatic [31:0] crc_byte(input [31:0] old,input [7:0] value);
        reg [31:0] c;
        begin c=old^value;for(integer k=0;k<8;k++) c=c[0] ? (c>>1)^32'hedb88320 : c>>1;return c;end
    endfunction
    autoload_uart_rx #(.DIVISOR(CLOCK_HZ/BAUD)) u_rx
        (.clk(clk),.rst_n(rst_n),.rx(uart_rx),.data(rx_data),.valid(rx_valid),.error(rx_error));
    autoload_uart_tx #(.DIVISOR(CLOCK_HZ/BAUD)) u_tx
        (.clk(clk),.rst_n(rst_n),.valid(state==SEND),.data(state==SEND ? request_bytes[index] : 8'd0),.ready(tx_ready),.tx(uart_tx));
    assign bridge_ready=rst_n && state==IDLE;
    assign bridge_busy=rst_n && state!=IDLE && state!=COMPLETE && state!=HALTED;
    assign load_complete=rst_n && state==COMPLETE;
    assign load_error=load_complete && bridge_error;
    assign rx_receiving=state==RECEIVE;
    assign pixel_valid=rst_n && occupied[rd_slot] && !bridge_error;
    assign pixel_data=slots[rd_slot][12+read_index];
    assign pixel_frame=slot_frames[rd_slot];
    assign pixel_sof=slot_offsets[rd_slot]==0 && read_index==0;
    assign pixel_eof=slot_offsets[rd_slot]+read_index==PIXELS-1;
    task automatic fail;
        bridge_error<=1;state<=COMPLETE;
    endtask
    always_ff @(posedge clk) begin
        if(!rst_n) begin
            state<=IDLE;occupied<=0;wr_slot<=0;rd_slot<=0;read_index<=0;
            frame<=0;offset<=0;length<=0;index<=0;timer<=0;tag<=0;
            crc<=32'hffffffff;bridge_error<=0;packets_checked<=0;
            for(integer k=0;k<2;k++) begin lengths[k]<=0;slot_frames[k]<=0;slot_offsets[k]<=0;end
        end else begin
            if(pixel_valid && pixel_ready) begin
                if(read_index==lengths[rd_slot]-1) begin
                    occupied[rd_slot]<=0;rd_slot<=~rd_slot;read_index<=0;
                end else read_index<=read_index+1;
            end
            case(state)
            IDLE: if(load_req) begin
                frame<=0;offset<=0;tag<=0;packets_checked<=0;state<=FREE;
            end
            FREE: if(!occupied[wr_slot]) begin
                length<=PIXELS-offset<CHUNK ? PIXELS-offset : CHUNK;state<=BUILD;
            end
            BUILD: begin
                request_bytes[0]<=8'h49;request_bytes[1]<=8'h4d;request_bytes[2]<=8'h49;request_bytes[3]<=8'h4f;
                request_bytes[4]<=2;request_bytes[5]<=tag;request_bytes[6]<=length;request_bytes[7]<=length>>8;
                for(integer k=0;k<4;k++) request_bytes[8+k]<=address>>(8*k);
                crc<=32'hffffffff;index<=0;state<=CRC;
            end
            CRC: begin
                crc<=crc_byte(crc,request_bytes[index]);
                if(index==11) begin
                    for(integer k=0;k<4;k++) request_bytes[12+k]<=(~crc_byte(crc,request_bytes[index]))>>(8*k);
                    index<=0;state<=SEND;
                end else index<=index+1;
            end
            SEND: if(tx_ready) begin if(index==15) state<=DRAIN;else index<=index+1;end
            DRAIN: if(tx_ready) begin index<=0;timer<=0;crc<=32'hffffffff;state<=RECEIVE;end
            RECEIVE: begin
                if(rx_error) fail();
                else if(rx_valid) begin
                    slots[wr_slot][index]<=rx_data;timer<=0;
                    if(index<12+length) crc<=crc_byte(crc,rx_data);
                    if(index==15+length) state<=VERIFY;else index<=index+1;
                end else if(timer==TIMEOUT-1) fail();
                else timer<=timer+1;
            end
            VERIFY: begin
                if({slots[wr_slot][0],slots[wr_slot][1],slots[wr_slot][2],slots[wr_slot][3]}!=32'h494d4f52 ||
                   slots[wr_slot][4]!=0 || slots[wr_slot][5]!=tag ||
                   {slots[wr_slot][7],slots[wr_slot][6]}!=length ||
                   {slots[wr_slot][11],slots[wr_slot][10],slots[wr_slot][9],slots[wr_slot][8]}!=address ||
                   {slots[wr_slot][15+length],slots[wr_slot][14+length],slots[wr_slot][13+length],slots[wr_slot][12+length]}!=~crc)
                    fail();
                else begin
                    occupied[wr_slot]<=1;lengths[wr_slot]<=length;
                    slot_frames[wr_slot]<=frame;slot_offsets[wr_slot]<=offset;
                    wr_slot<=~wr_slot;tag<=tag+1'b1;packets_checked<=packets_checked+1;
                    if(offset+length==PIXELS) begin
                        offset<=0;frame<=frame+1;state<=frame==FRAMES-1 ? FINISH : FREE;
                    end else begin offset<=offset+length;state<=FREE;end
                end
            end
            FINISH: if(occupied==0) state<=COMPLETE;
            COMPLETE: if(!load_req) state<=bridge_error ? HALTED : IDLE;
            HALTED: state<=HALTED;
            default: fail();
            endcase
        end
    end
`ifndef SYNTHESIS
    initial assert(CHUNK>0 && CHUNK<=1024 && FRAMES>0 && CLOCK_HZ/BAUD>=4);
    always @(posedge clk) if(rst_n) begin
        if(state==RECEIVE || state==VERIFY) assert(!occupied[wr_slot]) else $fatal(1,"packet overwrite");
    end
`endif
endmodule
