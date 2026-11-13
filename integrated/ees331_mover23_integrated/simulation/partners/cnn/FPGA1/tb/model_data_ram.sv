`timescale 1ns/1ps
// Simulation-only shared Data RAM. Request completes on a rising clock edge
// with ready=1. The periodic delay is deterministic and exercises long stalls.
module model_data_ram #(parameter BYTES=1048576, WAIT_CYCLES=3)(
    input wire clk,rst_n, input wire [31:0] addr,wdata,
    input wire rd,wr, output reg [31:0] rdata, output wire ready
);
    reg [7:0] bytes [0:BYTES-1];
    integer cycle=0, reads=0,writes=0;
    reg stalled=0; reg [31:0] prev_addr,prev_wdata; reg prev_rd,prev_wr;
    assign ready=(rd || wr) && ((WAIT_CYCLES==0) || cycle%(WAIT_CYCLES+1)==WAIT_CYCLES);
    // Present read data before the next rising-edge handshake. This avoids
    // a huge combinational sensitivity list for the simulation byte array.
    always @(negedge clk) begin
        rdata=0;
        if(rd && addr <= BYTES-4)
            rdata={bytes[addr+3],bytes[addr+2],bytes[addr+1],bytes[addr]};
    end
    always @(posedge clk) begin
        if(!rst_n) begin cycle<=0; stalled<=0; reads<=0; writes<=0; end
        else begin
            cycle<=cycle+1;
            if(rd && wr) $fatal(1,"simultaneous RAM read/write");
            if((rd || wr) && ((^addr)===1'bx || addr[1:0]!=0 || addr>BYTES-4)) $fatal(1,"RAM address %h",addr);
            if(stalled && {addr,wdata,rd,wr}!=={prev_addr,prev_wdata,prev_rd,prev_wr})
                $fatal(1,"RAM request changed during stall");
            stalled <= (rd || wr) && !ready;
            prev_addr<=addr; prev_wdata<=wdata; prev_rd<=rd; prev_wr<=wr;
            if(rd && ready) reads<=reads+1;
            if(wr && ready) begin
                bytes[addr]<=wdata[7:0]; bytes[addr+1]<=wdata[15:8];
                bytes[addr+2]<=wdata[23:16]; bytes[addr+3]<=wdata[31:24];
                writes<=writes+1;
            end
        end
    end
endmodule
