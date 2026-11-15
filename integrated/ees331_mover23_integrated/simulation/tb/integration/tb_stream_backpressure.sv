`timescale 1ns/1ps
// Saturate both packet slots, then throttle the consumer and check ordering.
module tb_stream_backpressure;
    logic clk=0,rst_n=0,uart_rx=1,load_req=0,pixel_ready=0;
    wire uart_tx,load_complete,load_error,bridge_ready,bridge_busy,bridge_error;
    wire pixel_valid,pixel_sof,pixel_eof,rx_receiving;
    wire [7:0] pixel_data;wire [31:0] pixel_frame,packets_checked;
    integer cycles=0,requests=0,consumed=0,addr,len;
    logic release_consumer=0;reg [7:0] req[0:15],reply[0:79],saved;
    reg [31:0] crc;reg stalled=0;
    always #5 clk=~clk;
    image_bridge_stream #(.WIDTH(16),.HEIGHT(16),.FRAMES(3),.CHUNK(64)) dut(.*);
    function automatic [31:0] crc_byte(input [31:0] old,input [7:0] value);
        reg [31:0] c;begin c=old^value;for(integer k=0;k<8;k++)c=c[0]?(c>>1)^32'hedb88320:c>>1;return c;end
    endfunction
    task automatic receive_byte(output reg [7:0] value);
        @(negedge uart_tx);#60;for(integer k=0;k<8;k++)begin value[k]=uart_tx;#40;end
        assert(uart_tx) else $fatal(1,"bad stop");
    endtask
    task automatic send_byte(input [7:0] value);
        uart_rx=0;#40;for(integer k=0;k<8;k++)begin uart_rx=value[k];#40;end uart_rx=1;#40;
    endtask
    initial begin
        repeat(5)@(negedge clk);rst_n=1;load_req=1;
        repeat(15000)@(negedge clk);
        assert(requests==2 && packets_checked==2 && consumed==0) else $fatal(1,"packet slots did not backpressure");
        release_consumer=1;
        wait(load_complete);assert(!load_error && consumed==768 && requests==12) else $fatal(1,"stream count");
        @(negedge clk);load_req=0;repeat(5)@(negedge clk);assert(bridge_ready);
        $display("PASS tb_stream_backpressure packets=12 pixels=768 full_slots=2");$finish;
    end
    always @(negedge clk) pixel_ready=release_consumer && cycles%17<3;
    always @(posedge clk) if(rst_n) begin
        cycles++;if(cycles>150000)$fatal(1,"timeout");
        if(stalled) assert(pixel_valid && pixel_data==saved) else $fatal(1,"stalled data changed");
        stalled=pixel_valid && !pixel_ready;saved=pixel_data;
        if(pixel_valid && pixel_ready) begin
            assert(pixel_data==8'(consumed*37+11) && pixel_frame==consumed/256 &&
                   pixel_sof==(consumed%256==0) && pixel_eof==(consumed%256==255)) else $fatal(1,"pixel order/flags");
            consumed++;
        end
    end
    initial forever begin
        for(integer i=0;i<16;i++) receive_byte(req[i]);
        addr={req[11],req[10],req[9],req[8]};len={req[7],req[6]};
        assert(addr==requests*64 && len==64) else $fatal(1,"request order");requests++;
        #120;reply[0]='h49;reply[1]='h4d;reply[2]='h4f;reply[3]='h52;
        reply[4]=0;reply[5]=req[5];reply[6]=64;reply[7]=0;
        for(integer i=0;i<4;i++)reply[8+i]=addr>>(8*i);
        for(integer i=0;i<64;i++)reply[12+i]=(addr+i)*37+11;
        crc=32'hffffffff;for(integer i=0;i<76;i++)crc=crc_byte(crc,reply[i]);crc=~crc;
        for(integer i=0;i<4;i++)reply[76+i]=crc>>(8*i);
        for(integer i=0;i<80;i++)send_byte(reply[i]);
    end
endmodule
