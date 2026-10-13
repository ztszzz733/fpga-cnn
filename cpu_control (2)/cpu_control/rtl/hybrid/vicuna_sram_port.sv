// One outstanding OBI request, preserving the complete ID and byte enables.
// Partial word writes become separate byte stores; return only after all finish.
module vicuna_sram_port #(
    parameter logic [31:0] SRAM_BASE=0,SRAM_SIZE=32'h40000,
    parameter integer ID_W=8
)(
    input logic clk,rst_n,enable,
    input logic req,we,input logic [31:0] addr,wdata,input logic [3:0] be,
    input logic [ID_W-1:0] aid,
    output wire gnt,rvalid,output logic [31:0] rdata,
    output logic [ID_W-1:0] rid,output logic error,
    output wire mem_valid,mem_write,mem_byte,
    output logic [31:0] mem_addr,mem_wdata,
    input logic mem_ready,mem_response,input logic [31:0] mem_rdata,
    input logic mem_fault,
    input logic [31:0] arg_src,arg_dst,arg_count,arg_mode,
    output logic finish,output logic [31:0] finish_code,
    output logic fault,output logic [2:0] state,
    output logic [31:0] reads,writes,stalls
);
    localparam IDLE=0,SEND=1,WAIT_MEM=2,REPLY=3;
    logic write_q,whole_q;
    logic [31:0] addr_q,data_q;
    logic [3:0] remain;
    logic [1:0] lane;
    always_comb begin
        lane=0;
        if(remain[0]) lane=0;
        else if(remain[1]) lane=1;
        else if(remain[2]) lane=2;
        else if(remain[3]) lane=3;
        mem_addr=addr_q+(whole_q ? 0 : {30'b0,lane});
        mem_wdata=whole_q ? data_q : ((data_q>>(8*lane))&32'hff);
    end
    assign gnt=enable && state==IDLE && !fault;
    assign rvalid=state==REPLY;
    assign mem_valid=state==SEND && !fault;
    assign mem_write=write_q;
    assign mem_byte=!whole_q;
    always_ff @(posedge clk) begin
        if(!rst_n) begin
            state<=IDLE;fault<=0;error<=0;rdata<=0;rid<=0;
            finish<=0;finish_code<=0;reads<=0;writes<=0;stalls<=0;
            addr_q<=0;data_q<=0;write_q<=0;whole_q<=0;remain<=0;
        end else begin
            finish<=0;
            if(mem_fault) fault<=1;
            if(state==SEND && !mem_ready) stalls<=stalls+1;
            case(state)
                IDLE: if(req && gnt) begin
                    rid<=aid;error<=0;rdata<=0;
                    if(addr==32'hffff0000 && we && be==15) begin
                        finish<=1;finish_code<=wdata;state<=REPLY;
                    end else if(addr>=32'hffff0010 && addr<=32'hffff001c && !we && addr[1:0]==0) begin
                        case(addr[3:2])
                            0:rdata<=arg_src;1:rdata<=arg_dst;
                            2:rdata<=arg_count;3:rdata<=arg_mode;
                        endcase
                        state<=REPLY;
                    end else if(addr[1:0]!=0 || addr<SRAM_BASE ||
                        {1'b0,addr}+4>{1'b0,SRAM_BASE}+SRAM_SIZE || (we && be==0)) begin
                        error<=1;fault<=1;state<=REPLY;
                    end else begin
                        addr_q<=addr;data_q<=wdata;write_q<=we;
                        whole_q<=!we || be==15;remain<=be;state<=SEND;
                    end
                end
                SEND: if(mem_ready) state<=WAIT_MEM;
                WAIT_MEM: if(mem_response) begin
                    if(write_q) writes<=writes+1;else reads<=reads+1;
                    rdata<=mem_rdata;
                    if(!whole_q && (remain & ~(4'b1<<lane))!=0) begin
                        remain<=remain & ~(4'b1<<lane);state<=SEND;
                    end else state<=REPLY;
                end
                REPLY: state<=IDLE;
                default: state<=IDLE;
            endcase
        end
    end
endmodule
