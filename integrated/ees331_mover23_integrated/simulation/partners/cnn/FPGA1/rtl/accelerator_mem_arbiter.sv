`timescale 1ns/1ps
// Parameterized round-robin clients; production: reader + 8 execution units.
// One outstanding transaction. Owner is retained through byte-write RMW and
// response delivery. A stalled client cannot change the external request.
module accelerator_mem_arbiter #(parameter CLIENTS=3, parameter OWNER_BITS=$clog2(CLIENTS))(
    input wire clk,rst_n,clear,
    input wire [CLIENTS-1:0] valid,write,byte_access,input wire [CLIENTS*32-1:0] addr,wdata,
    output reg [CLIENTS-1:0] ready,output wire [CLIENTS-1:0] response,
    output wire cmd_valid,cmd_write,cmd_byte,output wire [31:0] cmd_addr,cmd_wdata,
    input wire cmd_ready,rsp_valid,output wire idle,output reg [OWNER_BITS-1:0] owner
);
    reg pending;reg [OWNER_BITS-1:0] next_client;
    reg [OWNER_BITS-1:0] chosen;reg found;integer n,index;
    always @* begin
        chosen=0;found=0;ready=0;
        for(n=0;n<CLIENTS;n=n+1) begin
            index=next_client+n;if(index>=CLIENTS) index=index-CLIENTS;
            if(!found && valid[index]) begin chosen=index;found=1;end
        end
        if(!pending && !clear && found) ready[chosen]=cmd_ready;
    end
    assign idle=!pending;
    assign cmd_valid=!pending && !clear && found;
    assign cmd_write=write[chosen];assign cmd_byte=byte_access[chosen];
    assign cmd_addr=addr[chosen*32+:32];assign cmd_wdata=wdata[chosen*32+:32];
    assign response=(pending && rsp_valid && !clear) ? ({{(CLIENTS-1){1'b0}},1'b1}<<owner) : {CLIENTS{1'b0}};
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin pending<=0;owner<=0;next_client<=0;end
        else if(clear) begin pending<=0;owner<=0;next_client<=0;end
        else begin
            if(cmd_valid && cmd_ready) begin
                pending<=1;owner<=chosen;next_client<=chosen==CLIENTS-1 ? 0 : chosen+1'b1;
            end
            if(pending && rsp_valid) pending<=0;
        end
    end
endmodule
